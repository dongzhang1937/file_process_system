# LLM匹配页面 — 后端架构文档（上篇：API路由层）

> 本文档完整梳理 `chat_doc.html` 前端页面调用的 **全部后端API**，按功能模块分组，标注每个API的传参、出参格式及调用的服务层方法。

---

## 总览

| 项目 | 说明 |
|------|------|
| 前端页面 | `file_process/templates/chat_doc.html` |
| API常量 | `const API_BASE = '/api/chat'` |
| 后端Blueprint 1 | `chatdoc` — 路由文件 `chat_db_doc.py`，路由前缀 `/api/chat` |
| 后端Blueprint 2 | `llm_bp` — 路由文件 `llm_routes.py`，路由前缀 `/llm` |
| 前端 fetch 调用总数 | **38个** |

---

## 模块一：SQL数据库配置管理（3个API）

### 1.1 获取SQL数据库配置列表

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/sql-db-config')` |
| HTTP方法 | `GET` |
| 路由 | `@llm_bp.route('/sql-db-config', methods=['GET'])` |
| 路由函数 | `get_sql_db_configs()` — llm_routes.py:1056 |
| 服务方法 | `SQLDBConfigManager.list_configs()` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "db_type": "mysql_centralized",
      "host": "127.0.0.1",
      "port": 3306,
      "database": "test_db",
      "username": "root",
      "password": "****",
      "enabled": true,
      "description": "MySQL集中式测试库",
      "created_at": "2025-01-01 12:00:00",
      "updated_at": "2025-01-01 12:00:00"
    }
  ]
}
```

---

### 1.2 保存/更新SQL数据库配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/sql-db-config', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@llm_bp.route('/sql-db-config', methods=['POST'])` |
| 路由函数 | `save_sql_db_config()` — llm_routes.py:1078 |
| 服务方法 | `SQLDBConfigManager.upsert_config(db_type, **kwargs)` |

**请求参数（JSON Body）：**
```json
{
  "db_type": "mysql_centralized",    // 必需, 枚举: mysql_centralized|mysql_distributed|pg_centralized|pg_distributed|oracle_centralized|oracle_distributed
  "host": "127.0.0.1",               // 必需
  "port": 3306,                      // 必需
  "database": "test_db",             // 必需
  "username": "root",                // 必需
  "password": "123456",              // 必需
  "enabled": true,                   // 可选, 默认true
  "description": "备注"              // 可选
}
```

**返回格式：**
```json
{
  "success": true,
  "message": "配置保存成功"
}
```

---

### 1.3 测试SQL数据库连接

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/sql-db-config/test', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@llm_bp.route('/sql-db-config/test', methods=['POST'])` |
| 路由函数 | `test_sql_db_connection()` — llm_routes.py:1146 |
| 服务方法 | `SQLDBConfigManager.test_connection(db_type, host, port, database, username, password)` |

**请求参数（JSON Body）：**
```json
{
  "db_type": "mysql_centralized",
  "host": "127.0.0.1",
  "port": 3306,
  "database": "test_db",
  "username": "root",
  "password": "123456"
}
```

**返回格式：**
```json
{
  "success": true,
  "message": "连接成功",
  "data": {
    "version": "8.0.31",
    "tables_count": 15
  }
}
```

---

## 模块二：Prompt/技能配置管理（4个API）

### 2.1 获取技能配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/skills-config?scene_type=${scene}')` |
| HTTP方法 | `GET` |
| 路由 | `@llm_bp.route('/skills-config', methods=['GET'])` |
| 路由函数 | `get_skills_configs()` — llm_routes.py:965 |
| 服务方法 | `SkillsConfigManager.list_configs(scene_type=None)` |

**请求参数（Query String）：**
| 参数名 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| scene_type | string | 否 | 场景类型过滤，枚举: `requirement_analysis`, `sql_extraction`, `sql_validation`, `web_search_summary`, `general` |

**返回格式：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "需求分析默认Prompt",
      "scene_type": "requirement_analysis",
      "prompt_template": "你是一个需求分析师...",
      "is_default": true,
      "variables": ["requirement", "documents"],
      "created_at": "2025-01-01 12:00:00"
    }
  ]
}
```

---

### 2.2 创建技能配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/skills-config', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@llm_bp.route('/skills-config', methods=['POST'])` |
| 路由函数 | `create_skills_config()` — llm_routes.py:991 |
| 服务方法 | `SkillsConfigManager.create_config(...)` |

**请求参数（JSON Body）：**
```json
{
  "name": "自定义SQL提取Prompt",     // 必需
  "scene_type": "sql_extraction",   // 必需
  "prompt_template": "请根据...",    // 必需
  "is_default": false,              // 可选
  "variables": ["requirement"]      // 可选, Prompt模板中的变量列表
}
```

