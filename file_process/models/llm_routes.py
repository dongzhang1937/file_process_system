"""
LLM功能路由模块
提供LLM配置管理等API接口
"""
from flask import Blueprint, request, jsonify, session
from config.logging_config import logger
from .llm_config import LLMConfigManager, WebSearchConfigManager
from .llm_service import get_llm_service

# 创建蓝图
llm_bp = Blueprint('llm', __name__, url_prefix='/llm')


def _get_username():
    """从 session 获取当前用户名"""
    return session.get('user', {}).get('username', 'anonymous')


# ==================== LLM配置管理API ====================

@llm_bp.route('/config', methods=['GET'])
def list_llm_configs():
    """获取所有LLM配置"""
    try:
        username = _get_username()
        configs = LLMConfigManager.list_configs(username=username)
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
        username = _get_username()
        
        required_fields = ['config_name', 'model_type', 'model_name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        # Ollama 本地部署无需 API Key，其他类型必填
        if data['model_type'] != 'ollama' and not data.get('api_key'):
            return jsonify({'success': False, 'error': '缺少必填字段: api_key'}), 400
        
        config_id = LLMConfigManager.create_config(
            config_name=data['config_name'],
            model_type=data['model_type'],
            api_key=data['api_key'],
            model_name=data['model_name'],
            api_base_url=data.get('api_base_url'),
            max_tokens=data.get('max_tokens', 2048),
            temperature=data.get('temperature', 0.7),
            is_default=data.get('is_default', False),
            extra_params=data.get('extra_params'),
            username=username
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
        username = _get_username()
        
        success = LLMConfigManager.update_config(config_id, username=username, **data)
        
        if success:
            return jsonify({'success': True, 'message': '配置更新成功'})
        else:
            return jsonify({'success': False, 'error': '更新失败'}), 400
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error(f"更新LLM配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/config/<int:config_id>', methods=['DELETE'])
def delete_llm_config(config_id):
    """删除LLM配置"""
    try:
        username = _get_username()
        success = LLMConfigManager.delete_config(config_id, username=username)
        
        if success:
            return jsonify({'success': True, 'message': '配置删除成功'})
        else:
            return jsonify({'success': False, 'error': '删除失败'}), 400
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
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
        username = _get_username()
        configs = WebSearchConfigManager.list_configs(username=username)
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
        username = _get_username()
        
        # DuckDuckGo 不需要 api_key
        api_key = data.get('api_key', '')
        
        config_id = WebSearchConfigManager.create_config(
            search_engine=data['search_engine'],
            api_key=api_key,
            api_url=data.get('api_url'),
            extra_params=data.get('extra_params'),
            is_default=data.get('is_default', False),
            username=username
        )
        
        return jsonify({
            'success': True,
            'data': {'id': config_id},
            'message': '搜索配置创建成功'
        })
    except Exception as e:
        logger.error(f"创建搜索配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/search-config/<int:config_id>', methods=['PUT'])
def update_search_config(config_id):
    """更新网络搜索配置"""
    try:
        data = request.get_json()
        username = _get_username()
        
        success = WebSearchConfigManager.update_config(config_id, username=username, **data)
        
        if success:
            return jsonify({'success': True, 'message': '配置更新成功'})
        else:
            return jsonify({'success': False, 'error': '更新失败'}), 400
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error(f"更新搜索配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/search-config/<int:config_id>', methods=['DELETE'])
def delete_search_config(config_id):
    """删除网络搜索配置"""
    try:
        username = _get_username()
        success = WebSearchConfigManager.delete_config(config_id, username=username)
        
        if success:
            return jsonify({'success': True, 'message': '配置删除成功'})
        else:
            return jsonify({'success': False, 'error': '删除失败'}), 400
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error(f"删除搜索配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/test', methods=['POST'])
def test_llm_config():
    """测试LLM配置是否可用
    
    支持两种方式:
    1. 传入 config_id 测试已保存的配置
    2. 直接传入配置参数进行测试（用于保存前测试）
    """
    try:
        data = request.get_json()
        config_id = data.get('config_id')
        
        # 如果传入了直接配置参数，使用临时配置测试
        # Ollama 无需 api_key，其他类型需要
        if data.get('model_type') and (data.get('api_key') or data.get('model_type') == 'ollama'):
            # 直接使用传入的配置参数测试
            from .llm_service import LLMService
            
            temp_config = {
                'model_type': data['model_type'],
                'model_name': data.get('model_name', 'gpt-3.5-turbo'),
                'api_key': data.get('api_key', ''),
                'api_base_url': data.get('api_base_url'),
                'max_tokens': data.get('max_tokens', 2048),
                'temperature': data.get('temperature', 0.7)
            }
            
            llm_service = LLMService(temp_config)
        elif config_id:
            # 使用已保存的配置
            llm_service = get_llm_service(config_id)
        else:
            return jsonify({'success': False, 'error': '请提供配置ID或配置参数'}), 400
        
        # 发送测试消息
        # 智谱视觉模型（glm-4v系列）必须传图片，纯文本会报"参数有误"
        # 测试时临时切换到对应的文本模型验证API Key
        test_config = llm_service.config
        model_name = test_config.get('model_name', '')
        model_type = test_config.get('model_type', '')
        
        if model_type == 'zhipu' and any(k in model_name for k in ['4v', '6v', 'v-flash', 'v-plus', 'vision']):
            # 视觉模型 -> 用 glm-4-flash（免费）测试连接
            logger.info(f"[测试] 智谱视觉模型 {model_name} 不支持纯文本测试，临时使用 glm-4-flash 验证")
            test_messages = [{'role': 'user', 'content': '你好，请回复"测试成功"'}]
            result = llm_service.chat_completion(test_messages, model='glm-4-flash')
        else:
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


# ==================== Skills(Prompt模板) 配置管理API ====================

@llm_bp.route('/skills-config', methods=['GET'])
def list_skills_configs():
    """获取Prompt模板配置列表"""
    try:
        from .mcp_skills_config import SkillsConfigManager
        scene_type = request.args.get('scene_type')
        configs = SkillsConfigManager.list_configs(scene_type)
        return jsonify({'success': True, 'data': configs})
    except Exception as e:
        logger.error(f"获取Skills配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/skills-config/scene-types', methods=['GET'])
def get_skills_scene_types():
    """获取支持的场景类型列表"""
    try:
        from .mcp_skills_config import SkillsConfigManager
        return jsonify({
            'success': True,
            'data': SkillsConfigManager.get_scene_types()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/skills-config', methods=['POST'])
def create_skills_config():
    """创建Prompt模板"""
    try:
        from .mcp_skills_config import SkillsConfigManager
        data = request.get_json()

        required = ['name', 'scene_type', 'system_prompt']
        for field in required:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400

        config_id = SkillsConfigManager.create_config(
            name=data['name'],
            scene_type=data['scene_type'],
            system_prompt=data['system_prompt'],
            variables_json=data.get('variables_json'),
            is_default=data.get('is_default', False)
        )

        return jsonify({
            'success': True,
            'data': {'id': config_id},
            'message': 'Prompt模板创建成功'
        })
    except Exception as e:
        logger.error(f"创建Skills配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/skills-config/<int:config_id>', methods=['PUT'])
def update_skills_config(config_id):
    """更新Prompt模板"""
    try:
        from .mcp_skills_config import SkillsConfigManager
        data = request.get_json()
        success = SkillsConfigManager.update_config(config_id, **data)

        if success:
            return jsonify({'success': True, 'message': '模板更新成功'})
        else:
            return jsonify({'success': False, 'error': '更新失败'}), 400
    except Exception as e:
        logger.error(f"更新Skills配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/skills-config/<int:config_id>', methods=['DELETE'])
def delete_skills_config(config_id):
    """删除Prompt模板"""
    try:
        from .mcp_skills_config import SkillsConfigManager
        success = SkillsConfigManager.delete_config(config_id)

        if success:
            return jsonify({'success': True, 'message': '模板删除成功'})
        else:
            return jsonify({'success': False, 'error': '删除失败'}), 400
    except Exception as e:
        logger.error(f"删除Skills配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== SQL 数据库连接配置API ====================

@llm_bp.route('/sql-db-config', methods=['GET'])
def list_sql_db_configs():
    """获取所有SQL数据库连接配置"""
    try:
        from .mcp_skills_config import SQLDBConfigManager
        username = _get_username()
        configs = SQLDBConfigManager.list_configs(owner_username=username)

        # 密码脱敏
        for config in configs:
            if config.get('password'):
                config['password'] = SQLDBConfigManager.mask_password(config['password'])

        return jsonify({
            'success': True,
            'data': configs,
            'db_types': SQLDBConfigManager.get_db_types()
        })
    except Exception as e:
        logger.error(f"获取SQL数据库配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sql-db-config', methods=['POST'])
def save_sql_db_config():
    """保存SQL数据库连接配置（按db_type自动创建或更新）"""
    try:
        from .mcp_skills_config import SQLDBConfigManager
        data = request.get_json()
        username = _get_username()

        db_type = data.get('db_type')
        if not db_type:
            return jsonify({'success': False, 'error': '缺少必填字段: db_type'}), 400

        if db_type not in SQLDBConfigManager.DB_TYPES:
            return jsonify({'success': False, 'error': f'不支持的数据库类型: {db_type}'}), 400

        # 使用 upsert 模式
        result = SQLDBConfigManager.upsert_config(
            db_type=db_type,
            owner_username=username,
            host=data.get('host', ''),
            port=int(data.get('port', 0)),
            username=data.get('username', ''),
            password=data.get('password', ''),
            database_name=data.get('database_name', ''),
            name=data.get('name', ''),
            use_independent=data.get('use_independent', False)
        )

        return jsonify({
            'success': True,
            'message': f'{db_type} 配置保存成功'
        })
    except Exception as e:
        logger.error(f"保存SQL数据库配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sql-db-config/<int:config_id>', methods=['PUT'])
def update_sql_db_config(config_id):
    """更新SQL数据库连接配置"""
    try:
        from .mcp_skills_config import SQLDBConfigManager
        data = request.get_json()
        username = _get_username()
        success = SQLDBConfigManager.update_config(config_id, owner_username=username, **data)

        if success:
            return jsonify({'success': True, 'message': '配置更新成功'})
        else:
            return jsonify({'success': False, 'error': '更新失败'}), 400
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error(f"更新SQL数据库配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sql-db-config/<int:config_id>', methods=['DELETE'])
def delete_sql_db_config(config_id):
    """删除SQL数据库连接配置"""
    try:
        from .mcp_skills_config import SQLDBConfigManager
        username = _get_username()
        success = SQLDBConfigManager.delete_config(config_id, owner_username=username)

        if success:
            return jsonify({'success': True, 'message': '配置删除成功'})
        else:
            return jsonify({'success': False, 'error': '删除失败'}), 400
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error(f"删除SQL数据库配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@llm_bp.route('/sql-db-config/test', methods=['POST'])
def test_sql_db_connection():
    """测试SQL数据库连接"""
    try:
        from .mcp_skills_config import SQLDBConfigManager
        data = request.get_json()

        db_type = data.get('db_type')
        config_id = data.get('config_id')

        if config_id:
            result = SQLDBConfigManager.test_connection(config_id=config_id)
        elif db_type:
            result = SQLDBConfigManager.test_connection(
                db_type=db_type,
                host=data.get('host'),
                port=int(data.get('port', 0)) if data.get('port') else None,
                username=data.get('username'),
                password=data.get('password'),
                database_name=data.get('database_name')
            )
        else:
            return jsonify({'success': False, 'error': '请提供 db_type 或 config_id'}), 400

        return jsonify(result)

    except Exception as e:
        logger.error(f"测试SQL数据库连接失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@llm_bp.route('/sql-db-config/db-types', methods=['GET'])
def get_sql_db_types():
    """获取支持的SQL数据库类型列表"""
    try:
        from .mcp_skills_config import SQLDBConfigManager
        return jsonify({
            'success': True,
            'data': SQLDBConfigManager.get_db_types()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
