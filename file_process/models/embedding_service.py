"""
Embedding 服务模块
支持多种 embedding 模型提供商，用于文档向量化和语义搜索

支持的提供商：
- OpenAI: text-embedding-ada-002, text-embedding-3-small, text-embedding-3-large
- 腾讯混元: hunyuan-embedding
- HuggingFace: BAAI/bge-large-zh-v1.5, BAAI/bge-m3 等
- 本地模型: sentence-transformers
"""
import os
import json
import hashlib
import struct
import numpy as np
from typing import List, Dict, Optional, Union, Tuple
from abc import ABC, abstractmethod
from datetime import datetime

from config.logging_config import logger
from config.db_config import fetch_one, fetch_all, dml_sql, dml_sql_with_insert_id


class EmbeddingProvider(ABC):
    """Embedding 提供商基类"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.model_name = config.get('model_name', '')
        self.dimensions = config.get('dimensions', 1536)
    
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """将单个文本转换为向量"""
        pass
    
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量将文本转换为向量"""
        pass
    
    def get_dimensions(self) -> int:
        """获取向量维度"""
        return self.dimensions


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI Embedding 提供商"""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.api_key = config.get('api_key', os.environ.get('OPENAI_API_KEY', ''))
        self.api_base = config.get('api_base', 'https://api.openai.com/v1')
        
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")
    
    def embed_text(self, text: str) -> List[float]:
        """单文本嵌入"""
        return self.embed_texts([text])[0]
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量文本嵌入"""
        import requests
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'input': texts,
            'model': self.model_name
        }
        
        try:
            response = requests.post(
                f'{self.api_base}/embeddings',
                headers=headers,
                json=data,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            
            # 按索引排序确保顺序正确
            embeddings = [None] * len(texts)
            for item in result['data']:
                embeddings[item['index']] = item['embedding']
            
            return embeddings
            
        except Exception as e:
            logger.error(f"OpenAI embedding 请求失败: {e}")
            raise


class HunyuanEmbedding(EmbeddingProvider):
    """腾讯混元 Embedding 提供商"""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        
        # 从 config 和 extra_config 中尝试获取凭证
        extra_config = config.get('extra_config') or {}
        if isinstance(extra_config, str):
            import json
            extra_config = json.loads(extra_config)
        
        # api_key 存储 secret_id, extra_config.secret_key 存储 secret_key
        self.secret_id = config.get('api_key') or config.get('secret_id') or os.environ.get('TENCENT_SECRET_ID', '')
        self.secret_key = extra_config.get('secret_key') or config.get('secret_key') or os.environ.get('TENCENT_SECRET_KEY', '')
        self.region = extra_config.get('region', 'ap-guangzhou')
        
        # 尝试从 LLM 配置获取
        if not self.secret_id or not self.secret_key:
            self._load_from_llm_config()
        
        # 验证凭证是否有效
        if not self.secret_id or not self.secret_key:
            raise ValueError("腾讯云凭证未配置（需要 Secret ID 和 Secret Key）")
    
    def _load_from_llm_config(self):
        """从 LLM 配置表加载凭证"""
        try:
            sql = """
                SELECT api_key, secret_key 
                FROM llm_configs 
                WHERE provider = 'hunyuan' AND is_active = 1
                LIMIT 1
            """
            result = fetch_one(sql, ())
            if result:
                self.secret_id = result.get('api_key', '')
                self.secret_key = result.get('secret_key', '')
        except Exception as e:
            logger.warning(f"从LLM配置加载凭证失败: {e}")
    
    def embed_text(self, text: str) -> List[float]:
        """单文本嵌入"""
        return self.embed_texts([text])[0]
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量文本嵌入"""
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.hunyuan.v20230901 import hunyuan_client, models
        except ImportError:
            raise ImportError("请安装腾讯云SDK: pip install tencentcloud-sdk-python")
        
        cred = credential.Credential(self.secret_id, self.secret_key)
        httpProfile = HttpProfile()
        httpProfile.endpoint = "hunyuan.tencentcloudapi.com"
        
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        client = hunyuan_client.HunyuanClient(cred, self.region, clientProfile)
        
        embeddings = []
        for text in texts:
            try:
                req = models.GetEmbeddingRequest()
                req.Input = text
                resp = client.GetEmbedding(req)
                embeddings.append(resp.Data[0].Embedding)
            except Exception as e:
                logger.error(f"混元embedding请求失败: {e}")
                raise
        
        return embeddings


class HuggingFaceEmbedding(EmbeddingProvider):
    """HuggingFace 本地模型 Embedding 提供商"""
    
    _model_cache = {}  # 模型缓存
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.device = config.get('extra_config', {}).get('device', 'cpu')
        self._model = None
        self._tokenizer = None
    
    def _load_model(self):
        """延迟加载模型"""
        if self._model is not None:
            return
        
        cache_key = f"{self.model_name}_{self.device}"
        if cache_key in self._model_cache:
            self._model, self._tokenizer = self._model_cache[cache_key]
            return
        
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"加载 HuggingFace 模型: {self.model_name}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._model_cache[cache_key] = (self._model, None)
            
            # 更新实际维度
            self.dimensions = self._model.get_sentence_embedding_dimension()
            
        except ImportError:
            raise ImportError("请安装 sentence-transformers: pip install sentence-transformers")
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            raise
    
    def embed_text(self, text: str) -> List[float]:
        """单文本嵌入"""
        self._load_model()
        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量文本嵌入"""
        self._load_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings.tolist()


class OllamaEmbedding(EmbeddingProvider):
    """Ollama Embedding 提供商（支持 bge-m3 等本地/远程 Ollama 模型）"""
    
    def __init__(self, config: Dict):
        super().__init__(config)
        extra = config.get('extra_config') or {}
        if isinstance(extra, str):
            extra = json.loads(extra)
        # api_base 存 Ollama 地址，如 http://119.45.183.233:11434
        self.api_base = (config.get('api_base') or extra.get('api_base', '')).rstrip('/')
        if not self.api_base:
            raise ValueError("Ollama 需要配置 api_base（如 http://119.45.183.233:11434）")
    
    def embed_text(self, text: str) -> List[float]:
        """单文本嵌入"""
        return self.embed_texts([text])[0]
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量文本嵌入 — 优先使用 /api/embed 批量接口"""
        import requests
        
        # 预处理所有文本
        clean_texts = [self._deduplicate_text(t) for t in texts]
        
        # 尝试批量接口（sentence-transformers 服务支持）
        try:
            resp = requests.post(
                f'{self.api_base}/api/embed',
                json={'model': self.model_name, 'input': clean_texts},
                timeout=120
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get('embeddings', [])
                if embeddings and len(embeddings) == len(texts):
                    if self.dimensions != len(embeddings[0]):
                        self.dimensions = len(embeddings[0])
                    return embeddings
        except Exception as e:
            logger.debug(f"Ollama 批量接口不可用，回退逐条: {e}")
        
        # 回退：逐条调用
        embeddings = []
        for text in clean_texts:
            embedding = self._embed_single_cleaned(text)
            embeddings.append(embedding)
        return embeddings
    
    def _embed_single_cleaned(self, clean_text: str) -> List[float]:
        """单条 embedding（已预处理的文本），带 NaN 防护和重试"""
        import requests
        
        try:
            resp = requests.post(
                f'{self.api_base}/api/embeddings',
                json={'model': self.model_name, 'prompt': clean_text},
                timeout=60
            )
            
            # 先检查是否是 NaN bug（不立即 raise）
            if resp.status_code == 500 and 'NaN' in resp.text:
                logger.warning(f"Ollama NaN bug 触发，尝试截断重试: len={len(clean_text)}")
                return self._embed_with_fallback(clean_text)
            
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get('embedding', [])
            if not embedding:
                raise ValueError(f"Ollama 返回空向量, response: {data}")
            if self.dimensions != len(embedding):
                self.dimensions = len(embedding)
            return embedding
            
        except Exception as e:
            # 任何异常都尝试 fallback
            if '500' in str(e) or 'NaN' in str(e):
                logger.warning(f"Ollama 异常，尝试 fallback: {e}")
                return self._embed_with_fallback(clean_text)
            logger.error(f"Ollama embedding 失败 ({self.model_name}): {e}")
            raise
    
    def _embed_with_fallback(self, text: str) -> List[float]:
        """NaN fallback：逐步截断文本直到成功，最终用零向量兜底"""
        import requests
        
        # 尝试不同的截断长度
        for max_len in [200, 100, 50]:
            try:
                short = text[:max_len] if len(text) > max_len else text + " query"
                resp = requests.post(
                    f'{self.api_base}/api/embeddings',
                    json={'model': self.model_name, 'prompt': short},
                    timeout=30
                )
                if resp.status_code == 200:
                    embedding = resp.json().get('embedding', [])
                    if embedding:
                        logger.info(f"Ollama NaN fallback 成功 (截断到 {max_len} 字符)")
                        return embedding
            except Exception:
                continue
        
        logger.warning(f"Ollama NaN fallback 全部失败，返回零向量")
        return [0.0] * self.dimensions
    
    @staticmethod
    def _deduplicate_text(text: str) -> str:
        """
        去除文本中过度重复的片段（防止 bge-m3 NaN bug）
        
        bge-m3 在 Ollama 上对高度重复/结构化的文本（如表格数据）会产生 NaN。
        策略：检测多种重复模式，去重后保留语义信息。
        """
        if len(text) < 50:
            return text
        
        import re
        
        # 1. 表格数据检测：含有大量 | 分隔符（典型的表格 chunk）
        pipe_count = text.count('|')
        if pipe_count > 10:
            # 按 | 或换行拆分，去重保留唯一片段
            segments = re.split(r'[|\n]', text)
            seen = set()
            unique_segments = []
            for seg in segments:
                seg = seg.strip()
                if seg and seg not in seen:
                    seen.add(seg)
                    unique_segments.append(seg)
            deduped = ' | '.join(unique_segments[:30])  # 最多保留 30 个唯一片段
            if len(deduped) < len(text) * 0.5:
                return deduped if deduped else text[:200]
        
        # 2. 行级别重复检测
        lines = text.split('\n')
        if len(lines) > 3:
            non_empty = [l.strip() for l in lines if l.strip()]
            unique_lines = set(non_empty)
            if len(unique_lines) < max(len(non_empty) * 0.4, 2):
                seen = set()
                deduped = []
                for line in non_empty:
                    if line not in seen:
                        seen.add(line)
                        deduped.append(line)
                text = '\n'.join(deduped)
        
        # 3. 短语级别重复检测（4-gram）
        if len(text) > 200:
            words = text.split()
            if len(words) > 20:
                ngram_count = {}
                for i in range(len(words) - 3):
                    ngram = ' '.join(words[i:i+4])
                    ngram_count[ngram] = ngram_count.get(ngram, 0) + 1
                # 如果任一 4-gram 重复超过 5 次，截断
                max_repeat = max(ngram_count.values()) if ngram_count else 0
                if max_repeat > 5:
                    text = text[:300]
        
        # 4. 字符级别重复检测
        unique_chars = set(text.replace(' ', '').replace('\n', ''))
        if len(unique_chars) < 15 and len(text) > 100:
            return text[:150]
        
        # 5. 最终长度限制（超长文本截断到合理范围）
        if len(text) > 1500:
            text = text[:1500]
        
        return text


class EmbeddingConfigManager:
    """Embedding 配置管理器"""
    
    # 支持的提供商信息
    SUPPORTED_PROVIDERS = {
        'openai': {
            'name': 'OpenAI',
            'models': [
                {'name': 'text-embedding-ada-002', 'dimensions': 1536},
                {'name': 'text-embedding-3-small', 'dimensions': 1536},
                {'name': 'text-embedding-3-large', 'dimensions': 3072}
            ],
            'requires_api_key': True
        },
        'hunyuan': {
            'name': '腾讯混元',
            'models': [
                {'name': 'hunyuan-embedding', 'dimensions': 1024}
            ],
            'requires_api_key': True,
            'note': '需要腾讯云 SecretId 和 SecretKey'
        },
        'huggingface': {
            'name': 'HuggingFace本地模型',
            'models': [
                {'name': 'BAAI/bge-large-zh-v1.5', 'dimensions': 1024},
                {'name': 'BAAI/bge-m3', 'dimensions': 1024},
                {'name': 'sentence-transformers/all-MiniLM-L6-v2', 'dimensions': 384}
            ],
            'requires_api_key': False,
            'note': '本地运行，首次使用需下载模型'
        },
        'ollama': {
            'name': 'Ollama',
            'models': [
                {'name': 'bge-m3:latest', 'dimensions': 1024},
                {'name': 'nomic-embed-text:latest', 'dimensions': 768},
                {'name': 'mxbai-embed-large:latest', 'dimensions': 1024}
            ],
            'requires_api_key': False,
            'note': '通过 Ollama 服务提供，需配置 api_base 地址'
        }
    }
    
    @staticmethod
    def get_supported_providers() -> Dict:
        """获取支持的提供商列表"""
        return EmbeddingConfigManager.SUPPORTED_PROVIDERS
    
    @staticmethod
    def get_config(config_id: int) -> Optional[Dict]:
        """获取指定ID的配置"""
        sql = """
            SELECT id, name, provider, model_name, api_key, api_base,
                   dimensions, is_default, is_active, extra_config
            FROM embedding_configs
            WHERE id = %s AND is_active = 1
        """
        result = fetch_one(sql, (config_id,))
        if result and result.get('extra_config'):
            if isinstance(result['extra_config'], str):
                result['extra_config'] = json.loads(result['extra_config'])
        return result
    
    @staticmethod
    def get_default_config() -> Optional[Dict]:
        """获取默认配置"""
        sql = """
            SELECT id, name, provider, model_name, api_key, api_base,
                   dimensions, is_default, is_active, extra_config
            FROM embedding_configs
            WHERE is_default = 1 AND is_active = 1
            LIMIT 1
        """
        result = fetch_one(sql, ())
        if result and result.get('extra_config'):
            if isinstance(result['extra_config'], str):
                result['extra_config'] = json.loads(result['extra_config'])
        return result
    
    @staticmethod
    def get_all_configs() -> List[Dict]:
        """获取所有配置"""
        sql = """
            SELECT id, name, provider, model_name, api_key, api_base, dimensions, 
                   is_default, is_active, created_at
            FROM embedding_configs
            ORDER BY is_default DESC, created_at DESC
        """
        configs = fetch_all(sql, ())
        # 脱敏 api_key
        for c in configs:
            if c.get('api_key'):
                c['api_key'] = c['api_key'][:4] + '****'
        return configs
    
    @staticmethod
    def create_config(name: str, provider: str, model_name: str,
                      dimensions: int, api_key: str = None, api_base: str = None,
                      is_default: bool = False, extra_config: Dict = None) -> int:
        """创建新配置"""
        if is_default:
            # 取消其他默认配置
            dml_sql("UPDATE embedding_configs SET is_default = 0 WHERE is_default = 1", ())
        
        sql = """
            INSERT INTO embedding_configs 
            (name, provider, model_name, api_key, api_base, dimensions, is_default, extra_config)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            name, provider, model_name, api_key, api_base, dimensions,
            1 if is_default else 0,
            json.dumps(extra_config) if extra_config else None
        )
        
        result = dml_sql_with_insert_id(sql, params)
        return result[0] if result else None
    
    @staticmethod
    def update_config(config_id: int, **kwargs) -> bool:
        """更新配置"""
        allowed_fields = ['name', 'provider', 'model_name', 'api_key', 'api_base',
                          'dimensions', 'is_default', 'is_active', 'extra_config']
        
        updates = []
        params = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                if field == 'extra_config' and value is not None:
                    value = json.dumps(value)
                if field == 'is_default' and value:
                    dml_sql("UPDATE embedding_configs SET is_default = 0 WHERE is_default = 1", ())
                updates.append(f"{field} = %s")
                params.append(value)
        
        if not updates:
            return False
        
        params.append(config_id)
        sql = f"UPDATE embedding_configs SET {', '.join(updates)} WHERE id = %s"
        affected = dml_sql(sql, params)
        return affected > 0
    
    @staticmethod
    def delete_config(config_id: int, soft_delete: bool = True) -> bool:
        """删除配置（默认软删除）"""
        if soft_delete:
            sql = "UPDATE embedding_configs SET is_active = 0 WHERE id = %s"
        else:
            sql = "DELETE FROM embedding_configs WHERE id = %s"
        affected = dml_sql(sql, (config_id,))
        return affected > 0
    
    @staticmethod
    def set_default(config_id: int) -> bool:
        """设置默认配置"""
        # 先取消所有默认
        dml_sql("UPDATE embedding_configs SET is_default = 0 WHERE is_default = 1", ())
        # 设置新默认
        sql = "UPDATE embedding_configs SET is_default = 1 WHERE id = %s AND is_active = 1"
        affected = dml_sql(sql, (config_id,))
        return affected > 0
    
    @staticmethod
    def test_config(config_id: int = None, config_data: Dict = None) -> Dict:
        """
        测试 Embedding 配置是否可用
        
        Args:
            config_id: 配置ID（从数据库获取配置）
            config_data: 配置数据（直接传入配置，用于测试新配置）
        
        Returns:
            {'success': True/False, 'message': '...', 'dimensions': 维度, 'sample_vector': [...]}
        """
        try:
            if config_id:
                config = EmbeddingConfigManager.get_config(config_id)
                if not config:
                    return {'success': False, 'message': '配置不存在或已禁用'}
            elif config_data:
                config = config_data
            else:
                return {'success': False, 'message': '请提供配置ID或配置数据'}
            
            # 创建临时的 embedding 服务进行测试
            provider_name = config.get('provider', '').lower()
            provider_class = EmbeddingService.PROVIDERS.get(provider_name)
            
            if not provider_class:
                return {'success': False, 'message': f'不支持的提供商: {provider_name}'}
            
            # 初始化提供商
            provider = provider_class(config)
            
            # 测试文本
            test_text = "这是一段用于测试Embedding模型的文本。"
            
            # 生成向量
            embedding = provider.embed_text(test_text)
            
            if not embedding or len(embedding) == 0:
                return {'success': False, 'message': '生成向量失败：返回空结果'}
            
            return {
                'success': True,
                'message': '测试成功！Embedding 服务可用。',
                'dimensions': len(embedding),
                'sample_vector_preview': embedding[:5],  # 只返回前5个值作为预览
                'provider': provider_name,
                'model': config.get('model_name', '')
            }
            
        except ImportError as e:
            return {'success': False, 'message': f'缺少依赖: {str(e)}'}
        except ValueError as e:
            return {'success': False, 'message': f'配置错误: {str(e)}'}
        except Exception as e:
            logger.error(f"测试 Embedding 配置失败: {e}")
            return {'success': False, 'message': f'测试失败: {str(e)}'}