**返回格式：**
```json
{
  "success": true,
  "data": { "id": 2 },
  "message": "配置创建成功"
}
```

---

### 2.3 更新技能配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/skills-config/${configId}', {method: 'PUT', ...})` |
| HTTP方法 | `PUT` |
| 路由 | `@llm_bp.route('/skills-config/<int:config_id>', methods=['PUT'])` |
| 路由函数 | `update_skills_config(config_id)` — llm_routes.py:1021 |
| 服务方法 | `SkillsConfigManager.update_config(config_id, **kwargs)` |

**请求参数（JSON Body）：** 同创建，所有字段可选

**返回格式：**
```json
{
  "success": true,
  "message": "配置更新成功"
}
```

---

### 2.4 删除技能配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/skills-config/${configId}', {method: 'DELETE'})` |
| HTTP方法 | `DELETE` |
| 路由 | `@llm_bp.route('/skills-config/<int:config_id>', methods=['DELETE'])` |
| 路由函数 | `delete_skills_config(config_id)` — llm_routes.py:1038 |
| 服务方法 | `SkillsConfigManager.delete_config(config_id)` |

**请求参数：** 路径参数 `config_id` (int)

**返回格式：**
```json
{
  "success": true,
  "message": "配置删除成功"
}
```

---

## 模块三：搜索引擎配置管理（3个API）

### 3.1 获取搜索引擎配置列表

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/search-config')` |
| HTTP方法 | `GET` |
| 路由 | `@llm_bp.route('/search-config', methods=['GET'])` |
| 路由函数 | `get_search_configs()` — llm_routes.py:132 |
| 服务方法 | `WebSearchConfigManager.list_configs()` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "engine_type": "duckduckgo",
      "config_name": "DuckDuckGo搜索",
      "api_key": null,
      "api_base": null,
      "is_default": true,
      "extra_config": null,
      "created_at": "2025-01-01 12:00:00"
    }
  ]
}
```

---

### 3.2 创建/更新搜索引擎配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch(url, {method: method, ...})` — url为 `/llm/search-config` (POST) 或 `/llm/search-config/${id}` (PUT) |
| HTTP方法 | `POST` / `PUT` |
| 路由 | `@llm_bp.route('/search-config', methods=['POST'])` 和 `@llm_bp.route('/search-config/<int:config_id>', methods=['PUT'])` |
| 路由函数 | `create_search_config()` — llm_routes.py:150 / `update_search_config(config_id)` — llm_routes.py:177 |
| 服务方法 | `WebSearchConfigManager.create_config(...)` / `WebSearchConfigManager.update_config(config_id, ...)` |

**请求参数（JSON Body）：**
```json
{
  "engine_type": "duckduckgo",        // 必需, 枚举: duckduckgo|google|baidu|bing|custom
  "config_name": "DuckDuckGo搜索",   // 必需
  "api_key": "xxx",                   // 可选
  "api_base": "https://...",          // 可选
  "is_default": true,                 // 可选
  "extra_config": {}                  // 可选
}
```

**返回格式：**
```json
{
  "success": true,
  "data": { "id": 1 },
  "message": "配置创建成功"
}
```

---

### 3.3 删除搜索引擎配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/search-config/${configId}', {method: 'DELETE'})` |
| HTTP方法 | `DELETE` |
| 路由 | `@llm_bp.route('/search-config/<int:config_id>', methods=['DELETE'])` |
| 路由函数 | `delete_search_config(config_id)` — llm_routes.py:194 |
| 服务方法 | `WebSearchConfigManager.delete_config(config_id)` |

**请求参数：** 路径参数 `config_id` (int)

**返回格式：**
```json
{
  "success": true,
  "message": "配置删除成功"
}
```

---

## 模块四：LLM大模型配置管理（4个API）

### 4.1 获取LLM配置列表

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/config')` |
| HTTP方法 | `GET` |
| 路由 | `@llm_bp.route('/config', methods=['GET'])` |
| 路由函数 | `get_llm_configs()` — llm_routes.py:33 |
| 服务方法 | `LLMConfigManager.list_configs()` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "config_name": "DeepSeek-V3",
      "model_type": "deepseek",
      "model_name": "deepseek-chat",
      "api_key": "sk-xxxx****",
      "api_base": "https://api.deepseek.com",
      "is_default": true,
      "temperature": 0.7,
      "max_tokens": 4096,
      "extra_params": {},
      "created_at": "2025-01-01 12:00:00"
    }
  ]
}
```

---

### 4.2 创建/更新LLM配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch(url, {method: method, ...})` — url为 `/llm/config` (POST) 或 `/llm/config/${id}` (PUT) |
| HTTP方法 | `POST` / `PUT` |
| 路由 | `@llm_bp.route('/config', methods=['POST'])` / `@llm_bp.route('/config/<int:config_id>', methods=['PUT'])` |
| 路由函数 | `create_llm_config()` — llm_routes.py:52 / `update_llm_config(config_id)` — llm_routes.py:89 |
| 服务方法 | `LLMConfigManager.create_config(...)` / `LLMConfigManager.update_config(config_id, ...)` |

