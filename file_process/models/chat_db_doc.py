"""
文档对话模块 - 支持精准匹配和LLM匹配
"""
import os
import re
import json
import tempfile
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, session, send_file
from config.db_config import fetch_one, fetch_all, dml_sql
from config.logging_config import logger

chatdoc = Blueprint('chatdoc', __name__)

# 获取基础目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def clean_text_for_fuzzy(text):
    """
    清理文本用于模糊匹配：去掉标点符号和特殊字符
    """
    if not text:
        return ""
    # 去掉所有标点符号和特殊字符，只保留中文、英文、数字
    cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
    return cleaned.lower()


def get_chapter_with_children(chapter_id, document_id):
    """
    获取章节及其所有子章节（递归）
    """
    result = []
    
    # 获取当前章节
    chapter_sql = """
        SELECT c.id, c.document_id, c.parent_id, c.level, c.order_index, 
               c.title, c.content, c.style_name, c.font_size, c.is_bold, c.paragraph_index
        FROM chapters c
        WHERE c.id = %s AND c.document_id = %s
    """
    chapter = fetch_one(chapter_sql, (chapter_id, document_id))
    if chapter:
        # 获取章节关联的图片
        images = get_chapter_images(chapter_id)
        chapter['images'] = images
        result.append(chapter)
        
        # 递归获取子章节
        children_sql = """
            SELECT id FROM chapters 
            WHERE parent_id = %s AND document_id = %s
            ORDER BY order_index
        """
        children = fetch_all(children_sql, (chapter_id, document_id))
        for child in children:
            result.extend(get_chapter_with_children(child['id'], document_id))
    
    return result


def get_chapter_path(chapter_id):
    """
    获取章节的完整层级路径（从根到当前章节）
    返回路径列表，每个元素包含 id, level, title
    """
    path = []
    current_id = chapter_id
    
    while current_id:
        sql = """
            SELECT id, parent_id, level, title
            FROM chapters
            WHERE id = %s
        """
        chapter = fetch_one(sql, (current_id,))
        if chapter:
            path.insert(0, {
                'id': chapter['id'],
                'level': chapter['level'],
                'title': chapter['title']
            })
            current_id = chapter['parent_id']
        else:
            break
    
    return path


def get_chapter_images(chapter_id):
    """
    获取章节关联的图片
    """
    sql = """
        SELECT di.id, di.image_name, di.image_path, di.image_url, di.image_type
        FROM document_images di
        INNER JOIN chapter_images ci ON di.id = ci.image_id
        WHERE ci.chapter_id = %s
        ORDER BY ci.position_in_chapter
    """
    return fetch_all(sql, (chapter_id,))


def search_chapters_exact(query, document_ids=None):
    """
    精确匹配搜索章节 - 只匹配 title 字段
    """
    if document_ids:
        placeholders = ','.join(['%s'] * len(document_ids))
        sql = f"""
            SELECT c.id, c.document_id, c.parent_id, c.level, c.order_index,
                   c.title, c.content, c.style_name, c.font_size, c.is_bold, c.paragraph_index,
                   dpr.filename as doc_filename
            FROM chapters c
            LEFT JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
            WHERE c.title = %s AND c.document_id IN ({placeholders})
            ORDER BY c.document_id, c.level, c.order_index
        """
        params = [query] + list(document_ids)
    else:
        sql = """
            SELECT c.id, c.document_id, c.parent_id, c.level, c.order_index,
                   c.title, c.content, c.style_name, c.font_size, c.is_bold, c.paragraph_index,
                   dpr.filename as doc_filename
            FROM chapters c
            LEFT JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
            WHERE c.title = %s
            ORDER BY c.document_id, c.level, c.order_index
        """
        params = [query]
    
    return fetch_all(sql, params)


def search_chapters_fuzzy(query, document_ids=None):
    """
    模糊匹配搜索章节 - 只匹配 title 字段
    去掉标点符号和特殊字符后进行匹配
    """
    cleaned_query = clean_text_for_fuzzy(query)
    if not cleaned_query:
        return []
    
    # 获取章节
    if document_ids:
        placeholders = ','.join(['%s'] * len(document_ids))
        sql = f"""
            SELECT c.id, c.document_id, c.parent_id, c.level, c.order_index,
                   c.title, c.content, c.style_name, c.font_size, c.is_bold, c.paragraph_index,
                   dpr.filename as doc_filename
            FROM chapters c
            LEFT JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
            WHERE c.document_id IN ({placeholders})
            ORDER BY c.document_id, c.level, c.order_index
        """
        chapters = fetch_all(sql, document_ids)
    else:
        sql = """
            SELECT c.id, c.document_id, c.parent_id, c.level, c.order_index,
                   c.title, c.content, c.style_name, c.font_size, c.is_bold, c.paragraph_index,
                   dpr.filename as doc_filename
            FROM chapters c
            LEFT JOIN doc_process_records dpr ON c.document_id = dpr.doc_id
            ORDER BY c.document_id, c.level, c.order_index
        """
        chapters = fetch_all(sql)
    
    # 只匹配 title
    results = []
    for chapter in chapters:
        cleaned_title = clean_text_for_fuzzy(chapter.get('title', ''))
        if cleaned_query in cleaned_title:
            results.append(chapter)
    
    return results


