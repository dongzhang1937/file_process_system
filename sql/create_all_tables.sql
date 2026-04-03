-- =====================================================================
-- 文档处理系统 - 全量 MySQL 建表脚本
-- 包含所有代码中实际使用的表，一键初始化新环境
-- 执行方式: mysql -u用户名 -p 数据库名 < create_all_tables.sql
-- 生成时间: 2026-04-01
-- =====================================================================

-- =====================================================================
-- 一、用户认证
-- =====================================================================

-- 1. 用户表
CREATE TABLE IF NOT EXISTS `user` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(50) NOT NULL COMMENT '用户名',
    `password` VARCHAR(255) NOT NULL COMMENT '密码',
    UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- =====================================================================
-- 二、文件上传
-- =====================================================================

-- 2. 上传会话表
CREATE TABLE IF NOT EXISTS `upload_sessions` (
    `upload_id` VARCHAR(64) PRIMARY KEY COMMENT '上传ID (MD5)',
    `filename` VARCHAR(500) NOT NULL COMMENT '文件名',
    `filesize` BIGINT NOT NULL DEFAULT 0 COMMENT '文件大小(字节)',
    `total_chunks` INT NOT NULL DEFAULT 0 COMMENT '总分片数',
    `uploaded_chunks` TEXT COMMENT '已上传分片列表(JSON数组)',
    `status` VARCHAR(20) NOT NULL DEFAULT 'initialized' COMMENT '状态: initialized/uploading/merging/completed/failed',
    `final_path` VARCHAR(1000) COMMENT '合并后的最终文件路径',
    `username` VARCHAR(100) NOT NULL DEFAULT 'anonymous' COMMENT '上传用户',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT NULL COMMENT '更新时间',
    `completed_at` DATETIME DEFAULT NULL COMMENT '完成时间',
    INDEX `idx_upload_username` (`username`),
    INDEX `idx_upload_status` (`status`),
    INDEX `idx_upload_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文件上传会话表';

-- =====================================================================
-- 三、文档处理（Word解析）
-- =====================================================================

-- 3. 文档处理记录表
CREATE TABLE IF NOT EXISTS `doc_process_records` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `doc_id` VARCHAR(64) NOT NULL COMMENT '文档ID(与upload_id关联)',
    `upload_id` VARCHAR(64) COMMENT '上传会话ID',
    `filename` VARCHAR(500) NOT NULL COMMENT '文件名',
    `file_path` VARCHAR(1000) NOT NULL COMMENT '文件路径',
    `username` VARCHAR(100) NOT NULL COMMENT '用户名',
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态: pending/processing/completed/failed',
    `process_result` TEXT COMMENT '处理结果(JSON)',
    `process_start_time` DATETIME DEFAULT NULL COMMENT '处理开始时间',
    `process_end_time` DATETIME DEFAULT NULL COMMENT '处理结束时间',
    `error_message` TEXT COMMENT '错误信息',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY `uk_doc_id` (`doc_id`),
    INDEX `idx_docproc_username` (`username`),
    INDEX `idx_docproc_status` (`status`),
    INDEX `idx_docproc_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档处理记录表';

-- 4. 章节表（Word文档解析结果）
CREATE TABLE IF NOT EXISTS `chapters` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `document_id` VARCHAR(64) NOT NULL COMMENT '文档ID(关联doc_process_records.doc_id)',
    `parent_id` INT DEFAULT NULL COMMENT '父章节ID',
    `level` INT NOT NULL DEFAULT 1 COMMENT '标题层级(1-9)',
    `order_index` INT NOT NULL DEFAULT 0 COMMENT '同级排序索引',
    `title` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '章节标题',
    `content` MEDIUMTEXT COMMENT '章节内容(含图片占位符)',
    `style_name` VARCHAR(100) COMMENT 'Word样式名称',
    `font_size` DECIMAL(5,1) COMMENT '字体大小(pt)',
    `is_bold` TINYINT(1) DEFAULT 0 COMMENT '是否加粗',
    `paragraph_index` INT DEFAULT 0 COMMENT '在文档中的段落索引',
    INDEX `idx_chapters_docid` (`document_id`),
    INDEX `idx_chapters_parent` (`parent_id`),
    INDEX `idx_chapters_level` (`level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档章节表';

-- 5. 文档图片表
CREATE TABLE IF NOT EXISTS `document_images` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `document_id` VARCHAR(64) NOT NULL COMMENT '文档ID',
    `image_name` VARCHAR(500) NOT NULL COMMENT '图片文件名',
    `image_path` VARCHAR(1000) NOT NULL COMMENT '图片物理路径',
    `image_url` VARCHAR(1000) COMMENT '图片访问URL',
    `image_type` VARCHAR(20) COMMENT '图片类型(png/jpeg等)',
    `paragraph_index` INT COMMENT '所在段落索引',
    `order_in_doc` INT COMMENT '在文档中的图片顺序',
    `file_size` BIGINT DEFAULT 0 COMMENT '文件大小(字节)',
    INDEX `idx_docimg_docid` (`document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档图片表';

-- 6. 章节-图片关联表
CREATE TABLE IF NOT EXISTS `chapter_images` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `chapter_id` INT NOT NULL COMMENT '章节ID',
    `image_id` INT NOT NULL COMMENT '图片ID',
    `position_in_chapter` INT DEFAULT 0 COMMENT '在章节内的位置顺序',
    INDEX `idx_chapimg_chapter` (`chapter_id`),
    INDEX `idx_chapimg_image` (`image_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='章节-图片关联表';

-- =====================================================================
-- 四、LLM 配置
-- =====================================================================

-- 7. LLM 配置表
CREATE TABLE IF NOT EXISTS `llm_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户(asd为管理员全局配置)',
    `config_name` VARCHAR(100) NOT NULL COMMENT '配置名称',
    `model_type` VARCHAR(50) NOT NULL COMMENT '模型类型',
    `provider` VARCHAR(50) COMMENT '提供商',
    `api_base_url` VARCHAR(500) COMMENT 'API基础URL',
    `api_key` VARCHAR(500) NOT NULL COMMENT 'API密钥',
    `secret_key` VARCHAR(500) COMMENT '双密钥认证',
    `model_name` VARCHAR(100) NOT NULL COMMENT '模型名称',
    `max_tokens` INT DEFAULT 2048 COMMENT '最大token数',
    `temperature` DECIMAL(3,2) DEFAULT 0.70 COMMENT '温度参数',
    `is_default` TINYINT(1) DEFAULT 0 COMMENT '是否默认配置',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否激活',
    `extra_params` JSON COMMENT '额外参数',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_llm_username` (`username`, `is_active`),
    INDEX `idx_llm_model_type` (`model_type`),
    INDEX `idx_llm_is_default` (`is_default`),
    INDEX `idx_llm_is_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM配置表';

-- 8. 网络搜索配置表
CREATE TABLE IF NOT EXISTS `web_search_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户',
    `search_engine` VARCHAR(50) NOT NULL COMMENT '搜索引擎',
    `api_url` VARCHAR(500) COMMENT 'API地址',
    `api_key` VARCHAR(500) COMMENT 'API密钥',
    `extra_params` JSON COMMENT '额外参数',
    `is_default` TINYINT(1) DEFAULT 0 COMMENT '是否默认配置',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否激活',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_search_username` (`username`, `is_active`),
    INDEX `idx_search_engine` (`search_engine`),
    INDEX `idx_search_is_default` (`is_default`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网络搜索配置表';

-- =====================================================================
-- 五、Embedding 配置
-- =====================================================================

-- 9. Embedding 模型配置表
CREATE TABLE IF NOT EXISTS `embedding_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户',
    `name` VARCHAR(100) NOT NULL COMMENT '配置名称',
    `provider` VARCHAR(50) NOT NULL COMMENT '提供商',
    `model_name` VARCHAR(100) NOT NULL COMMENT '模型名称',
    `api_key` TEXT COMMENT 'API密钥',
    `api_base` VARCHAR(255) COMMENT 'API基础URL',
    `dimensions` INT NOT NULL DEFAULT 1536 COMMENT '向量维度',
    `is_default` TINYINT(1) DEFAULT 0 COMMENT '是否默认配置',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `extra_config` JSON COMMENT '额外配置',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_emb_username` (`username`, `is_active`),
    UNIQUE KEY `uk_emb_name_user` (`name`, `username`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Embedding模型配置表';

-- 插入默认的 Embedding 配置
INSERT INTO `embedding_configs` (`name`, `provider`, `model_name`, `dimensions`, `is_default`, `extra_config`) VALUES
('OpenAI-Ada', 'openai', 'text-embedding-ada-002', 1536, 0, '{"max_tokens": 8191}'),
('OpenAI-3-Small', 'openai', 'text-embedding-3-small', 1536, 0, '{"max_tokens": 8191}'),
('OpenAI-3-Large', 'openai', 'text-embedding-3-large', 3072, 0, '{"max_tokens": 8191}'),
('HunyuanEmbedding', 'hunyuan', 'hunyuan-embedding', 1024, 1, '{"region": "ap-guangzhou"}'),
('BGE-Large-ZH', 'huggingface', 'BAAI/bge-large-zh-v1.5', 1024, 0, '{"device": "cpu"}'),
('BGE-M3', 'huggingface', 'BAAI/bge-m3', 1024, 0, '{"device": "cpu"}')
ON DUPLICATE KEY UPDATE `updated_at` = CURRENT_TIMESTAMP;

-- =====================================================================
-- 六、Skills / Prompt 模板 / SQL数据库连接
-- =====================================================================

-- 10. Skills 配置表（LLM Prompt 模板管理）
CREATE TABLE IF NOT EXISTS `skills_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL COMMENT '模板名称',
    `scene_type` VARCHAR(50) NOT NULL COMMENT '场景类型',
    `system_prompt` TEXT NOT NULL COMMENT 'Prompt模板内容，支持{{变量名}}占位符',
    `variables_json` TEXT COMMENT '变量定义JSON',
    `is_default` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为该场景的默认模板',
    `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否有效(软删除)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_skills_scene` (`scene_type`, `is_enabled`, `is_active`),
    INDEX `idx_skills_default` (`scene_type`, `is_default`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM Prompt模板配置表';

-- 11. SQL 数据库连接配置表
CREATE TABLE IF NOT EXISTS `sql_db_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户',
    `db_type` VARCHAR(30) NOT NULL COMMENT '数据库类型',
    `name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '配置名称/别名',
    `host` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '主机地址',
    `port` INT NOT NULL DEFAULT 0 COMMENT '端口',
    `db_username` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '数据库用户名',
    `password` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '密码',
    `database_name` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '数据库名',
    `driver_type` VARCHAR(20) NOT NULL DEFAULT 'pymysql' COMMENT 'Python驱动',
    `reuse_from` VARCHAR(30) DEFAULT NULL COMMENT 'Oracle类型复用的PG配置',
    `use_independent` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Oracle是否使用独立连接',
    `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否有效(软删除)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_sqldb_username` (`username`, `is_active`),
    UNIQUE KEY `uk_db_type_user` (`db_type`, `username`, `is_active`),
    INDEX `idx_sqldb_enabled` (`is_enabled`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SQL数据库连接配置表';

-- =====================================================================
-- 七、批量分析任务
-- =====================================================================

-- 12. 批量分析后台任务表
CREATE TABLE IF NOT EXISTS `analysis_tasks` (
    `id` VARCHAR(36) PRIMARY KEY COMMENT '任务ID (UUID)',
    `username` VARCHAR(100) NOT NULL DEFAULT 'anonymous' COMMENT '提交用户',
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '任务状态: pending/running/completed/failed/cancelled',
    `total` INT NOT NULL DEFAULT 0 COMMENT '需求总条数',
    `current` INT NOT NULL DEFAULT 0 COMMENT '当前处理到第几条',
    `current_title` VARCHAR(200) DEFAULT '' COMMENT '当前正在处理的需求标题',
    `requirements_json` LONGTEXT COMMENT '提交的需求列表 JSON',
    `params_json` TEXT COMMENT '分析参数 JSON',
    `results_json` LONGTEXT COMMENT '已完成的结果列表 JSON',
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

-- =====================================================================
-- 完成提示
-- =====================================================================
-- 共 12 张 MySQL 表
-- PostgreSQL RAG 向量库表请使用: scripts/create_rag_tables.sql
-- =====================================================================
