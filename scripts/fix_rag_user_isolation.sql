-- =====================================================================
-- RAG 向量库用户隔离字段补齐（PostgreSQL）
-- 修复 rag_documents 表缺少 username 列的问题
-- 执行方式: psql -h 127.0.0.1 -U t11 -d t1 -f scripts/fix_rag_user_isolation.sql
-- 此脚本可安全重复执行（IF NOT EXISTS / IF EXISTS 保护）
-- =====================================================================

-- 1. 给 rag_documents 加 username 列（如果还不存在）
ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS username VARCHAR(100) NOT NULL DEFAULT 'asd';

-- 2. 加索引（如果还不存在）
CREATE INDEX IF NOT EXISTS idx_rag_docs_username ON rag_documents(username);

-- 3. 确认结果
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'rag_documents' AND column_name = 'username';
