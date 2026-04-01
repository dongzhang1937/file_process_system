-- ============================================================
-- 新增配置表 - MCP Server、Skills(Prompt模板)、SQL数据库连接
-- 执行前请确认已选择正确的数据库
-- ============================================================

-- 1. MCP Server 配置表
CREATE TABLE IF NOT EXISTS `mcp_server_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL COMMENT 'MCP Server名称',
    `endpoint` VARCHAR(500) NOT NULL COMMENT '端点地址(如stdio://或http://)',
    `transport_type` VARCHAR(20) NOT NULL DEFAULT 'stdio' COMMENT '传输类型: stdio/http',
    `tools_json` TEXT COMMENT '注册的工具列表(JSON数组)',
    `description` VARCHAR(500) DEFAULT '' COMMENT '描述',
    `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否有效(软删除)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_mcp_enabled` (`is_enabled`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MCP Server配置表';

-- 2. Skills 配置表（LLM System Prompt 模板管理）
CREATE TABLE IF NOT EXISTS `skills_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL COMMENT '模板名称',
    `scene_type` VARCHAR(50) NOT NULL COMMENT '场景类型: requirement_analysis/sql_extraction/sql_validation/web_search_summary/general',
    `system_prompt` TEXT NOT NULL COMMENT 'System Prompt模板内容，支持{{变量名}}占位符',
    `variables_json` TEXT COMMENT '变量定义JSON，如{"db_types":"全部","format":"详细"}',
    `is_default` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为该场景的默认模板(每个scene_type只能有一个)',
    `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否有效(软删除)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_skills_scene` (`scene_type`, `is_enabled`, `is_active`),
    INDEX `idx_skills_default` (`scene_type`, `is_default`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM Prompt模板配置表';

-- 3. SQL 数据库连接配置表
CREATE TABLE IF NOT EXISTS `sql_db_configs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `db_type` VARCHAR(30) NOT NULL COMMENT '数据库类型: mysql_centralized/mysql_distributed/pg_centralized/pg_distributed/oracle_centralized/oracle_distributed',
    `name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '配置名称/别名',
    `host` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '主机地址',
    `port` INT NOT NULL DEFAULT 0 COMMENT '端口',
    `username` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '用户名',
    `password` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '密码(建议加密存储)',
    `database_name` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '数据库名',
    `driver_type` VARCHAR(20) NOT NULL DEFAULT 'pymysql' COMMENT 'Python驱动: pymysql/psycopg2',
    `reuse_from` VARCHAR(30) DEFAULT NULL COMMENT 'Oracle类型复用的PG配置db_type标识(如pg_centralized)',
    `use_independent` TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Oracle类型是否使用独立连接(默认false即复用PG)',
    `is_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否有效(软删除)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_db_type` (`db_type`, `is_active`),
    INDEX `idx_sqldb_enabled` (`is_enabled`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SQL数据库连接配置表';

-- ============================================================
-- 预置 Skills 默认模板数据
-- ============================================================

INSERT INTO `skills_configs` (`name`, `scene_type`, `system_prompt`, `variables_json`, `is_default`, `is_enabled`) VALUES
('需求分析默认模板', 'requirement_analysis', 
'你是一个专业的需求分析助手。请分析以下需求项，判断其类型和匹配策略。\n\n需求内容：{{requirement}}\n\n请从以下维度分析：\n1. 需求类型（功能需求/性能需求/安全需求/兼容性需求/其他）\n2. 是否包含SQL语法要求\n3. 是否需要数据库验证\n4. 建议的匹配策略\n\n请以JSON格式返回结果。',
'{"requirement": "待分析的需求内容"}', 1, 1),

('SQL提取默认模板', 'sql_extraction',
'你是一个SQL语法专家。请从以下需求文本中识别和提取SQL语法要求。\n\n需求文本：{{requirement}}\n\n请提取：\n1. 需求中涉及的SQL语句或SQL特性\n2. 构造可用于验证的标准SQL语句\n3. 该SQL属于DDL/DML/DCL/TCL中的哪种类型\n\n目标数据库类型：{{db_types}}\n\n请以JSON格式返回：\n{"has_sql": true/false, "sql_statements": ["SQL1", "SQL2"], "sql_type": "DDL/DML/DCL/TCL", "description": "说明"}',
'{"requirement": "待分析的需求文本", "db_types": "全部"}', 1, 1),

('SQL验证结果判断默认模板', 'sql_validation',
'你是一个数据库兼容性专家。请根据以下SQL在{{db_count}}种数据库上的执行结果，判断各数据库对该SQL特性的支持情况。\n\n原始需求：{{requirement}}\nSQL语句：{{sql}}\n\n执行结果：\n{{results}}\n\n请对每种数据库给出判断：\n1. 是否支持该SQL特性（支持/不支持/部分支持）\n2. 判断依据\n3. 如有错误，分析错误原因\n\n请以JSON格式返回结果。',
'{"requirement": "原始需求", "sql": "执行的SQL", "db_count": "6", "results": "各数据库执行结果"}', 1, 1),

('搜索结果归纳默认模板', 'web_search_summary',
'你是一个专业的技术顾问。请根据以下网络搜索结果，针对用户的需求生成准确、结构化的答案。\n\n用户需求：{{requirement}}\n\n搜索结果：\n{{search_results}}\n\n要求：\n1. 综合多个搜索结果给出全面的答案\n2. 标注信息来源\n3. 如果搜索结果不足以回答，请说明\n4. 答案要简洁、专业',
'{"requirement": "用户需求", "search_results": "搜索结果内容"}', 1, 1),

('通用默认模板', 'general',
'你是一个专业的{{role}}。请根据以下要求完成任务：\n\n{{task}}\n\n请提供准确、专业的回答。',
'{"role": "技术顾问", "task": "待完成的任务描述"}', 1, 1);
