"""
LLM服务核心模块
提供统一的大模型调用接口，支持多种模型
"""
import json
import requests
from config.logging_config import logger
from .llm_config import LLMConfigManager


class LLMService:
    """LLM服务类 - 统一调用接口"""
    
    def __init__(self, config=None):
        """
        初始化LLM服务
        
        Args:
            config: LLM配置，如果为None则使用默认配置
        """
        self.config = config or LLMConfigManager.get_default_config()
        if not self.config:
            raise ValueError("未找到LLM配置，请先配置大模型")
    
    def chat_completion(self, messages, stream=False, **kwargs):
        """
        统一的聊天补全接口
        
        Args:
            messages: 消息列表 [{'role': 'user/assistant/system', 'content': '...'}]
            stream: 是否流式输出
            **kwargs: 其他参数（覆盖配置中的默认值）
        
        Returns:
            如果stream=False: {'content': '回复内容', 'usage': {...}}
            如果stream=True: 生成器，yield每个chunk
        """
        model_type = self.config.get('model_type', 'openai')
        
        # 合并参数
        params = {
            'model': kwargs.get('model', self.config.get('model_name')),
            'max_tokens': kwargs.get('max_tokens', self.config.get('max_tokens', 2048)),
            'temperature': kwargs.get('temperature', self.config.get('temperature', 0.7)),
            'stream': stream
        }
        
        try:
            if model_type == 'openai':
                return self._call_openai_api(messages, params)
            elif model_type == 'qianwen':
                return self._call_qianwen_api(messages, params)
            elif model_type == 'wenxin':
                return self._call_wenxin_api(messages, params)
            elif model_type == 'zhipu':
                return self._call_zhipu_api(messages, params)
            elif model_type == 'deepseek':
                return self._call_deepseek_api(messages, params)
            elif model_type == 'custom':
                return self._call_custom_api(messages, params)
            else:
                raise ValueError(f"不支持的模型类型: {model_type}")
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise
    
    def _call_openai_api(self, messages, params):
        """调用OpenAI兼容API"""
        api_url = self.config.get('api_base_url', 'https://api.openai.com/v1')
        api_key = self.config.get('api_key')
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        data = {
            'model': params['model'],
            'messages': messages,
            'max_tokens': params['max_tokens'],
            'temperature': params['temperature'],
            'stream': params['stream']
        }
        
        url = f"{api_url.rstrip('/')}/chat/completions"
        
        if params['stream']:
            return self._stream_response(url, headers, data)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            result = response.json()
            
            return {
                'content': result['choices'][0]['message']['content'],
                'usage': result.get('usage', {})
            }
    
    def _call_qianwen_api(self, messages, params):
        """调用通义千问API（兼容OpenAI格式）"""
        # 通义千问支持OpenAI兼容模式
        return self._call_openai_api(messages, params)
    
    def _call_wenxin_api(self, messages, params):
        """调用文心一言API"""
        api_url = self.config.get('api_base_url')
        api_key = self.config.get('api_key')
        extra_params = self.config.get('extra_params', {}) or {}
        
        # 文心需要access_token
        access_token = extra_params.get('access_token')
        if not access_token:
            access_token = self._get_wenxin_access_token(api_key, extra_params.get('secret_key'))
        
        # 转换消息格式
        wenxin_messages = []
        for msg in messages:
            wenxin_messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
        
        model = params['model']
        url = f"{api_url}/{model}?access_token={access_token}"
        
        headers = {'Content-Type': 'application/json'}
        data = {
            'messages': wenxin_messages,
            'temperature': params['temperature'],
            'stream': params['stream']
        }
        
        if params['stream']:
            return self._stream_wenxin_response(url, headers, data)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            result = response.json()
            
            if 'error_code' in result:
                raise Exception(f"文心API错误: {result.get('error_msg')}")
            
            return {
                'content': result.get('result', ''),
                'usage': result.get('usage', {})
            }
    
    def _get_wenxin_access_token(self, api_key, secret_key):
        """获取文心一言access_token"""
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            'grant_type': 'client_credentials',
            'client_id': api_key,
            'client_secret': secret_key
        }
        response = requests.post(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json().get('access_token')
    
    def _call_zhipu_api(self, messages, params):
        """调用智谱GLM API"""
        api_url = self.config.get('api_base_url', 'https://open.bigmodel.cn/api/paas/v4')
        api_key = self.config.get('api_key')
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        data = {
            'model': params['model'],
            'messages': messages,
            'max_tokens': params['max_tokens'],
            'temperature': params['temperature'],
            'stream': params['stream']
        }
        
        url = f"{api_url.rstrip('/')}/chat/completions"
        
        if params['stream']:
            return self._stream_response(url, headers, data)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            result = response.json()
            
            return {
                'content': result['choices'][0]['message']['content'],
                'usage': result.get('usage', {})
            }
    
    def _call_deepseek_api(self, messages, params):
        """调用DeepSeek API（兼容OpenAI格式）"""
        return self._call_openai_api(messages, params)
    
    def _call_custom_api(self, messages, params):
        """调用自定义API"""
        api_url = self.config.get('api_base_url')
        api_key = self.config.get('api_key')
        extra_params = self.config.get('extra_params', {}) or {}
        
        # 构建请求头
        headers = extra_params.get('headers', {})
        headers['Content-Type'] = 'application/json'
        
        # API密钥位置
        key_location = extra_params.get('key_location', 'header')
        key_name = extra_params.get('key_name', 'Authorization')
        key_prefix = extra_params.get('key_prefix', 'Bearer ')
        
        if key_location == 'header':
            headers[key_name] = f"{key_prefix}{api_key}"
        
        # 构建请求体
        data = {
            'model': params['model'],
            'messages': messages,
            'max_tokens': params['max_tokens'],
            'temperature': params['temperature'],
            'stream': params['stream']
        }
        
        # 合并额外参数
        if extra_params.get('body_params'):
            data.update(extra_params['body_params'])
        
        if params['stream']:
            return self._stream_response(api_url, headers, data)
        else:
            response = requests.post(api_url, headers=headers, json=data, timeout=120)
            response.raise_for_status()
            result = response.json()
            
            # 解析响应（根据配置的字段映射）
            content_path = extra_params.get('content_path', 'choices.0.message.content')
            content = self._extract_nested_value(result, content_path)
            
            return {
                'content': content,
                'usage': result.get('usage', {})
            }
    
    def _stream_response(self, url, headers, data):
        """流式响应处理（OpenAI格式）"""
        response = requests.post(url, headers=headers, json=data, stream=True, timeout=120)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    line = line[6:]
                    if line == '[DONE]':
                        break
                    try:
                        chunk = json.loads(line)
                        delta = chunk.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    
    def _stream_wenxin_response(self, url, headers, data):
        """文心一言流式响应处理"""
        response = requests.post(url, headers=headers, json=data, stream=True, timeout=120)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    line = line[6:]
                    try:
                        chunk = json.loads(line)
                        content = chunk.get('result', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    
    def _extract_nested_value(self, data, path):
        """从嵌套字典中提取值"""
        keys = path.split('.')
        value = data
        for key in keys:
            if key.isdigit():
                key = int(key)
            try:
                value = value[key]
            except (KeyError, IndexError, TypeError):
                return ''
        return value


def get_llm_service(config_id=None):
    """
    获取LLM服务实例
    
    Args:
        config_id: 配置ID，如果为None则使用默认配置
    
    Returns:
        LLMService实例
    """
    if config_id:
        config = LLMConfigManager.get_config(config_id)
    else:
        config = None
    
    return LLMService(config)