class EmbeddingService:
    """统一的 Embedding 服务"""
    
    PROVIDERS = {
        'openai': OpenAIEmbedding,
        'hunyuan': HunyuanEmbedding,
        'huggingface': HuggingFaceEmbedding,
        'local': HuggingFaceEmbedding,
        'ollama': OllamaEmbedding,
    }
    
    def __init__(self, config_id: int = None):
        """
        初始化 Embedding 服务
        
        Args:
            config_id: 配置ID，为 None 则使用默认配置
        """
        self.config_id = config_id
        self.config = None
        self.provider = None
        self._init_provider()
    
    def _init_provider(self):
        """初始化提供商"""
        if self.config_id:
            self.config = EmbeddingConfigManager.get_config(self.config_id)
        else:
            self.config = EmbeddingConfigManager.get_default_config()
        
        if not self.config:
            logger.warning("未找到 Embedding 配置，将使用简单的词向量方案")
            self.provider = None
            return
        
        provider_name = self.config.get('provider', '').lower()
        provider_class = self.PROVIDERS.get(provider_name)
        
        if not provider_class:
            logger.warning(f"不支持的 Embedding 提供商: {provider_name}，将使用简单的词向量方案")
            self.provider = None
            return
        
        try:
            self.provider = provider_class(self.config)
            logger.info(f"Embedding 服务初始化成功: {self.config.get('name')}")
        except Exception as e:
            # 初始化失败时降级到简单方案
            logger.warning(f"Embedding 提供商初始化失败: {e}，将使用简单的词向量方案")
            self.provider = None
    
    def embed_text(self, text: str) -> List[float]:
        """将文本转换为向量"""
        if not self.provider:
            # 回退到简单的词频向量
            return self._simple_embed(text)
        
        return self.provider.embed_text(text)
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量将文本转换为向量"""
        if not self.provider:
            return [self._simple_embed(t) for t in texts]
        
        return self.provider.embed_texts(texts)
    
    def get_dimensions(self) -> int:
        """获取向量维度"""
        if self.provider:
            return self.provider.get_dimensions()
        return 256  # 简单方案的默认维度
    
    def get_model_name(self) -> str:
        """获取模型名称"""
        if self.config:
            return self.config.get('model_name', 'unknown')
        return 'simple_tfidf'
    
    def _simple_embed(self, text: str) -> List[float]:
        """简单的词频向量化（备用方案）"""
        # 使用字符级别的 hash 生成固定维度的向量
        import hashlib
        
        dim = 256
        vector = [0.0] * dim
        
        # 分词（简单的字符级别）
        chars = list(text.lower())
        
        for i, char in enumerate(chars):
            # 使用 hash 确定位置
            h = int(hashlib.md5(char.encode()).hexdigest(), 16)
            pos = h % dim
            # 使用位置权重
            weight = 1.0 / (1 + i * 0.01)
            vector[pos] += weight
        
        # L2 归一化
        norm = sum(v ** 2 for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]
        
        return vector

