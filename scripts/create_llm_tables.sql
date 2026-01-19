-- =====================================================
-- LLM配置和需求分析相关数据库表
-- 执行方式: mysql -u用户名 -p 数据库名 < create_llm_tables.sql
-- =====================================================

-- 1. LLM配置表（如果不存在则创建）
CREATE TABLE IF NOT EXISTS `llm_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `config_name` VARCHAR(100) NOT NULL COMMENT '配置名称',
    `model_type` VARCHAR(50) NOT NULL COMMENT '模型类型: openai/qianwen/wenxin/zhipu/deepseek/custom',
    `provider` VARCHAR(50) COMMENT '提供商: openai/hunyuan/qianwen/zhipu/custom',
    `api_base_url` VARCHAR(500) COMMENT 'API基础URL',
    `api_key` VARCHAR(500) NOT NULL COMMENT 'API密钥（或腾讯云SecretId）',
    `secret_key` VARCHAR(500) COMMENT '密钥（用于需要双密钥认证的服务，如腾讯云SecretKey）',
    `model_name` VARCHAR(100) NOT NULL COMMENT '模型名称',
    `max_tokens` INT DEFAULT 2048 COMMENT '最大token数',
    `temperature` DECIMAL(3,2) DEFAULT 0.70 COMMENT '温度参数',
    `is_default` TINYINT(1) DEFAULT 0 COMMENT '是否默认配置',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否激活',
    `extra_params` JSON COMMENT '额外参数(JSON格式)',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_model_type` (`model_type`),
    INDEX `idx_provider` (`provider`),
    INDEX `idx_is_default` (`is_default`),
    INDEX `idx_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM配置表';

-- 2. 网络搜索配置表
CREATE TABLE IF NOT EXISTS `web_search_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `search_engine` VARCHAR(50) NOT NULL COMMENT '搜索引擎: google/baidu/bing/custom',
    `api_url` VARCHAR(500) COMMENT 'API地址',
    `api_key` VARCHAR(500) NOT NULL COMMENT 'API密钥',
    `extra_params` JSON COMMENT '额外参数',
    `is_default` TINYINT(1) DEFAULT 0 COMMENT '是否默认配置',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否激活',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_search_engine` (`search_engine`),
    INDEX `idx_is_default` (`is_default`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网络搜索配置表';

-- 3. 文档问答会话表
CREATE TABLE IF NOT EXISTS `document_qa_sessions` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` VARCHAR(100) NOT NULL COMMENT '用户ID',
    `title` VARCHAR(200) COMMENT '会话标题',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档问答会话表';

-- 4. LLM问答记录表
CREATE TABLE IF NOT EXISTS `llm_qa_records` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `session_id` INT COMMENT '会话ID',
    `question` TEXT NOT NULL COMMENT '问题',
    `answer` TEXT COMMENT '回答',
    `source_type` VARCHAR(50) COMMENT '来源类型: document/web/llm_generated/none',
    `source_documents` JSON COMMENT '来源文档信息',
    `web_search_results` JSON COMMENT '网络搜索结果',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_session_id` (`session_id`),
    INDEX `idx_created_at` (`created_at`),
    FOREIGN KEY (`session_id`) REFERENCES `document_qa_sessions`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM问答记录表';

-- 5. 需求分析任务表（用于批量分析任务追踪）
CREATE TABLE IF NOT EXISTS `requirement_analysis_tasks` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` VARCHAR(100) NOT NULL COMMENT '用户ID',
    `filename` VARCHAR(255) COMMENT '上传的文件名',
    `total_requirements` INT DEFAULT 0 COMMENT '总需求数',
    `processed_count` INT DEFAULT 0 COMMENT '已处理数',
    `status` VARCHAR(20) DEFAULT 'pending' COMMENT '状态: pending/processing/completed/failed',
    `results` JSON COMMENT '分析结果',
    `error_message` TEXT COMMENT '错误信息',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `completed_at` DATETIME COMMENT '完成时间',
    INDEX `idx_user_id` (`user_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求分析任务表';

-- 6. 需求分析结果表（存储每条需求的分析结果）
CREATE TABLE IF NOT EXISTS `requirement_analysis_results` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `task_id` INT NOT NULL COMMENT '任务ID',
    `requirement_index` INT COMMENT '需求序号',
    `requirement_title` VARCHAR(500) COMMENT '需求标题',
    `requirement_content` TEXT COMMENT '需求内容',
    `answer` TEXT COMMENT '回答',
    `match_type` VARCHAR(50) COMMENT '匹配类型: exact/semantic/web/llm_generated/none',
    `confidence` DECIMAL(5,4) DEFAULT 0 COMMENT '置信度',
    `source_type` VARCHAR(50) COMMENT '来源类型: document/web/llm',
    `source_info` JSON COMMENT '来源详情',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_task_id` (`task_id`),
    INDEX `idx_match_type` (`match_type`),
    FOREIGN KEY (`task_id`) REFERENCES `requirement_analysis_tasks`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求分析结果表';

-- =====================================================
-- 示例：插入一个默认的LLM配置（可选）
-- =====================================================
-- INSERT INTO `llm_configs` 
-- (`config_name`, `model_type`, `api_base_url`, `api_key`, `model_name`, `is_default`)
-- VALUES 
-- ('默认OpenAI配置', 'openai', 'https://api.openai.com/v1', 'sk-your-api-key', 'gpt-3.5-turbo', 1);

-- =====================================================
-- 查看表结构
-- =====================================================
-- SHOW TABLES LIKE '%llm%';
-- SHOW TABLES LIKE '%requirement%';
-- SHOW TABLES LIKE '%document_qa%';
-- SHOW TABLES LIKE '%web_search%';
