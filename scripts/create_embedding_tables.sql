-- 向量嵌入相关表结构
-- 用于存储文档章节的向量表示，支持语义搜索

-- Embedding 配置表
CREATE TABLE IF NOT EXISTS embedding_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT '配置名称',
    provider VARCHAR(50) NOT NULL COMMENT '提供商: openai, huggingface, local, hunyuan',
    model_name VARCHAR(100) NOT NULL COMMENT '模型名称',
    api_key TEXT COMMENT 'API密钥（加密存储）',
    api_base VARCHAR(255) COMMENT 'API基础URL',
    dimensions INT NOT NULL DEFAULT 1536 COMMENT '向量维度',
    is_default TINYINT(1) DEFAULT 0 COMMENT '是否默认配置',
    is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    extra_config JSON COMMENT '额外配置',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Embedding模型配置表';

-- 文档向量表
CREATE TABLE IF NOT EXISTS document_embeddings (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NOT NULL COMMENT '文档ID',
    chapter_id INT COMMENT '章节ID',
    content_type VARCHAR(20) NOT NULL DEFAULT 'chapter' COMMENT '内容类型: chapter, paragraph, table_row',
    content_hash VARCHAR(64) NOT NULL COMMENT '内容哈希（用于去重和更新检测）',
    content_text TEXT NOT NULL COMMENT '原始文本内容',
    content_summary VARCHAR(500) COMMENT '内容摘要',
    embedding LONGBLOB NOT NULL COMMENT '向量数据（二进制存储）',
    embedding_model VARCHAR(100) NOT NULL COMMENT '使用的embedding模型',
    dimensions INT NOT NULL COMMENT '向量维度',
    metadata JSON COMMENT '元数据（如：章节路径、标题等）',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_document_id (document_id),
    INDEX idx_chapter_id (chapter_id),
    INDEX idx_content_type (content_type),
    INDEX idx_content_hash (content_hash),
    INDEX idx_embedding_model (embedding_model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档向量存储表';

-- 向量搜索缓存表（可选，用于缓存热门查询结果）
CREATE TABLE IF NOT EXISTS embedding_search_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL COMMENT '查询哈希',
    query_text TEXT NOT NULL COMMENT '查询文本',
    query_embedding LONGBLOB COMMENT '查询向量',
    result_ids JSON NOT NULL COMMENT '结果ID列表',
    result_scores JSON NOT NULL COMMENT '相似度分数列表',
    search_scope JSON COMMENT '搜索范围（document_ids等）',
    hit_count INT DEFAULT 1 COMMENT '命中次数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP COMMENT '过期时间',
    INDEX idx_query_hash (query_hash),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='向量搜索缓存表';

-- 插入默认的 embedding 配置示例
INSERT INTO embedding_configs (name, provider, model_name, dimensions, is_default, extra_config) VALUES
('OpenAI-Ada', 'openai', 'text-embedding-ada-002', 1536, 0, '{"max_tokens": 8191}'),
('OpenAI-3-Small', 'openai', 'text-embedding-3-small', 1536, 0, '{"max_tokens": 8191}'),
('OpenAI-3-Large', 'openai', 'text-embedding-3-large', 3072, 0, '{"max_tokens": 8191}'),
('HunyuanEmbedding', 'hunyuan', 'hunyuan-embedding', 1024, 1, '{"region": "ap-guangzhou"}'),
('BGE-Large-ZH', 'huggingface', 'BAAI/bge-large-zh-v1.5', 1024, 0, '{"device": "cpu"}'),
('BGE-M3', 'huggingface', 'BAAI/bge-m3', 1024, 0, '{"device": "cpu"}')
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;
