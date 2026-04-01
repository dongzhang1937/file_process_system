-- ============================================================
-- 批量分析任务表 - 后台任务模式
-- 任务在服务端独立运行，前端可刷新/关闭后恢复查看进度
-- ============================================================

CREATE TABLE IF NOT EXISTS `analysis_tasks` (
    `id` VARCHAR(36) PRIMARY KEY COMMENT '任务ID (UUID)',
    `username` VARCHAR(100) NOT NULL DEFAULT 'anonymous' COMMENT '提交用户',
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '任务状态: pending/running/completed/failed/cancelled',
    `total` INT NOT NULL DEFAULT 0 COMMENT '需求总条数',
    `current` INT NOT NULL DEFAULT 0 COMMENT '当前处理到第几条',
    `current_title` VARCHAR(200) DEFAULT '' COMMENT '当前正在处理的需求标题',
    `requirements_json` LONGTEXT COMMENT '提交的需求列表 JSON',
    `params_json` TEXT COMMENT '分析参数 JSON (document_ids, enable_web_search, etc.)',
    `results_json` LONGTEXT COMMENT '已完成的结果列表 JSON (逐条追加)',
    `summary_json` TEXT COMMENT '完成后的统计摘要 JSON',
    `error` TEXT COMMENT '错误信息',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `started_at` DATETIME DEFAULT NULL COMMENT '开始执行时间',
    `completed_at` DATETIME DEFAULT NULL COMMENT '完成/取消时间',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_task_status` (`status`),
    INDEX `idx_task_user` (`username`, `status`),
    INDEX `idx_task_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='批量需求分析后台任务表';
