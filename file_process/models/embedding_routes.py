"""
Embedding 配置管理 API 路由
提供 Embedding 模型配置的增删改查和测试功能
"""
from flask import Blueprint, request, jsonify, session
from config.logging_config import logger
from .embedding_service import EmbeddingConfigManager, EmbeddingService

# 创建蓝图
embedding_bp = Blueprint('embedding', __name__, url_prefix='/api/embedding')


def _get_username():
    """从 session 获取当前用户名"""
    return session.get('user', {}).get('username', 'anonymous')


# ==================== Embedding配置管理API ====================

@embedding_bp.route('/providers', methods=['GET'])
def get_supported_providers():
    """获取支持的 Embedding 提供商列表"""
    try:
        providers = EmbeddingConfigManager.get_supported_providers()
        return jsonify({
            'success': True,
            'data': providers
        })
    except Exception as e:
        logger.error(f"获取提供商列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/config', methods=['GET'])
def list_configs():
    """获取所有 Embedding 配置 + 当前用户选中的 config_id"""
    try:
        username = _get_username()
        configs = EmbeddingConfigManager.get_all_configs(username=username)
        
        for config in configs:
            if config.get('created_at'):
                config['created_at'] = config['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        from .user_selection import get_effective_config_id
        selected_id = get_effective_config_id(username, 'embedding')
        if selected_id is None:
            for c in configs:
                if c.get('is_default'):
                    selected_id = c['id']
                    break
        
        return jsonify({
            'success': True,
            'data': configs,
            'selected_id': selected_id
        })
    except Exception as e:
        logger.error(f"获取配置列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/config/<int:config_id>', methods=['GET'])
def get_config(config_id):
    """获取指定配置详情"""
    try:
        config = EmbeddingConfigManager.get_config(config_id)
        if not config:
            return jsonify({
                'success': False,
                'error': '配置不存在'
            }), 404
        
        # 隐藏敏感信息
        if config.get('api_key'):
            config['api_key'] = '******'
        
        return jsonify({
            'success': True,
            'data': config
        })
    except Exception as e:
        logger.error(f"获取配置详情失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/config', methods=['POST'])
def create_config():
    """创建新的 Embedding 配置"""
    try:
        data = request.json
        username = _get_username()
        
        # 验证必要字段
        required_fields = ['name', 'provider', 'model_name', 'dimensions']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'缺少必要字段: {field}'
                }), 400
        
        # 创建配置
        config_id = EmbeddingConfigManager.create_config(
            name=data['name'],
            provider=data['provider'],
            model_name=data['model_name'],
            dimensions=int(data['dimensions']),
            api_key=data.get('api_key'),
            api_base=data.get('api_base'),
            is_default=data.get('is_default', False),
            extra_config=data.get('extra_config'),
            username=username
        )
        
        if config_id:
            # 自动选中新创建的配置
            from .user_selection import select_config as do_select
            do_select(username, 'embedding', config_id)
            logger.info(f"创建 Embedding 配置成功: id={config_id}, name={data['name']}")
            return jsonify({
                'success': True,
                'data': {'id': config_id},
                'message': '配置创建成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '创建配置失败'
            }), 500
            
    except Exception as e:
        logger.error(f"创建配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/config/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    """更新 Embedding 配置"""
    try:
        data = request.json
        username = _get_username()
        
        # 构建更新参数
        update_params = {}
        
        if 'name' in data:
            update_params['name'] = data['name']
        if 'provider' in data:
            update_params['provider'] = data['provider']
        if 'model_name' in data:
            update_params['model_name'] = data['model_name']
        if 'dimensions' in data:
            update_params['dimensions'] = int(data['dimensions'])
        if 'api_key' in data and data['api_key']:
            update_params['api_key'] = data['api_key']
        if 'api_base' in data:
            update_params['api_base'] = data['api_base']
        if 'is_default' in data:
            update_params['is_default'] = data['is_default']
        if 'is_active' in data:
            update_params['is_active'] = data['is_active']
        if 'extra_config' in data:
            update_params['extra_config'] = data['extra_config']
        
        success = EmbeddingConfigManager.update_config(config_id, username=username, **update_params)
        
        if success:
            logger.info(f"更新 Embedding 配置成功: id={config_id}")
            return jsonify({
                'success': True,
                'message': '配置更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '更新配置失败或配置不存在'
            }), 404
            
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/config/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    """删除 Embedding 配置"""
    try:
        username = _get_username()
        success = EmbeddingConfigManager.delete_config(config_id, username=username)
        
        if success:
            logger.info(f"删除 Embedding 配置成功: id={config_id}")
            return jsonify({
                'success': True,
                'message': '配置删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '删除配置失败或配置不存在'
            }), 404
            
    except PermissionError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except Exception as e:
        logger.error(f"删除配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/config/<int:config_id>/default', methods=['POST'])
def set_default_config(config_id):
    """设置默认配置"""
    try:
        username = _get_username()
        success = EmbeddingConfigManager.set_default(config_id, username=username)
        
        if success:
            logger.info(f"设置默认 Embedding 配置成功: id={config_id}")
            return jsonify({
                'success': True,
                'message': '已设为默认配置'
            })
        else:
            return jsonify({
                'success': False,
                'error': '设置失败或配置不存在'
            }), 404
            
    except Exception as e:
        logger.error(f"设置默认配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/test', methods=['POST'])
def test_config():
    """测试 Embedding 配置"""
    try:
        data = request.json
        config_id = data.get('config_id')
        config_data = data.get('config_data')
        
        # 调用测试方法
        result = EmbeddingConfigManager.test_config(
            config_id=config_id,
            config_data=config_data
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'data': result,
                'message': result.get('message', '测试成功')
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('message', '测试失败')
            }), 400
            
    except Exception as e:
        logger.error(f"测试配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@embedding_bp.route('/status', methods=['GET'])
def get_embedding_status():
    """获取当前 Embedding 服务状态"""
    try:
        # 尝试获取当前用户选中的配置
        username = _get_username()
        default_config = EmbeddingConfigManager.get_default_config(username=username)
        
        if default_config:
            # 隐藏敏感信息
            safe_config = {
                'id': default_config.get('id'),
                'name': default_config.get('name'),
                'provider': default_config.get('provider'),
                'model_name': default_config.get('model_name'),
                'dimensions': default_config.get('dimensions'),
                'is_active': default_config.get('is_active')
            }
            
            return jsonify({
                'success': True,
                'data': {
                    'configured': True,
                    'default_config': safe_config,
                    'message': f"已配置 {safe_config['provider']} - {safe_config['model_name']}"
                }
            })
        else:
            return jsonify({
                'success': True,
                'data': {
                    'configured': False,
                    'default_config': None,
                    'message': '未配置 Embedding 服务，将使用简单词向量方案'
                }
            })
            
    except Exception as e:
        logger.error(f"获取 Embedding 状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
