-- =====================================================
-- 修复向量嵌入表结构
-- 执行方式: mysql -u用户名 -p 数据库名 < fix_embedding_tables.sql
-- =====================================================

-- 1. 修改 document_embeddings 表的 document_id 字段类型
-- 从 INT/BIGINT 改为 VARCHAR(64)，支持 MD5 哈希字符串格式的文档ID
ALTER TABLE document_embeddings 
    MODIFY COLUMN document_id VARCHAR(64) NOT NULL COMMENT '文档ID（支持字符串格式如MD5哈希）';

-- 2. 修改 content_text 字段类型
-- 从 TEXT (最大 65535 字节) 改为 MEDIUMTEXT (最大 16MB)，避免内容过长导致截断
ALTER TABLE document_embeddings 
    MODIFY COLUMN content_text MEDIUMTEXT NOT NULL COMMENT '原始文本内容';

-- 3. 检查修改结果
SELECT 
    COLUMN_NAME, 
    DATA_TYPE, 
    CHARACTER_MAXIMUM_LENGTH,
    COLUMN_COMMENT
FROM information_schema.COLUMNS 
WHERE TABLE_NAME = 'document_embeddings' 
    AND COLUMN_NAME IN ('document_id', 'content_text');

-- =====================================================
-- 如果 chapters 表的 content 字段也需要扩容，执行以下语句：
-- =====================================================
-- ALTER TABLE chapters 
--     MODIFY COLUMN content MEDIUMTEXT COMMENT '章节内容';

-- 查看 chapters 表结构
-- DESCRIBE chapters;
