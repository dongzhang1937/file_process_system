"""
LLM服务核心模块
提供统一的大模型调用接口，支持多种模型
"""
import os
import json
import base64
import requests
from decimal import Decimal
from config.logging_config import logger
from .llm_config import LLMConfigManager


def convert_decimal(obj):
    """将Decimal类型转换为float，用于JSON序列化"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal(item) for item in obj]
    return obj


class LLMService:
    """LLM服务类 - 统一调用接口"""
    
    def __init__(self, config=None):
        """
        初始化LLM服务
        
        Args:
            config: LLM配置，如果为None则使用默认配置
        """
        config = config or LLMConfigManager.get_default_config()
        if not config:
            raise ValueError("未找到LLM配置，请先配置大模型")
        # 转换Decimal类型为float，避免JSON序列化错误
        self.config = convert_decimal(config)
    
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
        # max_tokens 策略：
        #   - 调用方传 max_tokens=None → 不限制（不发送该字段给API，让模型自由输出）
        #   - 调用方传 max_tokens=具体数值 → 使用该数值
        #   - 调用方不传 → 使用配置中的默认值（兜底2048）
        raw_max_tokens = kwargs.get('max_tokens', '__NOT_SET__')
        if raw_max_tokens == '__NOT_SET__':
            # 调用方未传，使用配置默认值
            resolved_max_tokens = self.config.get('max_tokens', 2048)
        else:
            # 调用方显式传了值（包括 None）
            resolved_max_tokens = raw_max_tokens
        
        params = {
            'model': kwargs.get('model', self.config.get('model_name')),
            'max_tokens': resolved_max_tokens,
            'temperature': kwargs.get('temperature', self.config.get('temperature', 0.7)),
            'stream': stream
        }
        
        try:
            if model_type == 'openai':
                return self._call_openai_api(messages, params)
            elif model_type == 'gemini':
                return self._call_gemini_api(messages, params)
            elif model_type == 'qianwen':
                return self._call_qianwen_api(messages, params)
            elif model_type == 'wenxin':
                return self._call_wenxin_api(messages, params)
            elif model_type == 'zhipu':
                return self._call_zhipu_api(messages, params)
            elif model_type == 'deepseek':
                return self._call_deepseek_api(messages, params)
            elif model_type == 'ollama':
                return self._call_ollama_api(messages, params)
            elif model_type == 'custom':
                return self._call_custom_api(messages, params)
            else:
                raise ValueError(f"不支持的模型类型: {model_type}")
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise
    
    def analyze_pdf_with_gemini(self, pdf_path: str, prompt: str) -> dict:
        """
        使用 Gemini 直接分析 PDF 文件
        
        Args:
            pdf_path: PDF 文件路径
            prompt: 分析提示词
        
        Returns:
            {'content': '回复内容', 'usage': {...}}
        """
        model_type = self.config.get('model_type', 'openai')
        if model_type != 'gemini':
            raise ValueError(f"当前配置的模型类型 {model_type} 不支持直接解析PDF，请使用 Gemini 模型")
        
        api_key = self.config.get('api_key') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("未配置 Gemini API Key")
        
        model = self.config.get('model_name', 'gemini-2.0-flash')
        api_base = self.config.get('api_base_url') or 'https://generativelanguage.googleapis.com/v1beta'
        
        # 读取 PDF 文件并转为 base64
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')
        
        # 构建请求
        url = f"{api_base.rstrip('/')}/models/{model}:generateContent?key={api_key}"
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        data = {
            'contents': [{
                'parts': [
                    {
                        'inline_data': {
                            'mime_type': 'application/pdf',
                            'data': pdf_data
                        }
                    },
                    {
                        'text': prompt
                    }
                ]
            }],
            'generationConfig': {
                'temperature': self.config.get('temperature', 0.7),
            }
        }
        # max_tokens 存在时才传 maxOutputTokens
        config_max_tokens = self.config.get('max_tokens')
        if config_max_tokens:
            data['generationConfig']['maxOutputTokens'] = config_max_tokens
        
        logger.info(f"[Gemini PDF] 调用API: {url[:80]}...")
        logger.info(f"[Gemini PDF] 模型: {model}, PDF大小: {len(pdf_data)} bytes (base64)")
        
        response = requests.post(url, headers=headers, json=data, timeout=180)
        result = response.json()
        
        logger.info(f"[Gemini PDF] API响应状态: {response.status_code}")
        
        if 'error' in result:
            error_msg = result['error'].get('message', str(result['error']))
            logger.error(f"[Gemini PDF] API错误: {error_msg}")
            raise Exception(f"Gemini API错误: {error_msg}")
        
        # 解析响应
        if 'candidates' not in result or not result['candidates']:
            logger.error(f"[Gemini PDF] 响应格式错误: {result}")
            raise Exception("Gemini API响应格式错误")
        
        content = result['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
        usage = result.get('usageMetadata', {})
        
        logger.info(f"[Gemini PDF] 成功获取响应，内容长度: {len(content)}")
        
        return {
            'content': content,
            'usage': usage
        }
    
    def analyze_pdf_with_zhipu(self, pdf_path: str, prompt: str) -> dict:
        """
        使用智谱文件解析API解析PDF文件
        
        流程：
        1. 调用 /files/parser/create 创建解析任务
        2. 轮询 /files/parser/query/{id} 获取解析结果
        3. 将解析结果作为上下文发给LLM进行分析
        
        Args:
            pdf_path: PDF 文件路径
            prompt: 分析提示词
        
        Returns:
            {'content': '回复内容', 'usage': {...}}
        """
        import time
        
        api_url = self.config.get('api_base_url') or 'https://open.bigmodel.cn/api/paas/v4'
        api_key = self.config.get('api_key')
        
        if not api_key:
            raise ValueError("未配置智谱 API Key")
        
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        
        # Step 1: 创建文件解析任务
        create_url = f"{api_url.rstrip('/')}/files/parser/create"
        
        # 获取文件扩展名确定file_type
        ext = os.path.splitext(pdf_path)[1].lower()
        file_type_map = {
            '.pdf': 'PDF',
            '.docx': 'DOCX',
            '.doc': 'DOC',
            '.xlsx': 'XLSX',
            '.xls': 'XLS',
            '.pptx': 'PPTX',
            '.ppt': 'PPT',
            '.txt': 'TXT',
            '.md': 'MD',
            '.jpg': 'JPG',
            '.jpeg': 'JPEG',
            '.png': 'PNG',
        }
        file_type = file_type_map.get(ext, 'PDF')
        
        logger.info(f"[智谱文件解析] 创建解析任务: {pdf_path}, file_type={file_type}")
        
        with open(pdf_path, 'rb') as f:
            files = {'file': (os.path.basename(pdf_path), f)}
            data = {
                'tool_type': 'lite',
                'file_type': file_type
            }
            response = requests.post(create_url, headers=headers, files=files, data=data, timeout=120)
        
        result = response.json()
        logger.info(f"[智谱文件解析] 创建任务响应: {response.status_code}, {result}")
        
        if not result.get('success', True):
            error_msg = result.get('error', {}).get('message', result.get('msg', str(result)))
            raise Exception(f"智谱文件解析创建失败: {error_msg}")
        
        # 获取任务ID（智谱API返回格式可能是 task_id 或 data.id）
        task_id = result.get('task_id') or result.get('data', {}).get('id') or result.get('id')
        if not task_id:
            raise Exception(f"智谱文件解析返回无任务ID: {result}")
        
        logger.info(f"[智谱文件解析] 任务ID: {task_id}")
        
        # Step 2: 轮询查询解析结果
        # 智谱API正确的查询URL: /files/parser/result/{taskId}/{format_type}
        # format_type: text(纯文本) 或 download_link(下载链接)
        query_url = f"{api_url.rstrip('/')}/files/parser/result/{task_id}/text"
        
        max_retries = 60  # 最多等待5分钟（每5秒查一次）
        for attempt in range(max_retries):
            time.sleep(5)
            
            query_response = requests.get(query_url, headers=headers, timeout=30)
            status_code = query_response.status_code
            logger.info(f"[智谱文件解析] 查询进度 [{attempt+1}/{max_retries}]: HTTP {status_code}")
            
            # 如果返回 404 或 202，表示任务还在处理中，继续等待
            if status_code == 404 or status_code == 202:
                logger.info(f"[智谱文件解析] 任务处理中，继续等待...")
                continue
            
            if status_code != 200:
                logger.warning(f"[智谱文件解析] 查询返回异常状态: {status_code}, 响应: {query_response.text[:200]}")
                continue
            
            # 200 状态码，尝试解析结果
            try:
                query_result = query_response.json()
            except Exception:
                # 响应可能直接是纯文本内容
                parsed_content = query_response.text
                if parsed_content and len(parsed_content) > 10:
                    logger.info(f"[智谱文件解析] 解析完成（纯文本），内容长度: {len(parsed_content)}")
                    return self._analyze_parsed_content(parsed_content, prompt)
                continue
            
            # JSON 响应 - 检查状态
            status = query_result.get('data', {}).get('status') or query_result.get('status', '')
            
            if status in ('failed', 'FAILED', 'error', 'ERROR'):
                error_msg = query_result.get('data', {}).get('error', query_result.get('message', '解析失败'))
                raise Exception(f"智谱文件解析失败: {error_msg}")
            
            if status in ('processing', 'PROCESSING', 'pending', 'PENDING'):
                logger.info(f"[智谱文件解析] 任务状态: {status}，继续等待...")
                continue
            
            # 尝试提取解析内容
            parsed_content = (
                query_result.get('data', {}).get('content', '') or 
                query_result.get('content', '') or
                query_result.get('data', {}).get('result', '') or
                query_result.get('result', '')
            )
            
            if not parsed_content:
                # 整个data可能就是内容
                data = query_result.get('data')
                if isinstance(data, str) and len(data) > 10:
                    parsed_content = data
                elif isinstance(data, dict):
                    parsed_content = json.dumps(data, ensure_ascii=False)
            
            if parsed_content and len(parsed_content) > 10:
                logger.info(f"[智谱文件解析] 解析完成，内容长度: {len(parsed_content)}")
                return self._analyze_parsed_content(parsed_content, prompt)
            else:
                logger.info(f"[智谱文件解析] 返回内容为空或过短，继续等待... 响应: {json.dumps(query_result, ensure_ascii=False)[:200]}")
            
            # 其他状态继续等待
        
        raise Exception("智谱文件解析超时（等待5分钟未完成）")
    
    def _analyze_parsed_content(self, parsed_content: str, prompt: str) -> dict:
        """
        将文件解析得到的内容发给LLM分析，自动处理超长内容。
        
        如果内容太长超出模型token限制，会分段发送并合并结果。
        
        Args:
            parsed_content: 文件解析后的文本内容
            prompt: 分析提示词
            
        Returns:
            {'content': '回复内容', 'usage': {...}}
        """
        # 估算 token 数（中文约1.5字符/token，英文约4字符/token，取保守估计2字符/token）
        estimated_tokens = len(parsed_content) // 2
        
        # 获取模型 token 限制
        model_type = self.config.get('model_type', 'openai')
        max_tokens_output = self.config.get('max_tokens', 2048)
        
        # 不同模型的上下文窗口限制
        model_context_limits = {
            'zhipu': 16384,
            'openai': 128000,
            'gemini': 1000000,
            'deepseek': 64000,
            'qianwen': 32000,
            'ollama': 32000,
        }
        context_limit = model_context_limits.get(model_type, 16384)
        
        # prompt + system 大约占 1500 tokens
        prompt_overhead = 1500
        max_content_tokens = context_limit - max_tokens_output - prompt_overhead
        # 转换回字符数（保守估计：2字符/token）
        max_content_chars = max_content_tokens * 2
        
        logger.info(f"[文档分析] 内容长度: {len(parsed_content)} 字符, 估算 {estimated_tokens} tokens, "
                     f"模型: {model_type}, 上下文限制: {context_limit}, 可用内容 tokens: {max_content_tokens}")
        
        if len(parsed_content) <= max_content_chars:
            # 内容不超长，直接发送
            messages = [
                {"role": "system", "content": "你是一个专业的文档分析助手。以下是通过文件解析工具提取的文档内容，请根据用户的要求进行分析。"},
                {"role": "user", "content": f"文档解析内容:\n{parsed_content}\n\n{prompt}"}
            ]
            return self.chat_completion(messages)
        
        # 内容超长，需要分段处理
        logger.info(f"[文档分析] 内容超长（{len(parsed_content)} 字符 > {max_content_chars} 字符限制），启用分段处理")
        
        # 按段落/章节边界切分内容
        segments = self._split_content_by_segments(parsed_content, max_content_chars)
        logger.info(f"[文档分析] 切分为 {len(segments)} 个片段")
        
        all_chapters = []
        total_usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        
        for i, segment in enumerate(segments):
            segment_prompt = prompt
            if len(segments) > 1:
                segment_prompt = (
                    f"这是文档的第 {i+1}/{len(segments)} 部分。\n"
                    f"请分析这部分内容，提取其中包含的章节结构。\n\n"
                    f"{prompt}"
                )
            
            messages = [
                {"role": "system", "content": "你是一个专业的文档分析助手。以下是通过文件解析工具提取的文档内容（可能是文档的一部分），请根据用户的要求进行分析。"},
                {"role": "user", "content": f"文档解析内容:\n{segment}\n\n{segment_prompt}"}
            ]
            
            try:
                result = self.chat_completion(messages)
                content = result.get('content', '')
                usage = result.get('usage', {})
                
                # 累加 usage
                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)
                
                if len(segments) > 1:
                    # 多段时需要合并 JSON 结果
                    all_chapters.append(content)
                    logger.info(f"[文档分析] 片段 {i+1}/{len(segments)} 处理完成，返回 {len(content)} 字符")
                else:
                    return result
                    
            except Exception as e:
                logger.error(f"[文档分析] 片段 {i+1}/{len(segments)} 处理失败: {e}")
                # 尝试进一步截断重试
                truncated = segment[:max_content_chars // 2]
                messages[1]["content"] = f"文档解析内容:\n{truncated}\n\n{segment_prompt}"
                try:
                    result = self.chat_completion(messages)
                    all_chapters.append(result.get('content', ''))
                    usage = result.get('usage', {})
                    for key in total_usage:
                        total_usage[key] += usage.get(key, 0)
                except Exception as e2:
                    logger.error(f"[文档分析] 片段 {i+1} 重试也失败: {e2}")
                    continue
        
        if not all_chapters:
            raise Exception("文档分析失败：所有片段处理均未成功")
        
        # 合并多段的JSON结果
        merged_content = self._merge_chapter_results(all_chapters)
        
        return {
            'content': merged_content,
            'usage': total_usage
        }
    
    def _split_content_by_segments(self, content: str, max_chars: int) -> list:
        """
        将长文档内容按段落/章节边界切分成多个片段。
        
        Args:
            content: 原始文档内容
            max_chars: 每个片段最大字符数
            
        Returns:
            文档片段列表
        """
        if len(content) <= max_chars:
            return [content]
        
        segments = []
        remaining = content
        
        while remaining:
            if len(remaining) <= max_chars:
                segments.append(remaining)
                break
            
            # 在 max_chars 范围内找一个好的切分点
            chunk = remaining[:max_chars]
            
            # 优先找双换行（段落边界）
            split_pos = chunk.rfind('\n\n')
            if split_pos < max_chars * 0.5:
                # 双换行太靠前，找单换行
                split_pos = chunk.rfind('\n')
            if split_pos < max_chars * 0.3:
                # 换行也太靠前，强制切分
                split_pos = max_chars
            
            segments.append(remaining[:split_pos])
            remaining = remaining[split_pos:].lstrip('\n')
        
        return segments
    
    def _merge_chapter_results(self, chapter_contents: list) -> str:
        """
        合并多段LLM返回的章节JSON结果。
        
        Args:
            chapter_contents: 每段LLM返回的内容列表
            
        Returns:
            合并后的JSON字符串
        """
        import re
        
        all_chapters = []
        
        for content in chapter_contents:
            # 尝试从返回中提取 chapters 数组
            try:
                # 去除 markdown 代码块标记
                clean = content.strip()
                if clean.startswith('```'):
                    clean = re.sub(r'^```\w*\n?', '', clean)
                    clean = re.sub(r'\n?```$', '', clean)
                
                data = json.loads(clean)
                if isinstance(data, dict) and 'chapters' in data:
                    all_chapters.extend(data['chapters'])
                elif isinstance(data, list):
                    all_chapters.extend(data)
            except json.JSONDecodeError:
                # 无法解析为JSON，作为原始文本添加
                logger.warning(f"[合并章节] 无法解析片段JSON，长度: {len(content)}")
                all_chapters.append({
                    'level': 1,
                    'title': '未解析章节',
                    'content': content,
                    'page': 0
                })
        
        result = json.dumps({'chapters': all_chapters}, ensure_ascii=False)
        logger.info(f"[合并章节] 合并完成: {len(all_chapters)} 个章节")
        return result
    
    def chat_with_tools(self, messages, tools=None, tool_choice='auto',
                        max_rounds=5, **kwargs):
        """
        带 Function Calling 的聊天接口

        流程：
        1. 发送消息和 tools 定义给 LLM
        2. 如果 LLM 返回 tool_calls，执行工具并将结果回传
        3. 重复直到 LLM 返回正常内容或达到最大轮次

        Args:
            messages: 消息列表
            tools: OpenAI 格式的 tool schema 列表，None 则使用所有注册工具
            tool_choice: 工具选择策略 ('auto'/'none'/'required')
            max_rounds: 最大工具调用轮次
            **kwargs: 传递给 chat API 的其他参数

        Returns:
            dict: {content, usage, tool_calls_log}
        """
        from .function_tools import get_all_tools, execute_tool

        if tools is None:
            tools = get_all_tools()

        if not tools:
            # 没有工具可用，直接普通聊天
            return self.chat_completion(messages, **kwargs)

        model_type = self.config.get('model_type', 'openai')

        # 目前仅 OpenAI 兼容格式的模型支持 Function Calling
        # (openai, deepseek, qianwen, zhipu, ollama 的 OpenAI兼容接口)
        supported_types = ('openai', 'deepseek', 'qianwen', 'zhipu', 'ollama', 'custom')
        if model_type not in supported_types:
            logger.warning(f"模型类型 {model_type} 不支持 Function Calling，回退到普通聊天")
            return self.chat_completion(messages, **kwargs)

        tool_calls_log = []  # 记录所有工具调用
        current_messages = list(messages)

        for round_num in range(max_rounds):
            logger.info(f"[Function Calling] 第 {round_num + 1}/{max_rounds} 轮")

            # 调用 LLM（带 tools）
            result = self._call_with_tools(current_messages, tools, tool_choice, **kwargs)

            if result is None:
                break

            message = result.get('message', {})
            content = message.get('content', '')
            tool_calls = message.get('tool_calls', [])

            if not tool_calls:
                # LLM 没有调用工具，返回最终结果
                return {
                    'content': content or '',
                    'usage': result.get('usage', {}),
                    'tool_calls_log': tool_calls_log
                }

            # 将 assistant 的 tool_calls 消息加入对话
            current_messages.append(message)

            # 执行每个工具调用
            for tool_call in tool_calls:
                tool_id = tool_call.get('id', '')
                function = tool_call.get('function', {})
                tool_name = function.get('name', '')
                tool_args = function.get('arguments', '{}')

                logger.info(f"[Function Calling] 调用工具: {tool_name}, args: {tool_args[:200]}")

                # 执行工具
                tool_result = execute_tool(tool_name, tool_args)

                # 记录日志
                tool_calls_log.append({
                    'round': round_num + 1,
                    'tool_name': tool_name,
                    'arguments': tool_args[:500],
                    'result': tool_result[:1000]
                })

                # 将工具结果以 role: tool 消息回传
                current_messages.append({
                    'role': 'tool',
                    'tool_call_id': tool_id,
                    'content': tool_result
                })

        # 达到最大轮次，最后再调一次不带 tools 获取总结
        logger.info("[Function Calling] 达到最大轮次，获取最终总结")
        final_result = self.chat_completion(current_messages, **kwargs)
        final_result['tool_calls_log'] = tool_calls_log
        return final_result

    def _call_with_tools(self, messages, tools, tool_choice='auto', **kwargs):
        """
        调用 OpenAI 兼容 API（带 tools 参数）

        Returns:
            dict: {message: {content, tool_calls}, usage} 或 None
        """
        model_type = self.config.get('model_type', 'openai')

        # 根据模型类型获取 API URL 和 headers
        if model_type == 'ollama':
            api_url = (self.config.get('api_base_url') or 'http://localhost:11434').rstrip('/')
            url = f"{api_url}/v1/chat/completions"
        elif model_type == 'zhipu':
            api_url = (self.config.get('api_base_url') or 'https://open.bigmodel.cn/api/paas/v4').rstrip('/')
            url = f"{api_url}/chat/completions"
        else:
            api_url = (self.config.get('api_base_url') or 'https://api.openai.com/v1').rstrip('/')
            url = f"{api_url}/chat/completions"

        api_key = self.config.get('api_key', '')
        headers = {
            'Content-Type': 'application/json',
        }
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        data = {
            'model': kwargs.get('model', self.config.get('model_name')),
            'messages': messages,
            'tools': tools,
            'tool_choice': tool_choice,
            'temperature': kwargs.get('temperature', self.config.get('temperature', 0.7)),
            'stream': False
        }
        # max_tokens 为 None 时不传，让模型自由输出
        raw_max_tokens = kwargs.get('max_tokens', self.config.get('max_tokens', 2048))
        if raw_max_tokens is not None:
            data['max_tokens'] = raw_max_tokens

        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            result = response.json()

            if 'error' in result:
                error_msg = result['error'].get('message', str(result['error']))
                logger.error(f"[Function Calling] API错误: {error_msg}")
                raise Exception(f"API错误: {error_msg}")

            if 'choices' not in result or not result['choices']:
                logger.error(f"[Function Calling] API响应异常: {result}")
                return None

            choice = result['choices'][0]
            return {
                'message': choice.get('message', {}),
                'usage': result.get('usage', {})
            }

        except Exception as e:
            logger.error(f"[Function Calling] 调用失败: {e}")
            raise

    def supports_pdf(self) -> bool:
        """检查当前配置的模型是否支持直接解析PDF"""
        model_type = self.config.get('model_type', 'openai')
        return model_type in ('gemini', 'zhipu')
    
    def _call_openai_api(self, messages, params):
        """调用OpenAI兼容API"""
        api_url = self.config.get('api_base_url') or 'https://api.openai.com/v1'
        api_key = self.config.get('api_key')
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        data = {
            'model': params['model'],
            'messages': messages,
            'temperature': params['temperature'],
            'stream': params['stream']
        }
        # max_tokens 为 None 时不传，让模型自由输出到自然结束
        if params.get('max_tokens') is not None:
            data['max_tokens'] = params['max_tokens']
        
        url = f"{api_url.rstrip('/')}/chat/completions"
        
        if params['stream']:
            return self._stream_response(url, headers, data)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            result = response.json()
            
            # 检查API错误响应
            if 'error' in result:
                error_msg = result['error'].get('message', str(result['error']))
                raise Exception(f"API错误: {error_msg}")
            
            if 'choices' not in result:
                logger.error(f"API响应异常: {result}")
                raise Exception(f"API响应格式错误: {result.get('msg', result.get('message', '未知错误'))}")
            
            choice = result['choices'][0]
            finish_reason = choice.get('finish_reason', 'unknown')
            content = choice.get('message', {}).get('content')
            
            # content 可能为 null（如模型只返回 tool_calls、达到 max_tokens 截断等）
            if content is None:
                logger.warning(f"[OpenAI API] content 为 null, finish_reason={finish_reason}, "
                              f"has_tool_calls={bool(choice.get('message', {}).get('tool_calls'))}")
                content = ''
            
            if finish_reason == 'length':
                logger.warning(f"[OpenAI API] 输出被截断 (finish_reason=length)! "
                              f"content长度={len(content)}, max_tokens={params.get('max_tokens', '未设置')}")
            
            return {
                'content': content,
                'usage': result.get('usage', {}),
                'finish_reason': finish_reason
            }
    
    def _call_gemini_api(self, messages, params):
        """调用 Google Gemini API"""
        api_key = self.config.get('api_key') or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("未配置 Gemini API Key")
        
        api_base = self.config.get('api_base_url') or 'https://generativelanguage.googleapis.com/v1beta'
        model = params['model']
        
        # 转换消息格式为 Gemini 格式
        contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg['role']
            content = msg['content']
            
            if role == 'system':
                # Gemini 使用 systemInstruction 处理系统消息
                system_instruction = content
            elif role == 'user':
                contents.append({
                    'role': 'user',
                    'parts': [{'text': content}]
                })
            elif role == 'assistant':
                contents.append({
                    'role': 'model',
                    'parts': [{'text': content}]
                })
        
        url = f"{api_base.rstrip('/')}/models/{model}:generateContent?key={api_key}"
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        generation_config = {
            'temperature': params['temperature']
        }
        # max_tokens 为 None 时不传 maxOutputTokens，让模型自由输出
        if params.get('max_tokens') is not None:
            generation_config['maxOutputTokens'] = params['max_tokens']
        
        data = {
            'contents': contents,
            'generationConfig': generation_config
        }
        
        if system_instruction:
            data['systemInstruction'] = {
                'parts': [{'text': system_instruction}]
            }
        
        logger.debug(f"Gemini请求URL: {url[:80]}...")
        
        if params['stream']:
            # Gemini 流式接口
            stream_url = f"{api_base.rstrip('/')}/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
            return self._stream_gemini_response(stream_url, headers, data)
        else:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            result = response.json()
            
            if 'error' in result:
                error_msg = result['error'].get('message', str(result['error']))
                raise Exception(f"Gemini API错误: {error_msg}")
            
            if 'candidates' not in result or not result['candidates']:
                logger.error(f"Gemini API响应异常: {result}")
                raise Exception(f"API响应格式错误")
            
            content = result['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
            
            return {
                'content': content,
                'usage': result.get('usageMetadata', {})
            }
    
    def _stream_gemini_response(self, url, headers, data):
        """Gemini 流式响应处理"""
        response = requests.post(url, headers=headers, json=data, stream=True, timeout=120)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    line = line[6:]
                    try:
                        chunk = json.loads(line)
                        candidates = chunk.get('candidates', [])
                        if candidates:
                            parts = candidates[0].get('content', {}).get('parts', [])
                            if parts:
                                content = parts[0].get('text', '')
                                if content:
                                    yield content
                    except json.JSONDecodeError:
                        continue
    
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
        api_url = self.config.get('api_base_url') or 'https://open.bigmodel.cn/api/paas/v4'
        api_key = self.config.get('api_key')
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        # 兼容模型名映射（部分模型API名称可能不同）
        model_name = params['model']
        model_alias_map = {
            'glm-4.6v-flash': 'glm-4v-flash',
            'glm-4.6v': 'glm-4v'
        }
        
        # 视觉模型在智谱API中建议使用多模态content结构
        is_vision_model = any(k in model_name for k in ['4v', '6v', 'v-flash', 'vision'])
        if is_vision_model:
            normalized_messages = []
            for m in messages:
                content = m.get('content')
                if isinstance(content, str):
                    content = [{'type': 'text', 'text': content}]
                normalized_messages.append({**m, 'content': content})
        else:
            normalized_messages = messages
        
        # 智谱API max_tokens 上限限制（智谱最大4096）
        if params.get('max_tokens') is not None:
            zhipu_max_tokens = min(params['max_tokens'], 4096)
        else:
            zhipu_max_tokens = None
        
        if is_vision_model:
            # 视觉模型（glm-4v系列）只支持 model/messages/stream，不支持 max_tokens/temperature
            data = {
                'model': model_name,
                'messages': normalized_messages,
                'stream': params['stream']
            }
        else:
            data = {
                'model': model_name,
                'messages': normalized_messages,
                'temperature': params['temperature'],
                'stream': params['stream']
            }
            # max_tokens 为 None 时不传，让模型自由输出
            if zhipu_max_tokens is not None:
                data['max_tokens'] = zhipu_max_tokens
        
        url = f"{api_url.rstrip('/')}/chat/completions"
        logger.debug(f"智谱GLM请求URL: {url}, model: {model_name}, is_vision: {is_vision_model}, max_tokens: {zhipu_max_tokens if not is_vision_model else '(视觉模型不传)'}")
        
        def _post_once(payload):
            logger.info(f"[智谱GLM] 请求URL: {url}")
            logger.info(f"[智谱GLM] 请求体: model={payload.get('model')}, max_tokens={payload.get('max_tokens')}, temperature={payload.get('temperature')}, stream={payload.get('stream')}")
            logger.info(f"[智谱GLM] messages数量: {len(payload.get('messages', []))}")
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            resp_json = response.json()
            logger.info(f"[智谱GLM] 响应状态: {response.status_code}, 响应体: {json.dumps(resp_json, ensure_ascii=False)[:500]}")
            return resp_json
        
        if params['stream']:
            return self._stream_response(url, headers, data)
        else:
            result = _post_once(data)
            
            # 检查API错误响应
            if 'error' in result:
                error_msg = result['error'].get('message', str(result['error']))
                # 如果是参数错误且存在别名映射，尝试回退模型名
                if ('参数有误' in error_msg or 'parameter' in error_msg.lower()) and model_name in model_alias_map:
                    fallback_model = model_alias_map[model_name]
                    logger.warning(f"智谱模型名可能不支持: {model_name}，尝试回退为 {fallback_model}")
                    data['model'] = fallback_model
                    result = _post_once(data)
                    if 'error' in result:
                        error_msg = result['error'].get('message', str(result['error']))
                        raise Exception(f"智谱API错误: {error_msg}")
                else:
                    raise Exception(f"智谱API错误: {error_msg}")
            
            if 'choices' not in result:
                logger.error(f"智谱API响应异常: {result}")
                raise Exception(f"API响应格式错误: {result.get('msg', result.get('message', '未知错误'))}")
            
            content = result['choices'][0].get('message', {}).get('content')
            if content is None:
                logger.warning(f"[智谱API] content 为 null, finish_reason={result['choices'][0].get('finish_reason')}")
                content = ''
            
            return {
                'content': content,
                'usage': result.get('usage', {})
            }
    
    def _call_deepseek_api(self, messages, params):
        """调用DeepSeek API（兼容OpenAI格式）"""
        return self._call_openai_api(messages, params)
    
    def _call_ollama_api(self, messages, params):
        """
        调用 Ollama 本地模型 API
        
        Ollama 支持两种接口：
        1. OpenAI 兼容接口: /v1/chat/completions（优先使用）
        2. 原生接口: /api/chat
        
        Ollama 无需 API Key，默认运行在 localhost:11434
        """
        api_url = self.config.get('api_base_url') or 'http://localhost:11434'
        api_url = api_url.rstrip('/')
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        # 如果用户配置了 API Key（例如通过反向代理加了鉴权），也传递它
        api_key = self.config.get('api_key')
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        # 使用 OpenAI 兼容接口
        url = f"{api_url}/v1/chat/completions"
        
        data = {
            'model': params['model'],
            'messages': messages,
            'temperature': params['temperature'],
            'stream': params['stream']
        }
        
        # Ollama 的 max_tokens 对应 num_predict 参数，通过 options 传递
        # 但在 OpenAI 兼容模式下也支持 max_tokens
        # max_tokens 为 None 时不传，让模型自由输出
        if params.get('max_tokens') is not None:
            data['max_tokens'] = params['max_tokens']
        
        # 从 extra_params 中获取 Ollama 特有参数
        extra_params = self.config.get('extra_params', {}) or {}
        ollama_options = {}
        
        # 支持 Ollama 特有的模型参数
        if extra_params.get('num_ctx'):
            ollama_options['num_ctx'] = int(extra_params['num_ctx'])
        if extra_params.get('num_gpu'):
            ollama_options['num_gpu'] = int(extra_params['num_gpu'])
        if extra_params.get('top_p'):
            ollama_options['top_p'] = float(extra_params['top_p'])
        if extra_params.get('top_k'):
            ollama_options['top_k'] = int(extra_params['top_k'])
        if extra_params.get('repeat_penalty'):
            ollama_options['repeat_penalty'] = float(extra_params['repeat_penalty'])
        
        # 通过 options 字段传递 Ollama 特有参数（兼容模式下也支持）
        if ollama_options:
            data['options'] = ollama_options
        
        logger.info(f"[Ollama] 请求URL: {url}, model: {params['model']}")
        
        if params['stream']:
            return self._stream_response(url, headers, data)
        else:
            try:
                response = requests.post(url, headers=headers, json=data, timeout=300)
                logger.info(f"[Ollama] HTTP状态码: {response.status_code}, 响应内容: {response.text[:500]}")
                
                # 检查 HTTP 状态码
                if response.status_code != 200:
                    error_text = response.text[:300] if response.text else '无响应内容'
                    logger.error(f"[Ollama] HTTP错误: status={response.status_code}, body={error_text}")
                    raise Exception(f"Ollama API HTTP错误 ({response.status_code}): {error_text}")
                
                result = response.json()
                
                # 检查 API 错误
                if 'error' in result:
                    error_msg = result['error'] if isinstance(result['error'], str) else result['error'].get('message', str(result['error']))
                    raise Exception(f"Ollama API错误: {error_msg}")
                
                # 尝试从 OpenAI 兼容格式解析 (choices[].message.content)
                if 'choices' in result and result['choices']:
                    content = result['choices'][0].get('message', {}).get('content')
                    if content is None:
                        logger.warning(f"[Ollama API] choices[0].message.content 为 null")
                        content = ''
                    return {
                        'content': content,
                        'usage': result.get('usage', {})
                    }
                
                # Fallback: 尝试从 Ollama 原生格式解析 (message.content)
                # Ollama 的 /api/chat 返回格式: {"message": {"role": "assistant", "content": "..."}, ...}
                if 'message' in result and isinstance(result['message'], dict):
                    content = result['message'].get('content', '')
                    logger.info(f"[Ollama] 使用原生格式解析成功, content长度={len(content)}")
                    return {
                        'content': content,
                        'usage': result.get('usage', {})
                    }
                
                # Fallback: 尝试直接从 response 字段获取 (某些 Ollama 版本的 /api/generate 格式)
                if 'response' in result:
                    content = result['response'] or ''
                    logger.info(f"[Ollama] 使用 response 字段解析, content长度={len(content)}")
                    return {
                        'content': content,
                        'usage': result.get('usage', {})
                    }
                
                # 所有格式都无法匹配，记录完整响应信息用于调试
                response_keys = list(result.keys())
                logger.error(f"[Ollama] API响应格式无法识别: keys={response_keys}, 内容={str(result)[:500]}")
                raise Exception(
                    f"Ollama API响应格式错误: 响应中无 choices/message/response 字段, "
                    f"实际返回的字段: {response_keys}"
                )
            except requests.exceptions.ConnectionError:
                raise Exception(
                    f"无法连接到 Ollama 服务（{api_url}）。"
                    f"请确认：1) Ollama 已安装并启动（运行 'ollama serve'）；"
                    f"2) 服务地址和端口配置正确"
                )
            except requests.exceptions.Timeout:
                raise Exception(
                    f"Ollama API 请求超时（300秒）。可能是模型推理时间过长，"
                    f"请检查模型负载或尝试缩短输入内容"
                )
    
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
            'temperature': params['temperature'],
            'stream': params['stream']
        }
        # max_tokens 为 None 时不传，让模型自由输出
        if params.get('max_tokens') is not None:
            data['max_tokens'] = params['max_tokens']
        
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