**请求参数（JSON Body）：**
```json
{
  "config_name": "DeepSeek-V3",      // 必需
  "model_type": "deepseek",          // 必需, 枚举: openai|gemini|qianwen|wenxin|zhipu|deepseek|ollama|custom
  "model_name": "deepseek-chat",     // 必需
  "api_key": "sk-xxxx",              // 必需（ollama可为空）
  "api_base": "https://...",         // 可选
  "is_default": false,               // 可选
  "temperature": 0.7,                // 可选, 默认0.7
  "max_tokens": 4096,                // 可选
  "extra_params": {}                 // 可选, JSON对象
}
```

**返回格式：**
```json
{
  "success": true,
  "data": { "id": 1 },
  "message": "配置创建成功"
}
```

---

### 4.3 删除LLM配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/config/${configId}', {method: 'DELETE'})` |
| HTTP方法 | `DELETE` |
| 路由 | `@llm_bp.route('/config/<int:config_id>', methods=['DELETE'])` |
| 路由函数 | `delete_llm_config(config_id)` — llm_routes.py:106 |
| 服务方法 | `LLMConfigManager.delete_config(config_id)` |

**请求参数：** 路径参数 `config_id` (int)

**返回格式：**
```json
{
  "success": true,
  "message": "配置删除成功"
}
```

---

### 4.4 测试LLM配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('/llm/test', {method: 'POST', ...})` — 注：此fetch在LLM配置弹窗中（非直接列在38个主fetch中，但页面确有使用） |
| HTTP方法 | `POST` |
| 路由 | `@llm_bp.route('/test', methods=['POST'])` |
| 路由函数 | `test_llm()` — llm_routes.py:357 |
| 服务方法 | `LLMService(config).chat_completion(messages)` |

**请求参数（JSON Body）：**
```json
{
  "config_id": 1,                    // 可选, 测试已保存配置
  "model_type": "deepseek",          // 或直接传配置参数
  "model_name": "deepseek-chat",
  "api_key": "sk-xxxx",
  "api_base": "https://...",
  "prompt": "你好"                   // 可选, 测试用提示词
}
```

**返回格式：**
```json
{
  "success": true,
  "data": {
    "response": "你好！有什么可以帮助你的？",
    "model": "deepseek-chat",
    "usage": {
      "prompt_tokens": 5,
      "completion_tokens": 12,
      "total_tokens": 17
    }
  }
}
```

---

## 模块五：Embedding向量配置管理（8个API）

### 5.1 获取Embedding配置列表

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/embedding-configs')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/embedding-configs', methods=['GET'])` |
| 路由函数 | `get_embedding_configs()` — chat_db_doc.py:2989 |
| 服务方法 | `EmbeddingConfigManager.get_all_configs()` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "OpenAI Embedding",
      "provider": "openai",
      "model_name": "text-embedding-3-small",
      "dimensions": 1536,
      "api_key": "sk-xxxx****",
      "api_base": null,
      "is_default": true,
      "extra_config": null
    }
  ]
}
```

---

### 5.2 获取Embedding提供商列表

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/embedding-providers')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/embedding-providers', methods=['GET'])` |
| 路由函数 | `get_embedding_providers()` — chat_db_doc.py:3232 |
| 服务方法 | `EmbeddingConfigManager.get_providers()` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": {
    "openai": {
      "name": "OpenAI",
      "models": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
      "requires_key": true
    },
    "ollama": {
      "name": "Ollama (本地)",
      "models": ["nomic-embed-text", "mxbai-embed-large"],
      "requires_key": false
    }
  }
}
```

---

### 5.3 检查Embedding配置状态

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/embedding-config/check')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/embedding-config/check', methods=['GET'])` |
| 路由函数 | `check_embedding_config()` — chat_db_doc.py:3253 |
| 服务方法 | `EmbeddingConfigManager.get_default_config()` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": {
    "has_config": true,
    "config_name": "OpenAI Embedding",
    "provider": "openai",
    "model_name": "text-embedding-3-small"
  }
}
```

---

