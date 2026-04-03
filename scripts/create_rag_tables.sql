-- =====================================================
-- RAG 向量检索三层表结构（pgvector）
-- 目标库：127.0.0.1 / t1 (PG)
-- 执行：psql -h 127.0.0.1 -U t11 -d t1 -f create_rag_tables.sql
-- =====================================================

-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- ==================== 层级1: 文档表 ====================
CREATE TABLE IF NOT EXISTS rag_documents (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL DEFAULT 'asd',  -- 所属用户
    filename VARCHAR(500) NOT NULL,              -- 文件名
    filepath VARCHAR(1000),                      -- 文件完整路径
    file_hash VARCHAR(64),                       -- 文件内容哈希（用于去重/更新检测）
    product_name VARCHAR(200),                   -- 产品名（如 "TDSQL MySQL版"）
    doc_type VARCHAR(100),                       -- 文档类型（如 "白皮书", "运维手册"）
    total_sections INT DEFAULT 0,                -- 总章节数
    total_chunks INT DEFAULT 0,                  -- 总 chunk 数
    embedding_model VARCHAR(100),                -- 使用的 embedding 模型
    status VARCHAR(20) DEFAULT 'pending',        -- pending / processing / done / error
    error_message TEXT,                          -- 错误信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_docs_hash ON rag_documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_rag_docs_status ON rag_documents(status);
CREATE INDEX IF NOT EXISTS idx_rag_docs_product ON rag_documents(product_name);
CREATE INDEX IF NOT EXISTS idx_rag_docs_username ON rag_documents(username);

-- ==================== 层级2: 章节表 ====================
CREATE TABLE IF NOT EXISTS rag_sections (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    parent_section_id INT REFERENCES rag_sections(id) ON DELETE SET NULL,  -- 父章节（支持层级）
    title VARCHAR(500),                          -- 章节标题
    section_number VARCHAR(50),                  -- 章节编号（如 "3.2.1"）
    heading_level INT DEFAULT 1,                 -- 标题层级（1-6）
    full_path TEXT,                              -- 完整路径（如 "3 运维管理 > 3.2 备份恢复 > 3.2.1 全量备份"）
    content TEXT,                                -- 章节完整文本（父块内容）
    content_length INT DEFAULT 0,                -- 内容字符数
    chunk_count INT DEFAULT 0,                   -- 该章节下的 chunk 数
    section_order INT DEFAULT 0,                 -- 章节在文档中的顺序
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_sections_doc ON rag_sections(document_id);
CREATE INDEX IF NOT EXISTS idx_rag_sections_parent ON rag_sections(parent_section_id);

-- ==================== 层级3: 检索块表（核心） ====================
CREATE TABLE IF NOT EXISTS rag_chunks (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    section_id INT NOT NULL REFERENCES rag_sections(id) ON DELETE CASCADE,
    chunk_index INT DEFAULT 0,                   -- 在章节内的顺序
    content TEXT NOT NULL,                       -- chunk 文本内容
    content_length INT DEFAULT 0,                -- 字符数
    content_hash VARCHAR(64),                    -- 内容哈希（去重）
    embedding vector(1024),                      -- bge-m3 向量（1024维）
    metadata JSONB,                              -- 额外元数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_section ON rag_chunks(section_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_hash ON rag_chunks(content_hash);

-- HNSW 向量索引（加速检索，余弦相似度）
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding 
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);
