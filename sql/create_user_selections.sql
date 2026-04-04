-- =====================================================================
-- 用户配置选中表
-- 每个用户每种配置类型只能选中一条，实现多用户独立选择互不影响
-- 执行方式: mysql -u用户名 -p 数据库名 < sql/create_user_selections.sql
-- =====================================================================

CREATE TABLE IF NOT EXISTS `user_selected_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL COMMENT '用户名',
    `config_type` VARCHAR(30) NOT NULL COMMENT '配置类型: llm/embedding/search/sql_db',
    `config_id` INT NOT NULL COMMENT '选中的配置记录ID',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_user_type` (`username`, `config_type`),
    INDEX `idx_config_type` (`config_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户选中的配置（每种类型只能选一个）';