### 5.4 测试Embedding配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/embedding-config/test', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/embedding-config/test', methods=['POST'])` |
| 路由函数 | `test_embedding_config()` — chat_db_doc.py:3185 |
| 服务方法 | `EmbeddingConfigManager.test_config(config_id=None, config_data=None)` |

**请求参数（JSON Body）：**
```json
// 方式A: 测试已保存配置
{ "config_id": 1 }

// 方式B: 测试新配置
{
  "provider": "openai",
  "model_name": "text-embedding-3-small",
  "api_key": "sk-xxxx",
  "api_base": null,
  "dimensions": 1536,
  "extra_config": null
}
```

**返回格式：**
```json
{
  "success": true,
  "data": {
    "dimensions": 1536,
    "sample_vector": [0.01, -0.02, ...],
    "latency_ms": 320
  }
}
```

---

### 5.5 创建/更新Embedding配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch(url, {method: method, ...})` — url为 `${API_BASE}/embedding-config` (POST) 或 `${API_BASE}/embedding-config/${id}` (PUT) |
| HTTP方法 | `POST` / `PUT` |
| 路由 | `@chatdoc.route('/api/chat/embedding-config', methods=['POST'])` / `@chatdoc.route('/api/chat/embedding-config/<int:config_id>', methods=['PUT'])` |
| 路由函数 | `create_embedding_config()` — chat_db_doc.py:3041 / `update_embedding_config(config_id)` — chat_db_doc.py:3096 |
| 服务方法 | `EmbeddingConfigManager.create_config(...)` / `EmbeddingConfigManager.update_config(config_id, ...)` |

**请求参数（JSON Body）：**
```json
{
  "name": "OpenAI Embedding",         // 必需
  "provider": "openai",               // 必需
  "model_name": "text-embedding-3-small", // 必需
  "dimensions": 1536,                 // 可选, 默认1536
  "api_key": "sk-xxxx",               // 可选
  "api_base": "https://...",           // 可选
  "is_default": false,                 // 可选
  "extra_config": {}                   // 可选
}
```

**返回格式：**
```json
{
  "success": true,
  "data": { "id": 1 },
  "message": "配置创建成功"
}
```

---

### 5.6 设置默认Embedding配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/embedding-config/${configId}/set-default', {method: 'POST'})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/embedding-config/<int:config_id>/set-default', methods=['POST'])` |
| 路由函数 | `set_default_embedding_config(config_id)` — chat_db_doc.py:3158 |
| 服务方法 | `EmbeddingConfigManager.set_default(config_id)` |

**请求参数：** 路径参数 `config_id` (int)

**返回格式：**
```json
{
  "success": true,
  "message": "已设为默认配置"
}
```

---

### 5.7 删除Embedding配置

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/embedding-config/${configId}', {method: 'DELETE'})` |
| HTTP方法 | `DELETE` |
| 路由 | `@chatdoc.route('/api/chat/embedding-config/<int:config_id>', methods=['DELETE'])` |
| 路由函数 | `delete_embedding_config(config_id)` — chat_db_doc.py:3131 |
| 服务方法 | `EmbeddingConfigManager.delete_config(config_id)` |

**请求参数：** 路径参数 `config_id` (int)

**返回格式：**
```json
{
  "success": true,
  "message": "配置删除成功"
}
```

---

## 模块六：LLM查询与文档分析（5个API）

### 6.1 获取文档列表

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/documents')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/documents', methods=['GET'])` |
| 路由函数 | `get_documents()` — chat_db_doc.py:322 |
| 服务方法 | 直接SQL查询 `doc_process_records` 表 |

**请求参数：** 无（通过 session 获取当前用户）

**返回格式：**
```json
{
  "success": true,
  "data": [
    {
      "doc_id": 1,
      "filename": "技术规范.docx",
      "status": "completed",
      "upload_time": "2025-01-01 12:00:00",
      "file_size": 102400,
      "chapter_count": 15
    }
  ]
}
```

---

### 6.2 获取LLM配置列表（chat_doc专用）

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/llm-configs')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/llm-configs', methods=['GET'])` |
| 路由函数 | `get_llm_configs()` — chat_db_doc.py:2199 |
| 服务方法 | `LLMConfigManager.list_configs()` + `LLMConfigManager.SUPPORTED_MODELS` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "config_name": "DeepSeek-V3",
      "model_type": "deepseek",
      "model_name": "deepseek-chat",
      "api_key": "sk-xxxx****",
      "is_default": true,
      "supports_pdf": false
    }
  ]
}
```

> 注：`supports_pdf` 字段由路由函数根据 `SUPPORTED_MODELS` 元数据补充，标识该模型是否支持直接PDF分析（如 Gemini）。

---

### 6.3 检查LLM配置可用性

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/llm-config/check')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/llm-config/check', methods=['GET'])` |
| 路由函数 | `check_llm_config()` — chat_db_doc.py:2229 |
| 服务方法 | `LLMConfigManager.get_default_config()` |

