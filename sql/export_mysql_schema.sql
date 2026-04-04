/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `_mcp_test_test_window_analysis` (
  `rank1` int DEFAULT NULL,
  `value1` int DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `analysis_tasks` (
  `id` varchar(36) NOT NULL COMMENT '任务ID (UUID)',
  `username` varchar(100) NOT NULL DEFAULT 'anonymous' COMMENT '提交用户',
  `status` varchar(20) NOT NULL DEFAULT 'pending' COMMENT '任务状态: pending/running/completed/failed/cancelled',
  `total` int NOT NULL DEFAULT '0' COMMENT '需求总条数',
  `current` int NOT NULL DEFAULT '0' COMMENT '当前处理到第几条',
  `current_title` varchar(200) DEFAULT '' COMMENT '当前正在处理的需求标题',
  `requirements_json` longtext COMMENT '提交的需求列表 JSON',
  `params_json` text COMMENT '分析参数 JSON (document_ids, enable_web_search, etc.)',
  `results_json` longtext COMMENT '已完成的结果列表 JSON (逐条追加)',
  `summary_json` text COMMENT '完成后的统计摘要 JSON',
  `error` text COMMENT '错误信息',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `started_at` datetime DEFAULT NULL COMMENT '开始执行时间',
  `completed_at` datetime DEFAULT NULL COMMENT '完成/取消时间',
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_task_status` (`status`),
  KEY `idx_task_user` (`username`,`status`),
  KEY `idx_task_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='批量需求分析后台任务表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `celery_taskmeta` (
  `id` int NOT NULL AUTO_INCREMENT,
  `task_id` varchar(155) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result` blob,
  `date_done` datetime DEFAULT NULL,
  `traceback` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `name` varchar(155) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `args` blob,
  `kwargs` blob,
  `worker` varchar(155) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `retries` int DEFAULT NULL,
  `queue` varchar(155) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `task_id` (`task_id`)
) ENGINE=InnoDB AUTO_INCREMENT=98 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `celery_tasksetmeta` (
  `id` int NOT NULL AUTO_INCREMENT,
  `taskset_id` varchar(155) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `result` blob,
  `date_done` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `taskset_id` (`taskset_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chapter_images` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '关联ID',
  `chapter_id` int NOT NULL COMMENT '章节ID (关联chapters.id)',
  `image_id` int NOT NULL COMMENT '图片ID (关联document_images.id)',
  `position_in_chapter` int DEFAULT '0' COMMENT '在章节内的位置 (0=第一个图片, 1=第二个图片, ...)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_chapter_image_position` (`chapter_id`,`image_id`,`position_in_chapter`),
  KEY `idx_chapter_id` (`chapter_id`),
  KEY `idx_image_id` (`image_id`)
) ENGINE=InnoDB AUTO_INCREMENT=14675 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='章节-图片关联表 - 记录图片属于哪个章节';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chapters` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '章节ID',
  `document_id` varchar(100) NOT NULL COMMENT '文档ID (关联doc_process_records.doc_id)',
  `parent_id` int DEFAULT NULL COMMENT '父章节ID (关联chapters.id，用于树形结构)',
  `level` int DEFAULT '1' COMMENT '目录层级: 1,2,3... (1=顶级章节)',
  `order_index` int DEFAULT '0' COMMENT '同级排序 (同级章节的显示顺序)',
  `title` varchar(500) NOT NULL COMMENT '章节标题',
  `content` text COMMENT '章节文本内容',
  `content_html` text COMMENT 'HTML格式内容 (保留格式)',
  `style_name` varchar(100) DEFAULT NULL COMMENT 'Word样式名称 (如: Heading 1, Heading 2, 标题1, 标题2)',
  `font_size` int DEFAULT NULL COMMENT '字体大小 (单位: 磅)',
  `is_bold` tinyint(1) DEFAULT '0' COMMENT '是否加粗',
  `paragraph_index` int DEFAULT NULL COMMENT '在Word中的段落索引 (用于定位原始位置)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_document_id` (`document_id`),
  KEY `idx_parent_id` (`parent_id`),
  KEY `idx_level` (`level`)
) ENGINE=InnoDB AUTO_INCREMENT=10948 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档章节表 - 树形结构存储目录';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chapters_copy1` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '章节ID',
  `document_id` varchar(100) NOT NULL COMMENT '文档ID (关联doc_process_records.doc_id)',
  `parent_id` int DEFAULT NULL COMMENT '父章节ID (关联chapters.id，用于树形结构)',
  `level` int DEFAULT '1' COMMENT '目录层级: 1,2,3... (1=顶级章节)',
  `order_index` int DEFAULT '0' COMMENT '同级排序 (同级章节的显示顺序)',
  `title` varchar(500) NOT NULL COMMENT '章节标题',
  `content` text COMMENT '章节文本内容',
  `content_html` text COMMENT 'HTML格式内容 (保留格式)',
  `style_name` varchar(100) DEFAULT NULL COMMENT 'Word样式名称 (如: Heading 1, Heading 2, 标题1, 标题2)',
  `font_size` int DEFAULT NULL COMMENT '字体大小 (单位: 磅)',
  `is_bold` tinyint(1) DEFAULT '0' COMMENT '是否加粗',
  `paragraph_index` int DEFAULT NULL COMMENT '在Word中的段落索引 (用于定位原始位置)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_document_id` (`document_id`),
  KEY `idx_parent_id` (`parent_id`),
  KEY `idx_level` (`level`)
) ENGINE=InnoDB AUTO_INCREMENT=2881 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档章节表 - 树形结构存储目录';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chapters_copy2` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '章节ID',
  `document_id` varchar(100) NOT NULL COMMENT '文档ID (关联doc_process_records.doc_id)',
  `parent_id` int DEFAULT NULL COMMENT '父章节ID (关联chapters.id，用于树形结构)',
  `level` int DEFAULT '1' COMMENT '目录层级: 1,2,3... (1=顶级章节)',
  `order_index` int DEFAULT '0' COMMENT '同级排序 (同级章节的显示顺序)',
  `title` varchar(500) NOT NULL COMMENT '章节标题',
  `content` text COMMENT '章节文本内容',
  `content_html` text COMMENT 'HTML格式内容 (保留格式)',
  `style_name` varchar(100) DEFAULT NULL COMMENT 'Word样式名称 (如: Heading 1, Heading 2, 标题1, 标题2)',
  `font_size` int DEFAULT NULL COMMENT '字体大小 (单位: 磅)',
  `is_bold` tinyint(1) DEFAULT '0' COMMENT '是否加粗',
  `paragraph_index` int DEFAULT NULL COMMENT '在Word中的段落索引 (用于定位原始位置)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_document_id` (`document_id`),
  KEY `idx_parent_id` (`parent_id`),
  KEY `idx_level` (`level`)
) ENGINE=InnoDB AUTO_INCREMENT=2881 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档章节表 - 树形结构存储目录';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `doc_process_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `doc_id` varchar(255) NOT NULL COMMENT '文档ID(对应upload_sessions的upload_id)',
  `upload_id` varchar(255) NOT NULL COMMENT '原始上传ID',
  `filename` varchar(255) NOT NULL COMMENT '文件名',
  `file_path` varchar(500) DEFAULT NULL COMMENT '文件路径',
  `username` varchar(100) DEFAULT 'anonymous' COMMENT '用户名',
  `status` enum('pending','processing','completed','failed') DEFAULT 'pending' COMMENT '处理状态',
  `process_result` text COMMENT '处理结果(JSON格式)',
  `process_start_time` datetime DEFAULT NULL COMMENT '处理开始时间',
  `process_end_time` datetime DEFAULT NULL COMMENT '处理结束时间',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `error_message` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_doc_id` (`doc_id`),
  KEY `idx_doc_id` (`doc_id`),
  KEY `idx_username` (`username`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=48 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档处理记录表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `document_embeddings` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `document_id` int NOT NULL COMMENT '文档ID',
  `chapter_id` int DEFAULT NULL COMMENT '章节ID',
  `content_type` varchar(20) NOT NULL DEFAULT 'chapter' COMMENT '内容类型: chapter, paragraph, table_row',
  `content_hash` varchar(64) NOT NULL COMMENT '内容哈希（用于去重和更新检测）',
  `content_text` text NOT NULL COMMENT '原始文本内容',
  `content_summary` varchar(500) DEFAULT NULL COMMENT '内容摘要',
  `embedding` longblob NOT NULL COMMENT '向量数据（二进制存储）',
  `embedding_model` varchar(100) NOT NULL COMMENT '使用的embedding模型',
  `dimensions` int NOT NULL COMMENT '向量维度',
  `metadata` json DEFAULT NULL COMMENT '元数据（如：章节路径、标题等）',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_document_id` (`document_id`),
  KEY `idx_chapter_id` (`chapter_id`),
  KEY `idx_content_type` (`content_type`),
  KEY `idx_content_hash` (`content_hash`),
  KEY `idx_embedding_model` (`embedding_model`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档向量存储表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `document_images` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '图片ID',
  `document_id` varchar(100) NOT NULL COMMENT '文档ID (关联doc_process_records.doc_id)',
  `image_name` varchar(255) DEFAULT NULL COMMENT '原始图片名',
  `image_path` varchar(500) NOT NULL COMMENT '存储路径 (服务器上的物理路径)',
  `image_url` varchar(500) DEFAULT NULL COMMENT '访问URL (浏览器可访问的URL路径)',
  `image_type` varchar(20) DEFAULT NULL COMMENT '图片格式 (如: png, jpg, gif等)',
  `width` int DEFAULT NULL COMMENT '原始宽度 (像素)',
  `height` int DEFAULT NULL COMMENT '原始高度 (像素)',
  `file_size` int DEFAULT NULL COMMENT '文件大小 (字节)',
  `paragraph_index` int DEFAULT NULL COMMENT '在Word中的段落索引 (用于定位原始位置)',
  `order_in_doc` int DEFAULT NULL COMMENT '在文档中的顺序 (从1开始)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_document_id` (`document_id`),
  KEY `idx_paragraph_index` (`paragraph_index`)
) ENGINE=InnoDB AUTO_INCREMENT=14675 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档图片表 - 存储Word中的所有图片';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `document_qa_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(100) NOT NULL COMMENT '用户ID',
  `title` varchar(200) DEFAULT NULL COMMENT '会话标题',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='文档问答会话表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `documents` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_size` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `upload_status` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `updated_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `embedding_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户',
  `name` varchar(100) NOT NULL COMMENT '配置名称',
  `provider` varchar(50) NOT NULL COMMENT '提供商: openai, huggingface, local, hunyuan',
  `model_name` varchar(100) NOT NULL COMMENT '模型名称',
  `api_key` text COMMENT 'API密钥（加密存储）',
  `api_base` varchar(255) DEFAULT NULL COMMENT 'API基础URL',
  `dimensions` int NOT NULL DEFAULT '1536' COMMENT '向量维度',
  `is_default` tinyint(1) DEFAULT '0' COMMENT '是否默认配置',
  `is_active` tinyint(1) DEFAULT '1' COMMENT '是否启用',
  `extra_config` json DEFAULT NULL COMMENT '额外配置',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name` (`name`),
  KEY `idx_emb_username` (`username`,`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='Embedding模型配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `embedding_search_cache` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `query_hash` varchar(64) NOT NULL COMMENT '查询哈希',
  `query_text` text NOT NULL COMMENT '查询文本',
  `query_embedding` longblob COMMENT '查询向量',
  `result_ids` json NOT NULL COMMENT '结果ID列表',
  `result_scores` json NOT NULL COMMENT '相似度分数列表',
  `search_scope` json DEFAULT NULL COMMENT '搜索范围（document_ids等）',
  `hit_count` int DEFAULT '1' COMMENT '命中次数',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` timestamp NULL DEFAULT NULL COMMENT '过期时间',
  PRIMARY KEY (`id`),
  KEY `idx_query_hash` (`query_hash`),
  KEY `idx_expires_at` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='向量搜索缓存表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `llm_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户(asd为管理员全局配置)',
  `config_name` varchar(100) NOT NULL COMMENT '配置名称',
  `model_type` varchar(50) NOT NULL COMMENT '模型类型: openai/qianwen/wenxin/zhipu/deepseek/custom',
  `provider` varchar(50) DEFAULT NULL COMMENT '提供商: openai/hunyuan/qianwen/zhipu/custom',
  `api_base_url` varchar(500) DEFAULT NULL COMMENT 'API基础URL',
  `api_key` varchar(500) NOT NULL COMMENT 'API密钥',
  `secret_key` varchar(500) DEFAULT NULL COMMENT '密钥（用于需要双密钥认证的服务）',
  `model_name` varchar(100) NOT NULL COMMENT '模型名称',
  `max_tokens` int DEFAULT '2048' COMMENT '最大token数',
  `temperature` decimal(3,2) DEFAULT '0.70' COMMENT '温度参数',
  `is_default` tinyint(1) DEFAULT '0' COMMENT '是否默认配置',
  `is_active` tinyint(1) DEFAULT '1' COMMENT '是否激活',
  `extra_params` json DEFAULT NULL COMMENT '额外参数(JSON格式)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_model_type` (`model_type`),
  KEY `idx_is_default` (`is_default`),
  KEY `idx_is_active` (`is_active`),
  KEY `idx_llm_username` (`username`,`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='LLM配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `llm_qa_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` int DEFAULT NULL COMMENT '会话ID',
  `question` text NOT NULL COMMENT '问题',
  `answer` text COMMENT '回答',
  `source_type` varchar(50) DEFAULT NULL COMMENT '来源类型: document/web/llm_generated/none',
  `source_documents` json DEFAULT NULL COMMENT '来源文档信息',
  `web_search_results` json DEFAULT NULL COMMENT '网络搜索结果',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_created_at` (`created_at`),
  CONSTRAINT `llm_qa_records_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `document_qa_sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='LLM问答记录表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mcp_server_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT 'MCP Server名称',
  `endpoint` varchar(500) NOT NULL COMMENT '端点地址(如stdio://或http://)',
  `transport_type` varchar(20) NOT NULL DEFAULT 'stdio' COMMENT '传输类型: stdio/http',
  `tools_json` text COMMENT '注册的工具列表(JSON数组)',
  `description` varchar(500) DEFAULT '' COMMENT '描述',
  `is_enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否有效(软删除)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_mcp_enabled` (`is_enabled`,`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='MCP Server配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `requirement_analysis_results` (
  `id` int NOT NULL AUTO_INCREMENT,
  `task_id` int NOT NULL COMMENT '任务ID',
  `requirement_index` int DEFAULT NULL COMMENT '需求序号',
  `requirement_title` varchar(500) DEFAULT NULL COMMENT '需求标题',
  `requirement_content` text COMMENT '需求内容',
  `answer` text COMMENT '回答',
  `match_type` varchar(50) DEFAULT NULL COMMENT '匹配类型: exact/semantic/web/llm_generated/none',
  `confidence` decimal(5,4) DEFAULT '0.0000' COMMENT '置信度',
  `source_type` varchar(50) DEFAULT NULL COMMENT '来源类型: document/web/llm',
  `source_info` json DEFAULT NULL COMMENT '来源详情',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_task_id` (`task_id`),
  KEY `idx_match_type` (`match_type`),
  CONSTRAINT `requirement_analysis_results_ibfk_1` FOREIGN KEY (`task_id`) REFERENCES `requirement_analysis_tasks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求分析结果表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `requirement_analysis_tasks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(100) NOT NULL COMMENT '用户ID',
  `filename` varchar(255) DEFAULT NULL COMMENT '上传的文件名',
  `total_requirements` int DEFAULT '0' COMMENT '总需求数',
  `processed_count` int DEFAULT '0' COMMENT '已处理数',
  `status` varchar(20) DEFAULT 'pending' COMMENT '状态: pending/processing/completed/failed',
  `results` json DEFAULT NULL COMMENT '分析结果',
  `error_message` text COMMENT '错误信息',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `completed_at` datetime DEFAULT NULL COMMENT '完成时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_status` (`status`),
  KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求分析任务表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skills_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL COMMENT '模板名称',
  `scene_type` varchar(50) NOT NULL COMMENT '场景类型: requirement_analysis/sql_extraction/sql_validation/web_search_summary/general',
  `system_prompt` text NOT NULL COMMENT 'System Prompt模板内容，支持{{变量名}}占位符',
  `variables_json` text COMMENT '变量定义JSON，如{"db_types":"全部","format":"详细"}',
  `is_default` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否为该场景的默认模板(每个scene_type只能有一个)',
  `is_enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否有效(软删除)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_skills_scene` (`scene_type`,`is_enabled`,`is_active`),
  KEY `idx_skills_default` (`scene_type`,`is_default`,`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='LLM Prompt模板配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sql_db_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `owner_username` varchar(100) NOT NULL DEFAULT 'asd' COMMENT '配置所属用户(asd为管理员)',
  `db_type` varchar(30) NOT NULL COMMENT '数据库类型: mysql_centralized/mysql_distributed/pg_centralized/pg_distributed/oracle_centralized/oracle_distributed',
  `name` varchar(100) NOT NULL DEFAULT '' COMMENT '配置名称/别名',
  `host` varchar(200) NOT NULL DEFAULT '' COMMENT '主机地址',
  `port` int NOT NULL DEFAULT '0' COMMENT '端口',
  `username` varchar(100) NOT NULL DEFAULT '' COMMENT '用户名',
  `password` varchar(500) NOT NULL DEFAULT '' COMMENT '密码(建议加密存储)',
  `database_name` varchar(200) NOT NULL DEFAULT '' COMMENT '数据库名',
  `driver_type` varchar(20) NOT NULL DEFAULT 'pymysql' COMMENT 'Python驱动: pymysql/psycopg2',
  `reuse_from` varchar(30) DEFAULT NULL COMMENT 'Oracle类型复用的PG配置db_type标识(如pg_centralized)',
  `use_independent` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'Oracle类型是否使用独立连接(默认false即复用PG)',
  `is_enabled` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否启用',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否有效(软删除)',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_db_type` (`db_type`,`is_active`),
  KEY `idx_sqldb_enabled` (`is_enabled`,`is_active`),
  KEY `idx_sqldb_owner` (`owner_username`,`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='SQL数据库连接配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `upload_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `upload_id` varchar(60) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'anonymous',
  `filename` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `filesize` bigint NOT NULL,
  `total_chunks` int NOT NULL,
  `uploaded_chunks` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `status` varchar(60) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'initialized',
  `final_path` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `completed_at` datetime DEFAULT NULL,
  `task_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unq_index` (`upload_id`)
) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `is_admin` int NOT NULL DEFAULT '0',
  `login_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_selected_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL COMMENT '用户名',
  `config_type` varchar(30) NOT NULL COMMENT '配置类型: llm/embedding/search/sql_db',
  `config_id` int NOT NULL COMMENT '选中的配置记录ID',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_type` (`username`,`config_type`),
  KEY `idx_config_type` (`config_type`)
) ENGINE=InnoDB AUTO_INCREMENT=35 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户选中的配置（每种类型只能选一个）';
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `web_search_configs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL DEFAULT 'asd' COMMENT '所属用户',
  `search_engine` varchar(50) NOT NULL COMMENT '搜索引擎: google/baidu/bing/custom',
  `api_url` varchar(500) DEFAULT NULL COMMENT 'API地址',
  `api_key` varchar(500) NOT NULL COMMENT 'API密钥',
  `extra_params` json DEFAULT NULL COMMENT '额外参数',
  `is_default` tinyint(1) DEFAULT '0' COMMENT '是否默认配置',
  `is_active` tinyint(1) DEFAULT '1' COMMENT '是否激活',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_search_engine` (`search_engine`),
  KEY `idx_is_default` (`is_default`),
  KEY `idx_search_username` (`username`,`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='网络搜索配置表';
/*!40101 SET character_set_client = @saved_cs_client */;