@chatdoc.route('/chatdoc', methods=['GET', 'POST'])
def chat_page():
    """渲染文档对话页面"""
    return render_template('chat_doc.html')


@chatdoc.route('/api/chat/documents', methods=['GET'])
def get_available_documents():
    """获取可用于查询的文档列表"""
    try:
        user_info = session.get('user')
        username = user_info.get('username') if user_info else 'anonymous'
        
        sql = """
            SELECT doc_id, filename, status, created_at
            FROM doc_process_records
            WHERE username = %s AND status = 'completed'
            ORDER BY created_at DESC
        """
        documents = fetch_all(sql, (username,))
        
        return jsonify({
            'success': True,
            'data': documents
        })
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/search', methods=['POST'])
def search_content():
    """
    搜索章节内容
    支持精确匹配和模糊匹配
    """
    try:
        data = request.json
        query = data.get('query', '').strip()
        match_type = data.get('match_type', 'exact')  # exact 或 fuzzy
        document_ids = data.get('document_ids', [])  # 可选，指定文档范围
        include_children = data.get('include_children', True)  # 是否包含子章节
        
        if not query:
            return jsonify({
                'success': False,
                'error': '查询内容不能为空'
            }), 400
        
        # 根据匹配类型搜索
        if match_type == 'exact':
            chapters = search_chapters_exact(query, document_ids if document_ids else None)
        else:
            chapters = search_chapters_fuzzy(query, document_ids if document_ids else None)
        
        if not chapters:
            return jsonify({
                'success': True,
                'data': {
                    'query': query,
                    'match_type': match_type,
                    'results': [],
                    'message': '未找到匹配的内容'
                }
            })
        
        # 按文档分组
        doc_results = {}
        for chapter in chapters:
            doc_id = chapter['document_id']
            if doc_id not in doc_results:
                doc_results[doc_id] = {
                    'document_id': doc_id,
                    'filename': chapter.get('doc_filename', '未知文档'),
                    'chapters': []
                }
            
            # 获取章节的层级路径
            chapter['path'] = get_chapter_path(chapter['id'])
            
            # 获取章节图片
            images = get_chapter_images(chapter['id'])
            chapter['images'] = images
            
            # 如果需要包含子章节
            if include_children:
                children = get_chapter_with_children(chapter['id'], doc_id)
                # 去掉第一个（当前章节本身，避免重复）
                if len(children) > 1:
                    chapter['children'] = children[1:]
            
            doc_results[doc_id]['chapters'].append(chapter)
        
        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'match_type': match_type,
                'results': list(doc_results.values()),
                'total_matches': len(chapters),
                'document_count': len(doc_results)
            }
        })
        
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/batch-search', methods=['POST'])
def batch_search():
    """
    批量搜索 - 支持多行查询
    每行一个查询条件
    """
    try:
        data = request.json
        queries = data.get('queries', [])  # 查询列表
        match_type = data.get('match_type', 'exact')
        document_ids = data.get('document_ids', [])
        include_children = data.get('include_children', True)
        
        if not queries:
            return jsonify({
                'success': False,
                'error': '查询内容不能为空'
            }), 400
        
        all_results = []
        
        for query in queries:
            query = query.strip()
            if not query:
                continue
            
            # 根据匹配类型搜索
            if match_type == 'exact':
                chapters = search_chapters_exact(query, document_ids if document_ids else None)
            else:
                chapters = search_chapters_fuzzy(query, document_ids if document_ids else None)
            
            # 按文档分组
            doc_results = {}
            for chapter in chapters:
                doc_id = chapter['document_id']
                if doc_id not in doc_results:
                    doc_results[doc_id] = {
                        'document_id': doc_id,
                        'filename': chapter.get('doc_filename', '未知文档'),
                        'chapters': []
                    }
                
                # 获取章节的层级路径
                chapter['path'] = get_chapter_path(chapter['id'])
                
                # 获取章节图片
                images = get_chapter_images(chapter['id'])
                chapter['images'] = images
                
                # 如果需要包含子章节
                if include_children:
                    children = get_chapter_with_children(chapter['id'], doc_id)
                    if len(children) > 1:
                        chapter['children'] = children[1:]
                
                doc_results[doc_id]['chapters'].append(chapter)
            
            all_results.append({
                'query': query,
                'results': list(doc_results.values()),
                'match_count': len(chapters)
            })
        
        return jsonify({
            'success': True,
            'data': {
                'match_type': match_type,
                'batch_results': all_results,
                'total_queries': len(queries)
            }
        })
        
    except Exception as e:
        logger.error(f"批量搜索失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/export-word', methods=['POST'])
def export_to_word():
    """
    导出搜索结果到Word文档
    """
    try:
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        data = request.json
        results = data.get('results', [])  # 搜索结果
        title = data.get('title', '文档查询结果')
        
        if not results:
            return jsonify({
                'success': False,
                'error': '没有可导出的内容'
            }), 400
        
        # 创建Word文档
        doc = Document()
        
        # 添加标题
        heading = doc.add_heading(title, 0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 添加生成时间
        doc.add_paragraph(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph()
        
        # 遍历结果
        query_index = 0
        for query_result in results:
            query = query_result.get('query', '')
            doc_results = query_result.get('results', [])
            query_index += 1
            
            # 添加用户输入作为标题（带序号）
            doc.add_heading(f"{query_index} 用户输入", level=1)
            # 添加用户输入的内容
            query_para = doc.add_paragraph(query)
            query_para.runs[0].bold = True
            doc.add_paragraph()  # 空行
            
            if not doc_results:
                doc.add_paragraph("未找到匹配结果")
                continue
            
            source_index = 0
            for doc_result in doc_results:
                filename = doc_result.get('filename', '未知文档')
                chapters = doc_result.get('chapters', [])
                source_index += 1
                
                # 添加来源（带序号，如 1.1 来源xxx）
                doc.add_heading(f"{query_index}.{source_index} 来源 {filename}", level=2)
                
                # 添加章节内容（带层级序号）
                chapter_counters = [0] * 10  # 支持最多10级
                for chapter in chapters:
                    add_chapter_to_doc_with_numbering(doc, chapter, level=3, 
                                                       prefix=f"{query_index}.{source_index}", 
                                                       counters=chapter_counters, 
                                                       depth=0)
        
        # 保存到临时文件
        temp_dir = tempfile.gettempdir()
        filename = f"查询结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        filepath = os.path.join(temp_dir, filename)
        doc.save(filepath)
        
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except ImportError:
        logger.error("python-docx 库未安装")
        return jsonify({
            'success': False,
            'error': '服务器缺少 python-docx 库，无法导出Word文档'
        }), 500
    except Exception as e:
        logger.error(f"导出Word失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def add_chapter_to_doc_with_numbering(doc, chapter, level=3, prefix="", counters=None, depth=0):
    """
    递归添加章节到Word文档，带层级序号（如 1.1.1, 1.1.2）
    
    Args:
        doc: Word文档对象
        chapter: 章节数据
        level: Word标题层级
        prefix: 序号前缀（如 "1.1"）
        counters: 各层级计数器列表
        depth: 当前递归深度
    """
    from docx.shared import Inches
    import re
    
    if counters is None:
        counters = [0] * 10
    
    title = chapter.get('title', '')
    content = chapter.get('content', '')
    images = chapter.get('images', [])
    children = chapter.get('children', [])
    
    # 增加当前层级计数
    counters[depth] += 1
    # 重置更深层级的计数
    for i in range(depth + 1, len(counters)):
        counters[i] = 0
    
    # 构建完整序号（如 1.1.1）
    number_parts = [str(counters[i]) for i in range(depth + 1)]
    full_number = f"{prefix}.{'.'.join(number_parts)}" if prefix else '.'.join(number_parts)
    
    # 添加章节标题（带序号）
    if title:
        heading_level = min(level, 9)
        doc.add_heading(f"{full_number} {title}", level=heading_level)
    
    # 添加内容（处理 [表格]...[/表格] 标签）
    if content:
        _add_content_with_tables(doc, content, images)
    else:
        # 没有内容时仍需添加图片
        for img in images:
            img_path = img.get('image_path', '')
            if img_path and os.path.exists(img_path):
                try:
                    doc.add_picture(img_path, width=Inches(5))
                except Exception as e:
                    logger.warning(f"添加图片失败: {img_path}, 错误: {e}")
    
    # 递归添加子章节
    for child in children:
        add_chapter_to_doc_with_numbering(doc, child, level=level + 1, 
                                          prefix=prefix, counters=counters, depth=depth + 1)


def add_chapter_to_doc(doc, chapter, level=3):
    """
    递归添加章节到Word文档（旧版本，保留兼容性）
    """
    from docx.shared import Inches
    import re
    
    title = chapter.get('title', '')
    content = chapter.get('content', '')
    images = chapter.get('images', [])
    children = chapter.get('children', [])
    
    # 添加章节标题
    if title:
        # 限制最大层级为9
        heading_level = min(level, 9)
        doc.add_heading(title, level=heading_level)
    
    # 添加内容（处理 [表格]...[/表格] 标签）
    if content:
        _add_content_with_tables(doc, content, images)
    else:
        # 没有内容时仍需添加图片
        for img in images:
            img_path = img.get('image_path', '')
            if img_path and os.path.exists(img_path):
                try:
                    doc.add_picture(img_path, width=Inches(5))
                except Exception as e:
                    logger.warning(f"添加图片失败: {img_path}, 错误: {e}")
    
    # 递归添加子章节
    for child in children:
        add_chapter_to_doc(doc, child, level=level + 1)


def _add_content_with_tables(doc, content, images):
    """
    将内容添加到 Word 文档，遇到 [表格]...[/表格] 就把里面的内容放进单行单列表格
    同时处理 {{IMAGE_ID_xxx}} 占位符替换为图片
    """
    from docx.shared import Inches, Pt
    from docx.oxml.ns import qn
    import re
    
    # 构建图片ID映射
    img_map = {}
    for img in images:
        img_id = img.get('id')
        if img_id:
            img_map[str(img_id)] = img.get('image_path', '')
    
    # 正则：匹配 [表格]...[/表格] 块
    table_pattern = re.compile(r'\[表格\](.*?)\[/表格\]', re.DOTALL)
    # 正则：匹配图片占位符
    image_pattern = re.compile(r'\{\{IMAGE_ID_(\d+)\}\}')
    
    last_end = 0
    for match in table_pattern.finditer(content):
        # 添加表格之前的普通文本
        before_text = content[last_end:match.start()]
        if before_text.strip():
            _add_text_with_images(doc, before_text, img_map, image_pattern)
        
        # 表格内容
        table_content = match.group(1).strip()
        if table_content:
            # 创建单行单列表格
            table = doc.add_table(rows=1, cols=1)
            table.style = 'Table Grid'
            cell = table.cell(0, 0)
            # 把表格内容（可能含图片占位符）写入单元格
            _add_cell_content_with_images(cell, table_content, img_map, image_pattern)
        
        last_end = match.end()
    
    # 添加最后剩余的普通文本
    remaining = content[last_end:]
    if remaining.strip():
        _add_text_with_images(doc, remaining, img_map, image_pattern)


def _add_text_with_images(doc, text, img_map, image_pattern):
    """
    将文本添加到文档，遇到 {{IMAGE_ID_xxx}} 替换为图片
    """
    from docx.shared import Inches
    
    last_end = 0
    for match in image_pattern.finditer(text):
        # 图片之前的文字
        before = text[last_end:match.start()]
        if before.strip():
            doc.add_paragraph(before.strip())
        
        # 插入图片
        img_id = match.group(1)
        img_path = img_map.get(img_id, '')
        if img_path and os.path.exists(img_path):
            try:
                doc.add_picture(img_path, width=Inches(5))
            except Exception as e:
                logger.warning(f"添加图片失败: {img_path}, 错误: {e}")
        
        last_end = match.end()
    
    # 剩余文字
    remaining = text[last_end:]
    if remaining.strip():
        doc.add_paragraph(remaining.strip())


def _add_cell_content_with_images(cell, text, img_map, image_pattern):
    """
    将文本添加到表格单元格，遇到 {{IMAGE_ID_xxx}} 替换为图片
    """
    from docx.shared import Inches
    
    # 清空单元格默认段落
    cell.text = ''
    
    last_end = 0
    for match in image_pattern.finditer(text):
        # 图片之前的文字
        before = text[last_end:match.start()]
        if before.strip():
            p = cell.add_paragraph(before.strip())
        
        # 插入图片到单元格
        img_id = match.group(1)
        img_path = img_map.get(img_id, '')
        if img_path and os.path.exists(img_path):
            try:
                p = cell.add_paragraph()
                run = p.add_run()
                run.add_picture(img_path, width=Inches(4.5))
            except Exception as e:
                logger.warning(f"添加图片到表格失败: {img_path}, 错误: {e}")
        
        last_end = match.end()
    
    # 剩余文字
    remaining = text[last_end:]
    if remaining.strip():
        cell.add_paragraph(remaining.strip())



@chatdoc.route('/api/chat/upload-txt', methods=['POST'])
def upload_txt_for_search():
    """
    上传TXT文件进行批量查询
    每行一个查询条件
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': '未上传文件'
            }), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '未选择文件'
            }), 400
        
        if not file.filename.endswith('.txt'):
            return jsonify({
                'success': False,
                'error': '只支持TXT文件'
            }), 400
        
        # 读取文件内容
        content = file.read().decode('utf-8')
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        if not lines:
            return jsonify({
                'success': False,
                'error': '文件内容为空'
            }), 400
        
        return jsonify({
            'success': True,
            'data': {
                'queries': lines,
                'count': len(lines)
            }
        })
        
    except Exception as e:
        logger.error(f"上传TXT文件失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@chatdoc.route('/api/chat/select-document', methods=['POST'])
def select_document_for_conflict():
    """
    当多个文档都匹配时，用户选择使用哪个文档的结果
    """
    try:
        data = request.json
        selected_doc_id = data.get('document_id')
        query = data.get('query')
        match_type = data.get('match_type', 'exact')
        include_children = data.get('include_children', True)
        
        if not selected_doc_id or not query:
            return jsonify({
                'success': False,
                'error': '参数不完整'
            }), 400
        
        # 只在选定的文档中搜索
        if match_type == 'exact':
            chapters = search_chapters_exact(query, [selected_doc_id])
        else:
            chapters = search_chapters_fuzzy(query, [selected_doc_id])
        
        results = []
        for chapter in chapters:
            # 获取章节的层级路径
            chapter['path'] = get_chapter_path(chapter['id'])
            
            images = get_chapter_images(chapter['id'])
            chapter['images'] = images
            
            if include_children:
                children = get_chapter_with_children(chapter['id'], selected_doc_id)
                if len(children) > 1:
                    chapter['children'] = children[1:]
            
            results.append(chapter)
        
        return jsonify({
            'success': True,
            'data': {
                'query': query,
                'document_id': selected_doc_id,
                'chapters': results
            }
        })
        
    except Exception as e:
        logger.error(f"选择文档失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============== LLM 匹配相关（待实现）==============

@chatdoc.route('/api/chat/llm-search', methods=['POST'])
def llm_search():
    """
    LLM智能匹配搜索（待实现）
    
    实现思路：
    1. 将用户查询发送给大模型（如 GPT、Claude、文心一言等）
    2. 大模型理解用户意图，生成结构化的查询条件
    3. 使用生成的条件在数据库中搜索
    4. 或者使用 RAG（检索增强生成）：
       - 将章节内容向量化存储
       - 用户查询时，先检索相似的章节
       - 将检索结果作为上下文发送给大模型
       - 大模型生成最终回答
    
    需要的配置：
    - LLM API 密钥（OpenAI、Azure、百度等）
    - 向量数据库（如 Milvus、Pinecone、Chroma）用于 RAG
    - Embedding 模型用于文本向量化
    """
    return jsonify({
        'success': False,
        'error': 'LLM匹配功能正在开发中',
        'message': '''
LLM匹配功能实现思路：

1. **基础方案 - 直接调用LLM**：
   - 将用户问题和相关章节内容发送给大模型
   - 大模型理解语义后返回匹配结果
   - 优点：实现简单
   - 缺点：每次查询都需要发送大量文本，成本高

2. **进阶方案 - RAG（检索增强生成）**：
   - 预处理：将所有章节内容通过 Embedding 模型转换为向量
   - 存储：将向量存入向量数据库（Milvus/Pinecone/Chroma）
   - 查询：用户问题也转换为向量，在向量库中检索相似内容
   - 生成：将检索到的内容作为上下文，让LLM生成回答
   - 优点：查询速度快，成本低，效果好
   - 缺点：需要额外的向量数据库

3. **推荐的技术栈**：
   - LLM: OpenAI GPT-4 / Claude / 文心一言 / 通义千问
   - Embedding: OpenAI text-embedding-ada-002 / BGE / M3E
   - 向量数据库: Milvus / Chroma / FAISS
   - 框架: LangChain / LlamaIndex

4. **实现步骤**：
   a. 配置LLM API密钥
   b. 安装必要的库（openai, langchain, chromadb等）
   c. 创建向量索引（首次运行时）
   d. 实现查询接口
   e. 实现结果展示
        '''
    }), 501