**请求参数：** 无

**返回格式：**
```json
{
  "success": true,
  "data": {
    "has_config": true,
    "config_name": "DeepSeek-V3",
    "model_type": "deepseek",
    "model_name": "deepseek-chat"
  }
}
```

---

### 6.4 LLM智能匹配搜索（单条查询）

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/llm-search', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/llm-search', methods=['POST'])` |
| 路由函数 | `llm_search()` — chat_db_doc.py:1055 |
| 服务方法 | `RequirementAnalyzer(llm_config_id).analyze_requirement(query, username, document_ids, ...)` |

**请求参数（JSON Body）：**
```json
{
  "query": "系统应支持MySQL数据库",    // 必需, 查询需求文本
  "document_ids": [1, 2],             // 可选, 限定搜索的文档ID列表
  "enable_web_search": true,          // 可选, 默认true
  "llm_config_id": 1,                 // 可选, 指定LLM配置ID
  "enable_sql_validation": true,      // 可选, 默认true
  "sql_db_types": ["mysql_centralized", "pg_centralized"]  // 可选, 限定SQL验证的数据库类型
}
```

**返回格式：**
```json
{
  "success": true,
  "data": {
    "requirement": "系统应支持MySQL数据库",
    "answer": "经验证，系统支持MySQL数据库...",
    "match_type": "sql_validation",    // 枚举: exact|sql_validation|web_search|combined|llm_generated|none|error
    "source": "MySQL集中式数据库验证",
    "confidence": 0.95,
    "sql_results": {
      "mysql_centralized": {
        "success": true,
        "result": [...],
        "rows_count": 5,
        "db_name": "test_db"
      }
    },
    "web_results": null,
    "process_logs": [
      {"stage": "exact_match", "status": "no_match", "message": "文档中未找到精确匹配"},
      {"stage": "sql_validation", "status": "success", "message": "SQL验证通过"}
    ]
  }
}
```

---

### 6.5 上传需求文件并解析

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/analyze-file', {method: 'POST', body: formData})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/analyze-file', methods=['POST'])` |
| 路由函数 | `analyze_uploaded_file()` — chat_db_doc.py:1674 |
| 服务方法 | `RequirementAnalyzer.parse_requirements_from_file(file_path, section_filter, use_llm)` + `RequirementAnalyzer.parse_txt_as_tree(file_path)` (TXT) |

**请求参数（FormData）：**
| 字段名 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| file | File | 是 | 上传文件，支持 .docx / .txt / .pdf |
| document_ids[] | string[] | 否 | 关联文档ID列表 |
| llm_config_id | string | 否 | LLM配置ID |
| enable_web_search | string | 否 | "true"/"false"，默认"true" |
| enable_sql_validation | string | 否 | "true"/"false"，默认"true" |
| section_filter | string | 否 | 章节过滤，如 "1.4.1,1.4.2" |
| use_llm | string | 否 | "true"/"false"，是否用LLM智能识别章节，默认"false" |

**返回格式：**
```json
{
  "success": true,
  "data": {
    "requirements": [
      {
        "id": "req_1",
        "content": "系统应支持MySQL数据库",
        "section": "1.4.1",
        "section_title": "数据库要求",
        "level": 3,
        "parent_section": "1.4"
      }
    ],
    "count": 25,
    "temp_file": "/tmp/req_upload_admin_20250301120000.docx",
    "filename": "技术规范.docx",
    "section_filter": ["1.4.1", "1.4.2"],
    "enable_sql_validation": true,
    "tree_structure": {                // 仅TXT文件返回
      "tree": {...},
      "total_nodes": 50,
      "leaf_count": 25,
      "leaves": [...]
    }
  }
}
```

---

## 模块七：后台任务管理（5个API）

