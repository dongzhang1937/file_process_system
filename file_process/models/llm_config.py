"""
LLM配置管理模块
支持多种大模型：OpenAI、通义千问、文心一言、智谱GLM等
"""
import json
from datetime import datetime
from config.db_config import dml_sql, query_sql, fetch_one, dml_sql_with_insert_id

# 管理员用户名常量
ADMIN_USERNAME = 'asd'


class LLMConfigManager:
    """LLM配置管理器"""
    
    # 支持的模型类型
    SUPPORTED_MODELS = {
        'openai': {
            'name': 'OpenAI',
            'default_base_url': 'https://api.openai.com/v1',
            'models': ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo', 'gpt-4o', 'gpt-4o-mini']
        },
        'gemini': {
            'name': 'Google Gemini',
            'default_base_url': 'https://generativelanguage.googleapis.com/v1beta',
            'models': [
                # Gemini 3 系列 - 最新最强
                'gemini-3-pro-preview',         # 最先进的多模态理解模型
                'gemini-3-flash-preview',       # 平衡速度与智能
                # Gemini 2.5 系列 - 稳定版
                'gemini-2.5-pro',               # 高级思考模型，擅长代码/数学/推理
                'gemini-2.5-flash',             # 性价比最高，适合大规模处理
                'gemini-2.5-flash-lite',        # 最快的 Flash 模型，成本优化
                # Gemini 2.0 系列 - 将于2026年3月31日关闭
                'gemini-2.0-flash',             # 2.0 快速模型（已弃用）
                'gemini-2.0-flash-lite'         # 2.0 轻量模型（已弃用）
            ],
            'supports_pdf': True  # 支持直接上传PDF
        },
        'qianwen': {
            'name': '通义千问',
            'default_base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'models': ['qwen-turbo', 'qwen-plus', 'qwen-max', 'qwen-long']
        },
        'wenxin': {
            'name': '文心一言',
            'default_base_url': 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat',
            'models': ['ernie-bot-4', 'ernie-bot-turbo', 'ernie-bot']
        },
        'zhipu': {
            'name': '智谱GLM',
            'default_base_url': 'https://open.bigmodel.cn/api/paas/v4',
            'models': ['glm-4', 'glm-4-flash', 'glm-4v-flash', 'glm-4.6v-flash', 'glm-3-turbo'],
            'supports_pdf': True  # 通过文件解析API支持PDF
        },
        'deepseek': {
            'name': 'DeepSeek',
            'default_base_url': 'https://api.deepseek.com/v1',
            'models': ['deepseek-chat', 'deepseek-coder']
        },
        'ollama': {
            'name': 'Ollama (本地)',
            'default_base_url': 'http://localhost:11434',
            'models': [
                'qwen3:8b',                # 通义千问3 8B
                'qwen3:4b',                # 通义千问3 4B
                'qwen3:1.7b',              # 通义千问3 1.7B
                'qwen2.5:7b',              # 通义千问2.5 7B
                'qwen2.5:14b',             # 通义千问2.5 14B
                'llama3.1:8b',             # Meta Llama 3.1 8B
                'llama3.1:70b',            # Meta Llama 3.1 70B
                'gemma3:12b',              # Google Gemma 3 12B
                'gemma3:4b',               # Google Gemma 3 4B
                'deepseek-r1:8b',          # DeepSeek R1 8B
                'deepseek-r1:14b',         # DeepSeek R1 14B
                'deepseek-r1:32b',         # DeepSeek R1 32B
                'phi4:14b',                # Microsoft Phi-4 14B
                'mistral:7b',              # Mistral 7B
                'nomic-embed-text',        # Embedding 模型
            ],
            'no_api_key': True  # Ollama 本地部署无需 API Key
        },
        'custom': {
            'name': '自定义模型',
            'default_base_url': '',
            'models': []
        }
    }
    
    @classmethod
    def create_config(cls, config_name, model_type, api_key, model_name,
                      api_base_url=None, max_tokens=2048, temperature=0.7,
                      is_default=False, extra_params=None, username=ADMIN_USERNAME):
        """
        创建LLM配置
        
        Args:
            config_name: 配置名称
            model_type: 模型类型 (openai/qianwen/wenxin/zhipu/deepseek/custom)
            api_key: API密钥
            model_name: 模型名称
            api_base_url: API基础URL（可选，使用默认值）
            max_tokens: 最大token数
            temperature: 温度参数
            is_default: 是否设为默认配置
            extra_params: 额外参数（JSON格式）
            username: 所属用户名
        
        Returns:
            配置ID或None
        """
        if model_type not in cls.SUPPORTED_MODELS:
            raise ValueError(f"不支持的模型类型: {model_type}")
        
        # 使用默认base_url
        if not api_base_url:
            api_base_url = cls.SUPPORTED_MODELS[model_type]['default_base_url']
        
        # 如果设为默认，先取消该用户的其他默认配置
        if is_default:
            cls._clear_default_config(username=username)
        
        sql = """
            INSERT INTO llm_configs 
            (config_name, model_type, api_base_url, api_key, model_name, 
             max_tokens, temperature, is_default, extra_params, username, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        now = datetime.now()
        extra_params_json = json.dumps(extra_params) if extra_params else None
        
        config_id, affected = dml_sql_with_insert_id(sql, (
            config_name, model_type, api_base_url, api_key, model_name,
            max_tokens, temperature, is_default, extra_params_json, username, now, now
        ))
        
        return config_id
    
    @classmethod
    def get_config(cls, config_id):
        """获取指定配置"""
        sql = "SELECT * FROM llm_configs WHERE id = %s AND is_active = 1"
        result = fetch_one(sql, (config_id,))
        if result and result.get('extra_params'):
            result['extra_params'] = json.loads(result['extra_params'])
        return result
    
    @classmethod
    def get_default_config(cls, username=ADMIN_USERNAME):
        """获取用户选中的配置：优先 user_selected_configs 表，fallback 到 is_default 字段"""
        from .user_selection import get_effective_config_id
        selected_id = get_effective_config_id(username, 'llm')
        if selected_id is not None:
            result = cls.get_config(selected_id)
            if result:
                return result
        # fallback: 旧的 is_default 逻辑
        if username != ADMIN_USERNAME:
            sql = "SELECT * FROM llm_configs WHERE is_default = 1 AND is_active = 1 AND username = %s LIMIT 1"
            result = fetch_one(sql, (username,))
            if result:
                if result.get('extra_params'):
                    result['extra_params'] = json.loads(result['extra_params'])
                return result
        sql = "SELECT * FROM llm_configs WHERE is_default = 1 AND is_active = 1 AND username = %s LIMIT 1"
        result = fetch_one(sql, (ADMIN_USERNAME,))
        if result and result.get('extra_params'):
            result['extra_params'] = json.loads(result['extra_params'])
        return result
    
    @classmethod
    def list_configs(cls, include_inactive=False, username=ADMIN_USERNAME):
        """列出配置：admin只看自己的，普通用户看自己的+admin的"""
        if username == ADMIN_USERNAME:
            if include_inactive:
                sql = "SELECT * FROM llm_configs WHERE username = %s ORDER BY is_default DESC, created_at DESC"
            else:
                sql = "SELECT * FROM llm_configs WHERE username = %s AND is_active = 1 ORDER BY is_default DESC, created_at DESC"
            results = query_sql(sql, (ADMIN_USERNAME,))
        else:
            if include_inactive:
                sql = "SELECT * FROM llm_configs WHERE username = %s OR username = %s ORDER BY is_default DESC, created_at DESC"
            else:
                sql = "SELECT * FROM llm_configs WHERE (username = %s OR username = %s) AND is_active = 1 ORDER BY is_default DESC, created_at DESC"
            results = query_sql(sql, (username, ADMIN_USERNAME))
        
        for r in results:
            if r.get('extra_params'):
                r['extra_params'] = json.loads(r['extra_params'])
        return results
    
    @classmethod
    def update_config(cls, config_id, username=ADMIN_USERNAME, **kwargs):
        """更新配置（普通用户只能改自己的）"""
        # 权限校验：普通用户不能修改 admin 的配置
        config = cls.get_config(config_id)
        if not config:
            return False
        config_owner = config.get('username', ADMIN_USERNAME)
        if username != ADMIN_USERNAME and config_owner == ADMIN_USERNAME:
            raise PermissionError("无权修改管理员配置")
        
        allowed_fields = ['config_name', 'model_type', 'api_base_url', 'api_key', 
                          'model_name', 'max_tokens', 'temperature', 'is_default', 
                          'extra_params', 'is_active']
        
        updates = []
        params = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                if field == 'extra_params' and value is not None:
                    value = json.dumps(value)
                if field == 'is_default' and value:
                    # 清除同归属用户的默认标记
                    cls._clear_default_config(username=config_owner)
                updates.append(f"{field} = %s")
                params.append(value)
        
        if not updates:
            return False
        
        updates.append("updated_at = %s")
        params.append(datetime.now())
        params.append(config_id)
        
        sql = f"UPDATE llm_configs SET {', '.join(updates)} WHERE id = %s"
        affected = dml_sql(sql, params)
        return affected > 0
    
    @classmethod
    def delete_config(cls, config_id, soft_delete=True, username=ADMIN_USERNAME):
        """删除配置（普通用户只能删自己的）"""
        # 权限校验
        if username != ADMIN_USERNAME:
            config = cls.get_config(config_id)
            if config and config.get('username', ADMIN_USERNAME) == ADMIN_USERNAME:
                raise PermissionError("无权删除管理员配置")
        
        if soft_delete:
            sql = "UPDATE llm_configs SET is_active = 0, updated_at = %s WHERE id = %s"
            affected = dml_sql(sql, (datetime.now(), config_id))
        else:
            sql = "DELETE FROM llm_configs WHERE id = %s"
            affected = dml_sql(sql, (config_id,))
        return affected > 0
    
    @classmethod
    def _clear_default_config(cls, username=ADMIN_USERNAME):
        """清除该用户的所有默认配置标记"""
        sql = "UPDATE llm_configs SET is_default = 0 WHERE is_default = 1 AND is_active = 1 AND username = %s"
        dml_sql(sql, (username,))
    
    @classmethod
    def select_config(cls, config_id, username=ADMIN_USERNAME):
        """选中配置（互斥）：写入 user_selected_configs 表，不影响任何人的 is_default"""
        target = cls.get_config(config_id)
        if not target:
            return False
        from .user_selection import select_config as do_select
        do_select(username, 'llm', config_id)
        return True
    
    @classmethod
    def get_supported_models(cls):
        """获取支持的模型列表"""
        return cls.SUPPORTED_MODELS


class WebSearchConfigManager:
    """网络搜索配置管理器"""
    
    SUPPORTED_ENGINES = {
        'duckduckgo': {
            'name': 'DuckDuckGo（免费）',
            'default_url': ''
        },
        'google': {
            'name': 'Google搜索',
            'default_url': 'https://www.googleapis.com/customsearch/v1'
        },
        'baidu': {
            'name': '百度搜索',
            'default_url': 'https://api.baidu.com/json/tongji/v1/ReportService/getData'
        },
        'bing': {
            'name': 'Bing搜索',
            'default_url': 'https://api.bing.microsoft.com/v7.0/search'
        },
        'custom': {
            'name': '自定义搜索',
            'default_url': ''
        }
    }
    
    @classmethod
    def create_config(cls, search_engine, api_key, api_url=None, 
                      extra_params=None, is_default=False, username=ADMIN_USERNAME):
        """创建搜索配置"""
        if search_engine not in cls.SUPPORTED_ENGINES:
            raise ValueError(f"不支持的搜索引擎: {search_engine}")
        
        if not api_url:
            api_url = cls.SUPPORTED_ENGINES[search_engine]['default_url']
        
        if is_default:
            cls._clear_default_config(username=username)
        
        sql = """
            INSERT INTO web_search_configs 
            (search_engine, api_url, api_key, extra_params, is_default, is_active, username, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)
        """
        now = datetime.now()
        extra_params_json = json.dumps(extra_params) if extra_params else None
        
        config_id, _ = dml_sql_with_insert_id(sql, (
            search_engine, api_url, api_key, extra_params_json, is_default, username, now, now
        ))
        return config_id
    
    @classmethod
    def get_default_config(cls, username=ADMIN_USERNAME):
        """获取用户选中的搜索配置：优先 user_selected_configs 表"""
        from .user_selection import get_effective_config_id
        selected_id = get_effective_config_id(username, 'search')
        if selected_id is not None:
            sql = "SELECT * FROM web_search_configs WHERE id = %s AND is_active = 1"
            result = fetch_one(sql, (selected_id,))
            if result:
                if result.get('extra_params'):
                    result['extra_params'] = json.loads(result['extra_params'])
                return result
        # fallback
        if username != ADMIN_USERNAME:
            sql = "SELECT * FROM web_search_configs WHERE is_default = 1 AND is_active = 1 AND username = %s LIMIT 1"
            result = fetch_one(sql, (username,))
            if result:
                if result.get('extra_params'):
                    result['extra_params'] = json.loads(result['extra_params'])
                return result
        sql = "SELECT * FROM web_search_configs WHERE is_default = 1 AND is_active = 1 AND username = %s LIMIT 1"
        result = fetch_one(sql, (ADMIN_USERNAME,))
        if result and result.get('extra_params'):
            result['extra_params'] = json.loads(result['extra_params'])
        return result
    
    @classmethod
    def list_configs(cls, username=ADMIN_USERNAME):
        """列出搜索配置：admin只看自己的，普通用户看自己的+admin的"""
        if username == ADMIN_USERNAME:
            sql = "SELECT * FROM web_search_configs WHERE username = %s AND is_active = 1 ORDER BY is_default DESC"
            results = query_sql(sql, (ADMIN_USERNAME,))
        else:
            sql = "SELECT * FROM web_search_configs WHERE (username = %s OR username = %s) AND is_active = 1 ORDER BY is_default DESC"
            results = query_sql(sql, (username, ADMIN_USERNAME))
        for r in results:
            if r.get('extra_params'):
                r['extra_params'] = json.loads(r['extra_params'])
        return results
    
    @classmethod
    def update_config(cls, config_id, username=ADMIN_USERNAME, **kwargs):
        """更新搜索配置（普通用户只能改自己的）"""
        existing = fetch_one("SELECT * FROM web_search_configs WHERE id = %s AND is_active = 1", (config_id,))
        if not existing:
            return False
        config_owner = existing.get('username', ADMIN_USERNAME)
        if username != ADMIN_USERNAME and config_owner == ADMIN_USERNAME:
            raise PermissionError("无权修改管理员配置")
        
        allowed_fields = ['search_engine', 'api_url', 'api_key', 'extra_params', 
                          'is_default', 'is_active']
        
        updates = []
        params = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                if field == 'extra_params' and value is not None:
                    value = json.dumps(value)
                if field == 'is_default' and value:
                    cls._clear_default_config(username=config_owner)
                updates.append(f"{field} = %s")
                params.append(value)
        
        if not updates:
            return False
        
        updates.append("updated_at = %s")
        params.append(datetime.now())
        params.append(config_id)
        
        sql = f"UPDATE web_search_configs SET {', '.join(updates)} WHERE id = %s"
        affected = dml_sql(sql, params)
        return affected > 0
    
    @classmethod
    def delete_config(cls, config_id, username=ADMIN_USERNAME):
        """软删除配置（普通用户只能删自己的）"""
        if username != ADMIN_USERNAME:
            sql = "SELECT username FROM web_search_configs WHERE id = %s AND is_active = 1"
            existing = fetch_one(sql, (config_id,))
            if existing and existing.get('username', ADMIN_USERNAME) == ADMIN_USERNAME:
                raise PermissionError("无权删除管理员配置")
        
        sql = "UPDATE web_search_configs SET is_active = 0, updated_at = %s WHERE id = %s"
        affected = dml_sql(sql, (datetime.now(), config_id))
        return affected > 0
    
    @classmethod
    def _clear_default_config(cls, username=ADMIN_USERNAME):
        """清除该用户的默认标记"""
        sql = "UPDATE web_search_configs SET is_default = 0 WHERE is_default = 1 AND is_active = 1 AND username = %s"
        dml_sql(sql, (username,))
    
    @classmethod
    def select_config(cls, config_id, username=ADMIN_USERNAME):
        """选中配置（互斥）：写入 user_selected_configs 表"""
        target = fetch_one("SELECT * FROM web_search_configs WHERE id = %s AND is_active = 1", (config_id,))
        if not target:
            return False
        from .user_selection import select_config as do_select
        do_select(username, 'search', config_id)
        return True
