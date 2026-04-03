-- =====================================================================
-- 多用户配置隔离 - 数据库迁移脚本
-- 给配置表添加 username 字段，实现用户级配置隔离
-- 执行方式: mysql -u用户名 -p 数据库名 < migrate_user_isolation.sql
-- =====================================================================

-- 1. llm_configs 添加 username 字段
ALTER TABLE `llm_configs` 
    ADD COLUMN `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户(asd为管理员全局配置)' AFTER `id`;
ALTER TABLE `llm_configs` ADD INDEX `idx_llm_username` (`username`, `is_active`);

-- 2. web_search_configs 添加 username 字段
ALTER TABLE `web_search_configs` 
    ADD COLUMN `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户' AFTER `id`;
ALTER TABLE `web_search_configs` ADD INDEX `idx_search_username` (`username`, `is_active`);

-- 3. embedding_configs 添加 username 字段
ALTER TABLE `embedding_configs` 
    ADD COLUMN `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户' AFTER `id`;
ALTER TABLE `embedding_configs` ADD INDEX `idx_emb_username` (`username`, `is_active`);
-- 修改唯一键：name + username + is_active 组合唯一（不同用户可以同名）
ALTER TABLE `embedding_configs` DROP INDEX `uk_embedding_name`;
ALTER TABLE `embedding_configs` ADD UNIQUE KEY `uk_emb_name_user` (`name`, `username`, `is_active`);

-- 4. sql_db_configs 添加 username 字段
ALTER TABLE `sql_db_configs` 
    ADD COLUMN `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户' AFTER `id`;
ALTER TABLE `sql_db_configs` ADD INDEX `idx_sqldb_username` (`username`, `is_active`);
-- 修改唯一键：db_type + username + is_active 组合唯一（不同用户可以配同类型）
ALTER TABLE `sql_db_configs` DROP INDEX `uk_db_type`;
ALTER TABLE `sql_db_configs` ADD UNIQUE KEY `uk_db_type_user` (`db_type`, `username`, `is_active`);

-- 5. RAG 向量库用户隔离（PostgreSQL 表，需在 PG 中单独执行）
-- psql -h 127.0.0.1 -U t11 -d t1 -c "ALTER TABLE rag_documents ADD COLUMN IF NOT EXISTS username VARCHAR(100) NOT NULL DEFAULT 'asd';"
-- psql -h 127.0.0.1 -U t11 -d t1 -c "CREATE INDEX IF NOT EXISTS idx_rag_docs_username ON rag_documents(username);"

-- 6. upload_sessions 已有 username 字段，无需修改
-- 7. doc_process_records 已有 username 字段，无需修改

-- =====================================================================
-- 完成提示
-- =====================================================================
-- 迁移完成后，现有数据的 username 默认为 'asd'（管理员）
-- PostgreSQL 的 RAG 表需要单独在 PG 中执行 ALTER TABLE
-- =====================================================================