### 7.1 提交批量分析任务

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/task/submit', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/task/submit', methods=['POST'])` |
| 路由函数 | `submit_analysis_task()` — chat_db_doc.py:2002 |
| 服务方法 | `AnalysisTaskManager.create_task(username, requirements, params)` → `AnalysisTaskManager.start_task(task_id, flask_app)` |

**请求参数（JSON Body）：**
```json
{
  "requirements": [                   // 必需, 需求列表（来自analyze-file解析结果）
    {"id": "req_1", "content": "系统应支持MySQL", "section": "1.4.1"}
  ],
  "document_ids": [1, 2],            // 可选
  "enable_web_search": true,          // 可选, 默认true
  "enable_sql_validation": true,      // 可选, 默认true
  "sql_db_types": ["mysql_centralized"], // 可选
  "llm_config_id": 1,                // 可选
  "temp_file": "/tmp/req_upload_xxx.docx" // 可选, 关联的临时文件路径
}
```

**返回格式（成功 200）：**
```json
{
  "success": true,
  "data": {
    "task_id": "task_20250301120000_admin",
    "total": 25,
    "status": "running"
  },
  "message": "任务已提交，后台开始处理"
}
```

**返回格式（冲突 409 — 已有活跃任务）：**
```json
{
  "success": false,
  "error": "您已有一个正在执行的任务，请等待完成或取消后再提交",
  "active_task": {
    "task_id": "task_xxx",
    "status": "running",
    "total": 25,
    "current": 10
  }
}
```

---

### 7.2 查询任务状态（轮询）

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/task/${taskId}/status')` — 每2秒轮询 |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/task/<task_id>/status', methods=['GET'])` |
| 路由函数 | `get_task_status(task_id)` — chat_db_doc.py:2058 |
| 服务方法 | `AnalysisTaskManager.get_task_status(task_id)` |

**请求参数：** 路径参数 `task_id` (string)

**返回格式：**
```json
{
  "success": true,
  "data": {
    "task_id": "task_xxx",
    "status": "running",              // 枚举: pending|running|completed|failed|cancelled
    "total": 25,
    "current": 10,
    "current_title": "系统应支持MySQL数据库",
    "created_at": "2025-03-01 12:00:00",
    "started_at": "2025-03-01 12:00:01",
    "completed_at": null,
    "error": null
  }
}
```

---

### 7.3 获取任务完整结果

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/task/${taskId}/results')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/task/<task_id>/results', methods=['GET'])` |
| 路由函数 | `get_task_results(task_id)` — chat_db_doc.py:2074 |
| 服务方法 | `AnalysisTaskManager.get_task_results(task_id)` |

**请求参数：** 路径参数 `task_id` (string)

**返回格式：**
```json
{
  "success": true,
  "data": {
    "status": "completed",
    "total": 25,
    "current": 25,
    "results": [
      {
        "requirement": "系统应支持MySQL数据库",
        "answer": "...",
        "match_type": "sql_validation",
        "source": "...",
        "confidence": 0.95,
        "sql_results": {...},
        "web_results": null,
        "process_logs": [...]
      }
    ],
    "summary": {
      "total": 25,
      "exact": 5,
      "sql_validation": 12,
      "web_search": 3,
      "llm_generated": 3,
      "none": 2
    },
    "error": null
  }
}
```

---

### 7.4 取消任务

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/task/${currentTaskId}/cancel', {method: 'POST'})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/task/<task_id>/cancel', methods=['POST'])` |
| 路由函数 | `cancel_analysis_task(task_id)` — chat_db_doc.py:2100 |
| 服务方法 | `AnalysisTaskManager.cancel_task(task_id)` |

**请求参数：** 路径参数 `task_id` (string)

**返回格式：**
```json
{
  "success": true,
  "message": "任务已取消"
}
```

---

### 7.5 检查活跃任务（页面恢复）

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/task/active')` |
| HTTP方法 | `GET` |
| 路由 | `@chatdoc.route('/api/chat/task/active', methods=['GET'])` |
| 路由函数 | `get_active_task()` — chat_db_doc.py:2117 |
| 服务方法 | `AnalysisTaskManager.get_active_task(username)` |

**请求参数：** 无（通过 session 获取用户名）

**返回格式：**
```json
{
  "success": true,
  "data": {                           // 有活跃任务时
    "task_id": "task_xxx",
    "status": "running",
    "total": 25,
    "current": 10
  }
  // 或 "data": null                  // 无活跃任务时
}
```

---

## 模块八：导出功能（2个API）

### 8.1 导出LLM分析结果

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/export-llm-results', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/export-llm-results', methods=['POST'])` |
| 路由函数 | `export_llm_results()` — chat_db_doc.py:2154 |
| 服务方法 | `RequirementAnalyzer().export_to_word(results, title, requirement_tree, format_config)` |

**请求参数（JSON Body）：**
```json
{
  "results": [...],                   // 必需, 分析结果数组（同task results格式）
  "title": "需求分析报告",            // 可选, 默认"需求分析报告"
  "requirement_tree": {...},          // 可选, 需求树结构（用于层级导出）
  "format_config": {...}              // 可选, 格式配置（预留）
}
```

**返回格式：** Word文件下载 (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`)

---

