"""
RAG 向量检索 API 路由
提供文档向量化、检索、管理的 HTTP 接口
"""
import os
from flask import Blueprint, request, jsonify, session
from config.logging_config import logger

rag_bp = Blueprint('rag', __name__, url_prefix='/api/rag')


def _get_username():
    """从 session 获取当前用户名"""
    return session.get('user', {}).get('username', 'anonymous')


@rag_bp.route('/embed-directory', methods=['POST'])
def embed_directory():
    """批量向量化目录下的所有 docx 文件"""
    try:
        from .rag_service import embed_directory as do_embed_dir
        
        data = request.get_json() or {}
        dir_path = data.get('dir_path', '')
        force = data.get('force', False)
        username = _get_username()
        
        if not dir_path:
            # 默认目录
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            dir_path = os.path.join(base, 'file_process', 'download_doc')
        
        if not os.path.isdir(dir_path):
            return jsonify({'success': False, 'error': f'目录不存在: {dir_path}'}), 400
        
        result = do_embed_dir(dir_path, force=force, username=username)
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"[RAG API] 批量向量化失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@rag_bp.route('/embed-file', methods=['POST'])
def embed_file():
    """向量化单个文件（仅管理员）"""
    denied = _require_admin()
    if denied:
        return denied
    try:
        from .rag_service import embed_and_store_document
        
        data = request.get_json() or {}
        filepath = data.get('filepath', '')
        force = data.get('force', False)
        username = _get_username()
        
        if not filepath or not os.path.isfile(filepath):
            return jsonify({'success': False, 'error': f'文件不存在: {filepath}'}), 400
        
        result = embed_and_store_document(filepath, force=force, username=username)
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logger.error(f"[RAG API] 向量化失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@rag_bp.route('/search', methods=['POST'])
def search():
    """语义检索"""
    try:
        from .rag_service import search_similar_chunks, format_search_results_as_context
        
        data = request.get_json() or {}
        query = data.get('query', '').strip()
        top_k = data.get('top_k', 10)
        threshold = data.get('threshold', 0.5)
        product_filter = data.get('product_filter')
        format_as_context = data.get('format_as_context', False)
        username = _get_username()
        
        if not query:
            return jsonify({'success': False, 'error': '查询内容不能为空'}), 400
        
        results = search_similar_chunks(query, top_k=top_k, threshold=threshold,
                                         product_filter=product_filter, username=username)
        
        response = {'success': True, 'data': results, 'count': len(results)}
        
        if format_as_context:
            response['context'] = format_search_results_as_context(results)
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"[RAG API] 检索失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@rag_bp.route('/documents', methods=['GET'])
def list_documents():
    """列出所有 RAG 文档"""
    try:
        from .rag_service import list_rag_documents
        username = _get_username()
        docs = list_rag_documents(username=username)
        return jsonify({'success': True, 'data': docs})
    except Exception as e:
        logger.error(f"[RAG API] 列出文档失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@rag_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """删除指定文档（仅管理员）"""
    denied = _require_admin()
    if denied:
        return denied
    try:
        from .rag_service import delete_rag_document
        username = _get_username()
        success = delete_rag_document(doc_id, username=username)
        if success:
            return jsonify({'success': True, 'message': f'文档 {doc_id} 已删除'})
        else:
            return jsonify({'success': False, 'error': '文档不存在或无权限'}), 404
    except Exception as e:
        logger.error(f"[RAG API] 删除文档失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@rag_bp.route('/documents/<int:doc_id>/retry', methods=['POST'])
def retry_document(doc_id):
    """重新向量化指定文档（用于 error/pending 状态的文档重试）"""
    try:
        import psycopg2, psycopg2.extras
        from .rag_service import _get_pg_conn, embed_and_store_document

        username = _get_username()

        # 从 rag_documents 获取文件路径
        conn = _get_pg_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, filepath, filename, status FROM rag_documents WHERE id = %s", (doc_id,))
        doc = cur.fetchone()
        cur.close()
        conn.close()

        if not doc:
            return jsonify({'success': False, 'error': '文档不存在'}), 404

        filepath = doc.get('filepath')
        if not filepath or not os.path.isfile(filepath):
            return jsonify({'success': False, 'error': f'文件不存在: {filepath}'}), 400

        # 强制重新处理
        result = embed_and_store_document(filepath, force=True, username=username)

        if result.get('success'):
            return jsonify({
                'success': True,
                'message': f"向量化成功: {result.get('sections', 0)} 章节, {result.get('chunks', 0)} 检索块",
                'data': result
            })
        else:
            return jsonify({'success': False, 'error': result.get('message', '向量化失败')}), 500

    except Exception as e:
        logger.error(f"[RAG API] 重新向量化失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@rag_bp.route('/documents/<int:doc_id>/detail', methods=['GET'])
def get_document_detail(doc_id):
    """获取文档切分详情（章节 + chunks）"""
    try:
        import psycopg2, psycopg2.extras
        from .rag_service import ADMIN_USERNAME, _get_pg_conn
        
        username = _get_username()
        conn = _get_pg_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # 文档基本信息
        if username == ADMIN_USERNAME:
            cur.execute("SELECT * FROM rag_documents WHERE id = %s", (doc_id,))
        else:
            cur.execute(
                "SELECT * FROM rag_documents WHERE id = %s AND username = %s",
                (doc_id, username),
            )
        doc = cur.fetchone()
        if not doc:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'error': '文档不存在或无权限'}), 404
        
        # 所有章节
        cur.execute("""
            SELECT id, title, section_number, heading_level, full_path, 
                   content_length, chunk_count, section_order
            FROM rag_sections WHERE document_id = %s
            ORDER BY section_order
        """, (doc_id,))
        sections = cur.fetchall()
        
        # 每个章节的 chunks
        for sec in sections:
            cur.execute("""
                SELECT id, chunk_index, content, content_length
                FROM rag_chunks WHERE section_id = %s
                ORDER BY chunk_index
            """, (sec['id'],))
            sec['chunks'] = cur.fetchall()
        
        cur.close()
        conn.close()
        
        # 序列化 datetime
        for key in ['created_at', 'updated_at']:
            if doc.get(key):
                doc[key] = doc[key].isoformat()
        
        return jsonify({
            'success': True,
            'data': {
                'document': dict(doc),
                'sections': [dict(s) for s in sections]
            }
        })
    except Exception as e:
        logger.error(f"[RAG API] 获取文档详情失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@rag_bp.route('/stats', methods=['GET'])
def get_stats():
    """获取 RAG 系统统计"""
    try:
        from .rag_service import get_rag_stats
        username = _get_username()
        stats = get_rag_stats(username=username)
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        logger.error(f"[RAG API] 获取统计失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
