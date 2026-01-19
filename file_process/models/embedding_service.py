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
            SELECT id, name, provider, model_name, dimensions, 
                   is_default, is_active, created_at
            FROM embedding_configs
            ORDER BY is_default DESC, created_at DESC
        """
        return fetch_all(sql, ())
    
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


class VectorStore:
    """向量存储和检索"""
    
    def __init__(self, embedding_service: EmbeddingService = None):
        """
        初始化向量存储
        
        Args:
            embedding_service: Embedding 服务实例
        """
        self.embedding_service = embedding_service or EmbeddingService()
        self._faiss_index = None
        self._id_mapping = {}  # faiss_idx -> db_id
    
    @staticmethod
    def _vector_to_bytes(vector: List[float]) -> bytes:
        """将向量转换为二进制"""
        return struct.pack(f'{len(vector)}f', *vector)
    
    @staticmethod
    def _bytes_to_vector(data: bytes) -> List[float]:
        """将二进制转换为向量"""
        count = len(data) // 4  # float 是 4 字节
        return list(struct.unpack(f'{count}f', data))
    
    @staticmethod
    def _compute_content_hash(content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def add_document_embeddings(self, document_id: int, chapters: List[Dict],
                                 batch_size: int = 10) -> int:
        """
        为文档的章节生成并存储向量
        
        Args:
            document_id: 文档ID
            chapters: 章节列表 [{'id': 1, 'title': '...', 'content': '...', 'level': 1}, ...]
            batch_size: 批处理大小
        
        Returns:
            成功存储的向量数量
        """
        success_count = 0
        model_name = self.embedding_service.get_model_name()
        dimensions = self.embedding_service.get_dimensions()
        
        # 准备需要处理的内容
        to_embed = []
        for chapter in chapters:
            chapter_id = chapter.get('id')
            content = chapter.get('content', '') or chapter.get('title', '')
            
            if not content or len(content.strip()) < 10:
                continue
            
            content_hash = self._compute_content_hash(content)
            
            # 检查是否已存在相同内容的向量
            existing = fetch_one(
                "SELECT id FROM document_embeddings WHERE content_hash = %s AND embedding_model = %s",
                (content_hash, model_name)
            )
            
            if existing:
                continue
            
            # 准备元数据
            metadata = {
                'chapter_id': chapter_id,
                'title': chapter.get('title', ''),
                'level': chapter.get('level', 0),
                'path': chapter.get('path', [])
            }
            
            to_embed.append({
                'document_id': document_id,
                'chapter_id': chapter_id,
                'content': content[:2000],  # 限制长度
                'content_hash': content_hash,
                'metadata': metadata
            })
        
        if not to_embed:
            return 0
        
        # 批量生成向量
        for i in range(0, len(to_embed), batch_size):
            batch = to_embed[i:i + batch_size]
            texts = [item['content'] for item in batch]
            
            try:
                embeddings = self.embedding_service.embed_texts(texts)
                
                for item, embedding in zip(batch, embeddings):
                    # 存储到数据库
                    sql = """
                        INSERT INTO document_embeddings 
                        (document_id, chapter_id, content_type, content_hash, content_text,
                         content_summary, embedding, embedding_model, dimensions, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    params = (
                        item['document_id'],
                        item['chapter_id'],
                        'chapter',
                        item['content_hash'],
                        item['content'],
                        item['content'][:200],
                        self._vector_to_bytes(embedding),
                        model_name,
                        dimensions,
                        json.dumps(item['metadata'], ensure_ascii=False)
                    )
                    
                    try:
                        dml_sql(sql, params)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"存储向量失败: {e}")
                        
            except Exception as e:
                logger.error(f"批量生成向量失败: {e}")
        
        logger.info(f"文档 {document_id} 向量化完成，成功存储 {success_count} 条")
        return success_count
    
    def search_similar(self, query: str, document_ids: List[int] = None,
                       top_k: int = 10, threshold: float = 0.5) -> List[Dict]:
        """
        搜索相似内容
        
        Args:
            query: 查询文本
            document_ids: 限定的文档ID列表
            top_k: 返回结果数量
            threshold: 相似度阈值
        
        Returns:
            相似结果列表，包含相似度分数
        """
        # 生成查询向量
        query_embedding = self.embedding_service.embed_text(query)
        
        # 从数据库获取候选向量
        conditions = ["1=1"]
        params = []
        
        if document_ids:
            placeholders = ','.join(['%s'] * len(document_ids))
            conditions.append(f"document_id IN ({placeholders})")
            params.extend(document_ids)
        
        sql = f"""
            SELECT id, document_id, chapter_id, content_text, content_summary,
                   embedding, metadata
            FROM document_embeddings
            WHERE {' AND '.join(conditions)}
        """
        
        candidates = fetch_all(sql, params if params else None)
        
        if not candidates:
            return []
        
        # 计算相似度
        results = []
        query_np = np.array(query_embedding)
        query_norm = np.linalg.norm(query_np)
        
        for candidate in candidates:
            try:
                embedding = self._bytes_to_vector(candidate['embedding'])
                candidate_np = np.array(embedding)
                candidate_norm = np.linalg.norm(candidate_np)
                
                # 余弦相似度
                if query_norm > 0 and candidate_norm > 0:
                    similarity = np.dot(query_np, candidate_np) / (query_norm * candidate_norm)
                else:
                    similarity = 0
                
                if similarity >= threshold:
                    metadata = {}
                    if candidate.get('metadata'):
                        if isinstance(candidate['metadata'], str):
                            metadata = json.loads(candidate['metadata'])
                        else:
                            metadata = candidate['metadata']
                    
                    results.append({
                        'id': candidate['id'],
                        'document_id': candidate['document_id'],
                        'chapter_id': candidate['chapter_id'],
                        'content': candidate['content_text'],
                        'summary': candidate['content_summary'],
                        'similarity': float(similarity),
                        'metadata': metadata
                    })
                    
            except Exception as e:
                logger.error(f"计算相似度失败: {e}")
                continue
        
        # 按相似度排序
        results.sort(key=lambda x: x['similarity'], reverse=True)
        
        return results[:top_k]
    
    def delete_document_embeddings(self, document_id: int) -> int:
        """删除文档的所有向量"""
        sql = "DELETE FROM document_embeddings WHERE document_id = %s"
        return dml_sql(sql, (document_id,))
    
    def get_embedding_stats(self, document_id: int = None) -> Dict:
        """获取向量存储统计信息"""
        if document_id:
            sql = """
                SELECT COUNT(*) as count, 
                       COUNT(DISTINCT chapter_id) as chapter_count,
                       MAX(created_at) as last_updated
                FROM document_embeddings
                WHERE document_id = %s
            """
            result = fetch_one(sql, (document_id,))
        else:
            sql = """
                SELECT COUNT(*) as count,
                       COUNT(DISTINCT document_id) as document_count,
                       COUNT(DISTINCT chapter_id) as chapter_count,
                       MAX(created_at) as last_updated
                FROM document_embeddings
            """
            result = fetch_one(sql, ())
        
        return result or {}


# ==================== 便捷函数 ====================

def get_embedding_service(config_id: int = None) -> EmbeddingService:
    """获取 Embedding 服务实例"""
    return EmbeddingService(config_id)


def get_vector_store(config_id: int = None) -> VectorStore:
    """获取向量存储实例"""
    embedding_service = get_embedding_service(config_id)
    return VectorStore(embedding_service)


def embed_text(text: str, config_id: int = None) -> List[float]:
    """快捷方法：将文本转换为向量"""
    service = get_embedding_service(config_id)
    return service.embed_text(text)


def search_similar_content(query: str, document_ids: List[int] = None,
                           top_k: int = 10, config_id: int = None) -> List[Dict]:
    """快捷方法：搜索相似内容"""
    store = get_vector_store(config_id)
    return store.search_similar(query, document_ids, top_k)