### 8.2 导出招标作答结果

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/export-bid-answers', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/export-bid-answers', methods=['POST'])` |
| 路由函数 | `export_bid_answers()` — chat_db_doc.py:2691 |
| 服务方法 | `BidAnswerGenerator().export_to_word(results, title, doc_info)` 或 `export_to_word_table_format(...)` |

**请求参数（JSON Body）：**
```json
{
  "results": [...],                   // 必需, 作答结果列表
  "title": "招标技术要求应答书",       // 可选, 默认"招标技术要求应答书"
  "doc_info": {                       // 可选, 文档信息
    "filename": "招标文件.docx",
    "doc_id": 1
  },
  "format_type": "default"            // 可选, "default"|"table"
}
```

**返回格式：** Word文件下载

---

## 模块九：招标智能应答（3个API）

### 9.1 解析招标作答指令

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/parse-bid-instruction', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/parse-bid-instruction', methods=['POST'])` |
| 路由函数 | `parse_bid_instruction()` — chat_db_doc.py:2257 |
| 服务方法 | `UserInstructionParser().parse_instruction(instruction)` → `BidResponseGenerator().process_instruction(instruction, doc_id)` |

**请求参数（JSON Body）：**
```json
{
  "instruction": "针对文档中的1.4.1,1.4.2作答",   // 必需
  "doc_id": 1,                                    // 可选
  "file_path": "/path/to/file.docx"               // 可选
}
```

**返回格式：**
```json
{
  "success": true,
  "data": {
    "instruction_info": {
      "parsed": true,
      "action": "answer",
      "section_numbers": ["1.4.1", "1.4.2"],
      "raw_instruction": "针对文档中的1.4.1,1.4.2作答"
    },
    "section_numbers": ["1.4.1", "1.4.2"],
    "sections": {
      "1.4.1": {
        "title": "数据库要求",
        "requirements": [...]
      }
    }
  }
}
```

---

### 9.2 获取章节技术要求

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/get-section-requirements', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/get-section-requirements', methods=['POST'])` |
| 路由函数 | `get_section_requirements()` — chat_db_doc.py:2407 |
| 服务方法 | `BidDocumentParser(file_path).parse_document_structure()` → `get_all_requirements_from_section(num)` |

**请求参数（JSON Body）：**
```json
{
  "doc_id": 1,                                    // 必需
  "section_numbers": ["1.4.1", "1.4.2"]           // 必需
}
```

**返回格式：**
```json
{
  "success": true,
  "data": {
    "sections": {
      "1.4.1": {
        "title": "数据库要求",
        "requirements": [
          {"index": "1", "text": "支持MySQL 8.0+", "spec": "必需", "type": "list"}
        ]
      }
    },
    "total_requirements": 15,
    "found_sections": ["1.4.1", "1.4.2"],
    "missing_sections": [],
    "available_sections": ["1.1", "1.2", "1.3", "1.4", "1.4.1", "1.4.2"]
  }
}
```

---

### 9.3 执行招标需求智能作答

| 项目 | 内容 |
|------|------|
| 前端调用 | `fetch('${API_BASE}/answer-bid-requirements', {method: 'POST', ...})` |
| HTTP方法 | `POST` |
| 路由 | `@chatdoc.route('/api/chat/answer-bid-requirements', methods=['POST'])` |
| 路由函数 | `answer_bid_requirements()` — chat_db_doc.py:2525 |
| 服务方法 | `BidDocumentParser(file_path).parse_document_structure()` → `BidAnswerGenerator(llm_config_id).answer_requirements(all_requirements, username, knowledge_doc_ids, enable_web_search)` |

**请求参数（JSON Body）：**
```json
{
  "doc_id": 1,                        // 必需
  "section_numbers": ["1.4.1"],       // 必需
  "knowledge_doc_ids": [1, 2],        // 可选, 知识库文档ID
  "llm_config_id": 1,                 // 可选
  "enable_web_search": true,          // 可选, 默认true
  "export_format": "json"             // 可选, "json"|"word"|"word_table"
}
```

**返回格式（export_format="json"时）：**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "section_number": "1.4.1",
        "section_title": "数据库要求",
        "index": "1",
        "content": "支持MySQL 8.0+",
        "answer": "我方产品支持MySQL 8.0及以上版本...",
        "match_type": "exact",
        "source": "知识库文档",
        "confidence": 0.92
      }
    ],
    "summary": {
      "total": 15,
      "exact": 8,
      "semantic": 3,
      "web": 2,
      "llm_generated": 1,
      "none": 1
    },
    "doc_info": {
      "doc_id": 1,
      "filename": "招标文件.docx"
    }
  }
}
```

**返回格式（export_format="word"时）：** Word文件下载

---

## 前端fetch调用 → 后端路由 完整映射表

