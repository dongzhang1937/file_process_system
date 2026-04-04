-- =====================================================================
-- 用户隔离字段补齐 - 一次性迁移脚本
-- 修复所有配置表缺少的用户隔离列
-- 执行方式: mysql -u用户名 -p 数据库名 < sql/fix_user_isolation_columns.sql
-- =====================================================================

-- =====================================================================
-- 1. embedding_configs: 加 username 列（如果还不存在）
-- =====================================================================
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'embedding_configs' AND COLUMN_NAME = 'username');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `embedding_configs` ADD COLUMN `username` VARCHAR(100) NOT NULL DEFAULT ''asd'' COMMENT ''所属用户'' AFTER `id`',
    'SELECT ''embedding_configs.username already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 加索引（如果不存在）
SET @idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'embedding_configs' AND INDEX_NAME = 'idx_emb_username');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE `embedding_configs` ADD INDEX `idx_emb_username` (`username`, `is_active`)',
    'SELECT ''idx_emb_username already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- =====================================================================
-- 2. llm_configs: 加 username 列（如果还不存在）
-- =====================================================================
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'llm_configs' AND COLUMN_NAME = 'username');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `llm_configs` ADD COLUMN `username` VARCHAR(100) NOT NULL DEFAULT ''asd'' COMMENT ''所属用户(asd为管理员全局配置)'' AFTER `id`',
    'SELECT ''llm_configs.username already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'llm_configs' AND INDEX_NAME = 'idx_llm_username');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE `llm_configs` ADD INDEX `idx_llm_username` (`username`, `is_active`)',
    'SELECT ''idx_llm_username already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- =====================================================================
-- 3. web_search_configs: 加 username 列（如果还不存在）
-- =====================================================================
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'web_search_configs' AND COLUMN_NAME = 'username');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `web_search_configs` ADD COLUMN `username` VARCHAR(100) NOT NULL DEFAULT ''asd'' COMMENT ''所属用户'' AFTER `id`',
    'SELECT ''web_search_configs.username already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'web_search_configs' AND INDEX_NAME = 'idx_search_username');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE `web_search_configs` ADD INDEX `idx_search_username` (`username`, `is_active`)',
    'SELECT ''idx_search_username already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- =====================================================================
-- 4. sql_db_configs: 加 owner_username 列（代码用 owner_username 区分"谁拥有这条配置"）
--    注意: 表里原有的 username 列是"数据库连接的登录用户名"，含义不同
-- =====================================================================
SET @col_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sql_db_configs' AND COLUMN_NAME = 'owner_username');
SET @sql = IF(@col_exists = 0,
    'ALTER TABLE `sql_db_configs` ADD COLUMN `owner_username` VARCHAR(100) NOT NULL DEFAULT ''asd'' COMMENT ''配置所属用户(asd为管理员)'' AFTER `id`',
    'SELECT ''sql_db_configs.owner_username already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sql_db_configs' AND INDEX_NAME = 'idx_sqldb_owner');
SET @sql = IF(@idx_exists = 0,
    'ALTER TABLE `sql_db_configs` ADD INDEX `idx_sqldb_owner` (`owner_username`, `is_active`)',
    'SELECT ''idx_sqldb_owner already exists''');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- =====================================================================
-- 5. 同步更新 create_all_tables.sql 中 sql_db_configs 的字段名
--    代码中: username = 数据库登录用户名, owner_username = 配置所属用户
--    旧建表脚本混用了这两个概念，这里把旧数据库的 db_username 字段名统一
-- =====================================================================

-- 如果旧表里有 db_username 列但没有 username 列（表示用的是 create_all_tables.sql 建的），
-- 则不需要额外操作，因为 create_all_tables.sql 已经用 db_username 存数据库用户名

-- 如果旧表里只有 username（表示用的是 create_new_tables.sql 建的），
-- username 存的是数据库登录用户名，owner_username 上面已经加了

-- =====================================================================
-- 完成
-- =====================================================================
-- 此脚本可安全重复执行（每步都先检查列/索引是否存在）
-- 执行后所有配置表的用户隔离列补齐完毕
-- =====================================================================
