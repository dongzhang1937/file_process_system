"""
LLM功能路由模块
提供LLM配置管理、文档问答等API接口
"""
import json
from flask import Blueprint, request, jsonify, session, render_template, Response
from config.logging_config import logger
from .llm_config import LLMConfigManager, WebSearchConfigManager
from .llm_service import get_llm_service
from .document_qa import get_document_qa_service

# 创建蓝图
llm_bp = Blueprint('llm', __name__, url_prefix='/llm')


# ==================== 页面路由 ====================

@llm_bp.route('/')
def llm_main_page():
    """LLM主页面"""
    return render_template('llm_main.html')


# ==================== LLM配置管理API ====================

@llm_bp.route('/config', methods=['GET'])
def list_llm_configs():
    """获取所有LLM配置"""
    try:
        configs = LLMConfigManager.list_configs()
        # 隐藏敏感信息
        for config in configs:
            if config.get('api_key'):
                config['api_key'] = config['api_key'][:8] + '****'
        
        return jsonify({
            'success': True,
            'data': configs
        })
    except Exception as e:
        logger.error(f"获取LLM配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/config', methods=['POST'])
def create_llm_config():
    """创建LLM配置"""
    try:
        data = request.get_json()
        
        required_fields = ['config_name', 'model_type', 'api_key', 'model_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        config_id = LLMConfigManager.create_config(
            config_name=data['config_name'],
            model_type=data['model_type'],
            api_key=data['api_key'],
            model_name=data['model_name'],
            api_base_url=data.get('api_base_url'),
            max_tokens=data.get('max_tokens', 2048),
            temperature=data.get('temperature', 0.7),
            is_default=data.get('is_default', False),
            extra_params=data.get('extra_params')
        )
        
        return jsonify({
            'success': True,
            'data': {'id': config_id},
            'message': '配置创建成功'
        })
    except Exception as e:
        logger.error(f"创建LLM配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/config/<int:config_id>', methods=['PUT'])
def update_llm_config(config_id):
    """更新LLM配置"""
    try:
        data = request.get_json()
        
        success = LLMConfigManager.update_config(config_id, **data)
        
        if success:
            return jsonify({'success': True, 'message': '配置更新成功'})
        else:
            return jsonify({'success': False, 'error': '更新失败'}), 400
    except Exception as e:
        logger.error(f"更新LLM配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/config/<int:config_id>', methods=['DELETE'])
def delete_llm_config(config_id):
    """删除LLM配置"""
    try:
        success = LLMConfigManager.delete_config(config_id)
        
        if success:
            return jsonify({'success': True, 'message': '配置删除成功'})
        else:
            return jsonify({'success': False, 'error': '删除失败'}), 400
    except Exception as e:
        logger.error(f"删除LLM配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/config/models', methods=['GET'])
def get_supported_models():
    """获取支持的模型列表"""
    return jsonify({
        'success': True,
        'data': LLMConfigManager.get_supported_models()
    })


# ==================== 网络搜索配置API ====================

@llm_bp.route('/search-config', methods=['GET'])
def list_search_configs():
    """获取网络搜索配置"""
    try:
        configs = WebSearchConfigManager.list_configs()
        for config in configs:
            if config.get('api_key'):
                config['api_key'] = config['api_key'][:8] + '****'
        
        return jsonify({
            'success': True,
            'data': configs
        })
    except Exception as e:
        logger.error(f"获取搜索配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/search-config', methods=['POST'])
def create_search_config():
    """创建网络搜索配置"""
    try:
        data = request.get_json()
        
        config_id = WebSearchConfigManager.create_config(
            search_engine=data['search_engine'],
            api_key=data['api_key'],
            api_url=data.get('api_url'),
            extra_params=data.get('extra_params'),
            is_default=data.get('is_default', False)
        )
        
        return jsonify({
            'success': True,
            'data': {'id': config_id},
            'message': '搜索配置创建成功'
        })
    except Exception as e:
        logger.error(f"创建搜索配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== 文档问答API ====================

@llm_bp.route('/sessions', methods=['GET'])
def list_sessions():
    """获取用户的问答会话列表"""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('id') or user_info.get('username', 'anonymous')
        
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        qa_service = get_document_qa_service()
        sessions = qa_service.list_sessions(user_id, limit, offset)
        
        return jsonify({
            'success': True,
            'data': sessions
        })
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sessions', methods=['POST'])
def create_session():
    """创建新的问答会话"""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('id') or user_info.get('username', 'anonymous')
        
        data = request.get_json() or {}
        title = data.get('title')
        
        qa_service = get_document_qa_service()
        session_id = qa_service.create_session(user_id, title)
        
        return jsonify({
            'success': True,
            'data': {'session_id': session_id},
            'message': '会话创建成功'
        })
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除问答会话"""
    try:
        qa_service = get_document_qa_service()
        qa_service.delete_session(session_id)
        
        return jsonify({
            'success': True,
            'message': '会话删除成功'
        })
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sessions/<int:session_id>/history', methods=['GET'])
def get_session_history(session_id):
    """获取会话的问答历史"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        qa_service = get_document_qa_service()
        history = qa_service.get_qa_history(session_id, limit, offset)
        
        return jsonify({
            'success': True,
            'data': history
        })
    except Exception as e:
        logger.error(f"获取问答历史失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/qa', methods=['POST'])
def ask_question():
    """提问接口"""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('id') or user_info.get('username', 'anonymous')
        
        data = request.get_json()
        
        if not data.get('question'):
            return jsonify({'success': False, 'error': '问题不能为空'}), 400
        
        session_id = data.get('session_id')
        question = data['question']
        document_ids = data.get('document_ids')
        enable_web_search = data.get('enable_web_search', True)
        custom_search_urls = data.get('custom_search_urls')
        llm_config_id = data.get('llm_config_id')
        stream = data.get('stream', False)
        
        # 如果没有会话ID，创建新会话
        qa_service = get_document_qa_service(llm_config_id)
        if not session_id:
            session_id = qa_service.create_session(user_id, question[:50])
        
        if stream:
            # 流式响应
            def generate():
                for chunk in qa_service.process_question(
                    session_id=session_id,
                    question=question,
                    user_id=user_id,
                    document_ids=document_ids,
                    enable_web_search=enable_web_search,
                    custom_search_urls=custom_search_urls,
                    stream=True
                ):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            
            return Response(generate(), mimetype='text/event-stream')
        else:
            # 非流式响应
            result = qa_service.process_question(
                session_id=session_id,
                question=question,
                user_id=user_id,
                document_ids=document_ids,
                enable_web_search=enable_web_search,
                custom_search_urls=custom_search_urls,
                stream=False
            )
            
            return jsonify({
                'success': True,
                'data': {
                    'session_id': session_id,
                    'answer': result['answer'],
                    'source_type': result['source_type'],
                    'sources': result['sources']
                }
            })
    except Exception as e:
        logger.error(f"问答处理失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/test', methods=['POST'])
def test_llm_config():
    """测试LLM配置是否可用"""
    try:
        data = request.get_json()
        config_id = data.get('config_id')
        
        llm_service = get_llm_service(config_id)
        
        # 发送测试消息
        result = llm_service.chat_completion([
            {'role': 'user', 'content': '你好，请回复"测试成功"'}
        ])
        
        return jsonify({
            'success': True,
            'data': {
                'response': result['content'],
                'usage': result.get('usage', {})
            },
            'message': 'LLM配置测试成功'
        })
    except Exception as e:
        logger.error(f"LLM配置测试失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