| # | 前端fetch URL | HTTP方法 | 后端路由函数 | 所在文件 | 行号 |
|---|---------------|----------|-------------|---------|------|
| 1 | `/llm/sql-db-config` | GET | `get_sql_db_configs()` | llm_routes.py | 1056 |
| 2 | `/llm/sql-db-config` | POST | `save_sql_db_config()` | llm_routes.py | 1078 |
| 3 | `/llm/sql-db-config/test` | POST | `test_sql_db_connection()` | llm_routes.py | 1146 |
| 4 | `/llm/skills-config?scene_type=` | GET | `get_skills_configs()` | llm_routes.py | 965 |
| 5 | `/llm/skills-config` | POST | `create_skills_config()` | llm_routes.py | 991 |
| 6 | `/llm/skills-config/:id` | PUT | `update_skills_config()` | llm_routes.py | 1021 |
| 7 | `/llm/skills-config/:id` | DELETE | `delete_skills_config()` | llm_routes.py | 1038 |
| 8 | `/llm/search-config` | GET | `get_search_configs()` | llm_routes.py | 132 |
| 9 | `/llm/search-config` | POST | `create_search_config()` | llm_routes.py | 150 |
| 10 | `/llm/search-config/:id` | PUT | `update_search_config()` | llm_routes.py | 177 |
| 11 | `/llm/search-config/:id` | DELETE | `delete_search_config()` | llm_routes.py | 194 |
| 12 | `/llm/config` | GET | `get_llm_configs()` | llm_routes.py | 33 |
| 13 | `/llm/config` | POST | `create_llm_config()` | llm_routes.py | 52 |
| 14 | `/llm/config/:id` | PUT | `update_llm_config()` | llm_routes.py | 89 |
| 15 | `/llm/config/:id` | DELETE | `delete_llm_config()` | llm_routes.py | 106 |
| 16 | `/api/chat/embedding-configs` | GET | `get_embedding_configs()` | chat_db_doc.py | 2989 |
| 17 | `/api/chat/embedding-providers` | GET | `get_embedding_providers()` | chat_db_doc.py | 3232 |
| 18 | `/api/chat/embedding-config/check` | GET | `check_embedding_config()` | chat_db_doc.py | 3253 |
| 19 | `/api/chat/embedding-config/test` | POST | `test_embedding_config()` | chat_db_doc.py | 3185 |
| 20 | `/api/chat/embedding-config` | POST | `create_embedding_config()` | chat_db_doc.py | 3041 |
| 21 | `/api/chat/embedding-config/:id` | PUT | `update_embedding_config()` | chat_db_doc.py | 3096 |
| 22 | `/api/chat/embedding-config/:id/set-default` | POST | `set_default_embedding_config()` | chat_db_doc.py | 3158 |
| 23 | `/api/chat/embedding-config/:id` | DELETE | `delete_embedding_config()` | chat_db_doc.py | 3131 |
| 24 | `/api/chat/documents` | GET | `get_documents()` | chat_db_doc.py | 322 |
| 25 | `/api/chat/llm-configs` | GET | `get_llm_configs()` | chat_db_doc.py | 2199 |
| 26 | `/api/chat/llm-config/check` | GET | `check_llm_config()` | chat_db_doc.py | 2229 |
| 27 | `/api/chat/llm-search` | POST | `llm_search()` | chat_db_doc.py | 1055 |
| 28 | `/api/chat/analyze-file` | POST | `analyze_uploaded_file()` | chat_db_doc.py | 1674 |
| 29 | `/api/chat/task/submit` | POST | `submit_analysis_task()` | chat_db_doc.py | 2002 |
| 30 | `/api/chat/task/:id/status` | GET | `get_task_status()` | chat_db_doc.py | 2058 |
| 31 | `/api/chat/task/:id/results` | GET | `get_task_results()` | chat_db_doc.py | 2074 |
| 32 | `/api/chat/task/:id/cancel` | POST | `cancel_analysis_task()` | chat_db_doc.py | 2100 |
| 33 | `/api/chat/task/active` | GET | `get_active_task()` | chat_db_doc.py | 2117 |
| 34 | `/api/chat/export-llm-results` | POST | `export_llm_results()` | chat_db_doc.py | 2154 |
| 35 | `/api/chat/export-bid-answers` | POST | `export_bid_answers()` | chat_db_doc.py | 2691 |
| 36 | `/api/chat/parse-bid-instruction` | POST | `parse_bid_instruction()` | chat_db_doc.py | 2257 |
| 37 | `/api/chat/get-section-requirements` | POST | `get_section_requirements()` | chat_db_doc.py | 2407 |
| 38 | `/api/chat/answer-bid-requirements` | POST | `answer_bid_requirements()` | chat_db_doc.py | 2525 |

---

> 下篇文档详细说明每个服务层类的方法签名、参数说明和内部调用关系。
