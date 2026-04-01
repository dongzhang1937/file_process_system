# LLM匹配页面 — 后端架构文档（下篇：服务层）

> 本文档详细说明 LLM匹配页面后端涉及的所有服务层类、方法签名、参数说明、返回值格式以及内部调用关系链。

---

## 服务层文件总览

| 文件 | 主要类/模块 | 行数 | 职责 |
|------|------------|------|------|
| `requirement_analyzer.py` | `RequirementAnalyzer` | 3577 | 核心分析引擎（需求解析、三阶段匹配、导出） |
| `llm_service.py` | `LLMService` | 1188 | 统一LLM调用（8种模型类型、Function Calling、流式） |
| `analysis_tasks.py` | `AnalysisTaskManager` | 389 | 后台任务管理（MySQL持久化 + Python线程） |
| `sql_validator.py` | `SQLValidator` | 612 | SQL安全验证与6库并行执行 |
| `function_tools.py` | 模块级函数 | 314 | Function Calling工具定义与执行 |
| `mcp_skills_config.py` | `SkillsConfigManager`, `SQLDBConfigManager`, `MCPServerConfigManager` | 628 | Prompt/技能/SQL数据库/MCP配置管理 |
| `llm_config.py` | `LLMConfigManager`, `WebSearchConfigManager` | 332 | LLM配置与搜索引擎配置管理 |
| `pdf_parser.py` | `PDFParser`, `DocumentParser` | 1692 | PDF/DOCX文档解析与章节提取 |
| `bid_requirement_extractor.py` | `BidRequirementExtractor`, `BidRequirementWordExporter` | 1128 | 招标需求提取与Word导出 |
| `embedding_service.py` | `EmbeddingConfigManager`, `EmbeddingService`, `VectorStore` | ~800 | Embedding配置管理、向量化、相似度搜索 |

---

## 一、RequirementAnalyzer — 核心分析引擎

**文件：** `file_process/models/requirement_analyzer.py` (3577行)

**工厂函数：** `get_requirement_analyzer(llm_config_id=None) -> RequirementAnalyzer`

### 1.1 公开方法

#### `__init__(self, llm_config_id=None)`
| 参数 | 类型 | 说明 |
|------|------|------|
| llm_config_id | int/None | LLM配置ID，None则使用默认配置 |

初始化内部属性：
- `self.llm_service` → `LLMService` 实例
- `self.sql_validator` → `SQLValidator` 实例
- `self.skills_manager` → `SkillsConfigManager` 实例

---

#### `parse_requirements_from_file(self, file_path, section_filter=None, use_llm=False) -> list[dict]`

解析需求文件，提取需求条目。

| 参数 | 类型 | 说明 |
|------|------|------|
| file_path | str | 文件路径（.docx / .txt / .pdf） |
| section_filter | list[str]/None | 章节过滤列表，如 `["1.4.1", "1.4.2"]` |
| use_llm | bool | 是否使用LLM智能识别章节，默认False |

**返回值：**
```python
[
    {
        "id": "req_1",              # 唯一ID
        "content": "系统应支持...",   # 需求文本
        "section": "1.4.1",         # 章节编号
        "section_title": "数据库要求", # 章节标题
        "level": 3,                 # 层级深度
        "parent_section": "1.4"     # 父章节编号
    }
]
```

**内部调用链：**
```
parse_requirements_from_file()
  ├─ 根据扩展名分发:
  │   ├─ .docx → _parse_docx_requirements(file_path, section_filter)
  │   ├─ .txt  → _parse_txt_requirements(file_path, section_filter)
  │   └─ .pdf  → _parse_pdf_requirements(file_path, section_filter, use_llm)
  └─ 返回需求列表
```

---

#### `analyze_requirement(self, requirement, user_id, document_ids=None, enable_web_search=True, enable_sql_validation=True, sql_db_types=None) -> dict`

单条需求三阶段分析（核心方法）。

| 参数 | 类型 | 说明 |
|------|------|------|
| requirement | str | 需求文本 |
| user_id | str | 用户名 |
| document_ids | list[int]/None | 限定搜索的文档ID列表 |
| enable_web_search | bool | 是否启用网络搜索，默认True |
| enable_sql_validation | bool | 是否启用SQL验证，默认True |
| sql_db_types | list[str]/None | 限定SQL验证的数据库类型 |

**返回值：**
```python
{
    "requirement": "系统应支持MySQL",
    "answer": "经验证，系统支持MySQL...",
    "match_type": "sql_validation",    # exact|sql_validation|web_search|combined|llm_generated|none|error
    "source": "MySQL集中式数据库验证",
    "confidence": 0.95,                # 0.0~1.0
    "sql_results": {                   # SQL验证结果（仅match_type含sql时有值）
        "mysql_centralized": {
            "success": True,
            "result": [...],
            "rows_count": 5,
            "db_type": "mysql_centralized",
            "db_name": "test_db"
        }
    },
    "web_results": None,               # 网络搜索结果
    "process_logs": [                  # 处理过程日志
        {"stage": "exact_match", "status": "no_match", "message": "..."},
        {"stage": "sql_validation", "status": "success", "message": "..."}
    ]
}
```

**三阶段调用链：**
```
analyze_requirement()
  │
  ├─ Stage 1: _exact_match_in_documents(requirement, user_id, document_ids)
  │   ├─ 查询 chapters 表进行文本精确匹配
  │   └─ 匹配成功 → 直接返回 match_type="exact"
  │
  ├─ Stage 2: _classify_and_process_unmatched(requirement, ...)
  │   ├─ SQLValidator.detect_sql_requirements(requirement) → 判断是否需要SQL验证
  │   ├─ 若需SQL验证 → _process_sql_requirement(requirement, sql_db_types)
  │   │   ├─ 检查Prompt配置 → SkillsConfigManager.get_prompt_for_scene("sql_extraction")
  │   │   ├─ Mode A (无自定义Prompt): _process_sql_with_function_calling()
  │   │   │   ├─ LLMService.chat_with_tools(messages, tools=[execute_sql, execute_sql_test])
  │   │   │   └─ function_tools.execute_tool("execute_sql"|"execute_sql_test", args)
  │   │   └─ Mode B (有自定义Prompt): _process_sql_with_custom_prompt()
  │   │       ├─ SkillsConfigManager.render_prompt(template, variables)
  │   │       ├─ LLMService.chat_completion(messages) → 解析JSON测试用例
  │   │       └─ SQLValidator.execute_test_sql_on_all(sql_statements, db_types)
  │   └─ 返回SQL验证结果
  │
  └─ Stage 3: _process_web_search_requirement(requirement)
      ├─ function_tools.execute_tool("web_search", {query: requirement})
      ├─ LLMService.chat_completion(messages)  → 总结搜索结果
      └─ 返回 match_type="web_search"
```

---

#### `analyze_requirements_batch(self, requirements, user_id, document_ids=None, enable_web_search=True, enable_sql_validation=True, sql_db_types=None, progress_callback=None) -> list[dict]`

批量分析需求（逐条调用 `analyze_requirement`）。

| 参数 | 类型 | 说明 |
|------|------|------|
| requirements | list[dict] | 需求列表，每项含 `content` 字段 |
| user_id | str | 用户名 |
| document_ids | list[int]/None | 文档ID列表 |
| enable_web_search | bool | 启用网络搜索 |
| enable_sql_validation | bool | 启用SQL验证 |
| sql_db_types | list[str]/None | 数据库类型 |
| progress_callback | callable/None | 进度回调 `callback(current, total, result)` |

**返回值：** `list[dict]` — 每个元素同 `analyze_requirement` 返回格式

---

#### `export_to_word(self, results, title='需求分析报告', requirement_tree=None, format_config=None) -> tuple[str, str]`

将分析结果导出为Word文档。

| 参数 | 类型 | 说明 |
|------|------|------|
| results | list[dict] | 分析结果列表 |
| title | str | 文档标题 |
| requirement_tree | dict/None | 需求树结构（用于层级输出） |
| format_config | dict/None | 格式配置（预留） |

**返回值：** `(filepath: str, filename: str)` — 生成的Word文件路径和文件名

---

#### `parse_txt_as_tree(self, file_path) -> dict`

解析TXT文件为树结构。

| 参数 | 类型 | 说明 |
|------|------|------|
| file_path | str | TXT文件路径 |

**返回值：**
```python
{
    "tree": {                          # 完整树结构
        "1": {
            "title": "总体要求",
            "children": {"1.1": {...}, "1.2": {...}}
        }
    },
    "total_nodes": 50,                 # 总节点数
    "leaf_count": 25,                  # 叶子节点数
    "leaves": [                        # 叶子节点列表
        {"id": "req_1", "content": "...", "section": "1.4.1"}
    ]
}
```

---

### 1.2 关键内部方法

| 方法 | 作用 | 调用者 |
|------|------|--------|
| `_exact_match_in_documents(requirement, user_id, document_ids)` | Stage 1: 文档精确匹配 | `analyze_requirement` |
| `_classify_and_process_unmatched(requirement, ...)` | 分类并处理未匹配需求 | `analyze_requirement` |
| `_process_sql_requirement(requirement, sql_db_types)` | Stage 2: SQL验证处理 | `_classify_and_process_unmatched` |
| `_process_sql_with_function_calling(requirement, sql_db_types)` | Mode A: Function Calling方式SQL验证 | `_process_sql_requirement` |
| `_process_sql_with_custom_prompt(requirement, sql_db_types, prompt_template)` | Mode B: 自定义Prompt方式SQL验证 | `_process_sql_requirement` |
| `_process_web_search_requirement(requirement)` | Stage 3: 网络搜索+LLM总结 | `_classify_and_process_unmatched` |
| `_parse_docx_requirements(file_path, section_filter)` | 解析DOCX文件需求 | `parse_requirements_from_file` |
| `_parse_txt_requirements(file_path, section_filter)` | 解析TXT文件需求 | `parse_requirements_from_file` |
| `_parse_pdf_requirements(file_path, section_filter, use_llm)` | 解析PDF文件需求 | `parse_requirements_from_file` |
| `_build_requirement_tree(requirements)` | 从扁平需求列表构建树结构 | `export_to_word` |

---

## 二、LLMService — 统一LLM调用

**文件：** `file_process/models/llm_service.py` (1188行)

### 2.1 公开方法

#### `__init__(self, config=None)`
| 参数 | 类型 | 说明 |
|------|------|------|
| config | dict/None | LLM配置字典，None则加载默认配置 |

配置字典格式：
```python
{
    "model_type": "deepseek",          # openai|gemini|qianwen|wenxin|zhipu|deepseek|ollama|custom
    "model_name": "deepseek-chat",
    "api_key": "sk-xxxx",
    "api_base": "https://api.deepseek.com",
    "temperature": 0.7,
    "max_tokens": 4096,
    "extra_params": {}
}
```

---

#### `chat_completion(self, messages, stream=False, **kwargs) -> dict | generator`

基础对话完成调用。

| 参数 | 类型 | 说明 |
|------|------|------|
| messages | list[dict] | OpenAI格式消息列表 `[{"role": "system"/"user"/"assistant", "content": "..."}]` |
| stream | bool | 是否流式输出 |
| **kwargs | dict | 额外参数（temperature, max_tokens等覆盖默认值） |

**返回值（非流式）：**
```python
{
    "content": "回复文本...",
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 200,
        "total_tokens": 300
    }
}
```

**返回值（流式）：** `generator` — 逐 chunk yield `{"content": "片段", "done": False}` ... `{"content": "", "done": True, "usage": {...}}`

**内部调用链：**
```
chat_completion()
  └─ 根据 self.model_type 分发:
      ├─ "openai"    → _call_openai_api(messages, stream, **kwargs)
      ├─ "gemini"    → _call_gemini_api(messages, stream, **kwargs)
      ├─ "qianwen"   → _call_qianwen_api(messages, stream, **kwargs)
      ├─ "wenxin"    → _call_wenxin_api(messages, stream, **kwargs)
      ├─ "zhipu"     → _call_zhipu_api(messages, stream, **kwargs)
      ├─ "deepseek"  → _call_deepseek_api(messages, stream, **kwargs)
      ├─ "ollama"    → _call_ollama_api(messages, stream, **kwargs)
      └─ "custom"    → _call_custom_api(messages, stream, **kwargs)
```

---

#### `chat_with_tools(self, messages, tools=None, tool_choice='auto', max_rounds=5, **kwargs) -> dict`

支持Function Calling的对话（自动循环执行工具调用）。

| 参数 | 类型 | 说明 |
|------|------|------|
| messages | list[dict] | 消息列表 |
| tools | list[dict]/None | 工具定义列表（OpenAI Function Calling格式） |
| tool_choice | str | "auto"/"none"/"required" |
| max_rounds | int | 最大工具调用轮次，默认5 |
| **kwargs | dict | 额外参数 |

**返回值：**
```python
{
    "content": "最终回复文本...",
    "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...},
    "tool_calls_log": [                # 工具调用日志
        {
            "tool_name": "execute_sql",
            "arguments": {"sql": "SELECT ...", "db_type": "mysql_centralized"},
            "result": {...}
        }
    ]
}
```

**内部调用链：**
```
chat_with_tools()
  └─ 循环 (max_rounds):
      ├─ _call_with_tools(messages, tools, tool_choice)  → LLM响应
      ├─ 检查是否有 tool_calls
      ├─ 有 → function_tools.execute_tool(name, args) → 将结果追加到messages
      └─ 无 → 返回最终结果
```

---

#### `analyze_pdf_with_gemini(self, pdf_path, prompt) -> dict`

使用Gemini的原生PDF理解能力分析PDF。

| 参数 | 类型 | 说明 |
|------|------|------|
| pdf_path | str | PDF文件路径 |
| prompt | str | 分析提示词 |

**返回值：** `{"content": "分析结果...", "usage": {...}}`

---

#### `analyze_pdf_with_zhipu(self, pdf_path, prompt) -> dict`

使用智谱的文档分析能力。参数和返回同上。

---

#### `supports_pdf(self) -> bool`

当前模型是否支持原生PDF分析。返回 `True`/`False`。

---

### 2.2 关键内部方法

| 方法 | 作用 |
|------|------|
| `_call_openai_api(messages, stream, **kwargs)` | 调用OpenAI兼容API |
| `_call_gemini_api(messages, stream, **kwargs)` | 调用Google Gemini API |
| `_call_qianwen_api(messages, stream, **kwargs)` | 调用通义千问 API |
| `_call_wenxin_api(messages, stream, **kwargs)` | 调用百度文心 API |
| `_call_zhipu_api(messages, stream, **kwargs)` | 调用智谱 API |
| `_call_deepseek_api(messages, stream, **kwargs)` | 调用DeepSeek API |
| `_call_ollama_api(messages, stream, **kwargs)` | 调用本地Ollama API |
| `_call_custom_api(messages, stream, **kwargs)` | 调用自定义OpenAI兼容API |
| `_call_with_tools(messages, tools, tool_choice)` | Function Calling单轮调用 |
| `_analyze_parsed_content(content, prompt)` | 分析已解析的长文本内容 |
| `_split_content_by_segments(content, max_length)` | 长文本分段 |
| `_merge_chapter_results(results)` | 合并多段分析结果 |

---

## 三、AnalysisTaskManager — 后台任务管理

**文件：** `file_process/models/analysis_tasks.py` (389行)

> 所有方法均为 `@classmethod`

### 3.1 方法列表

#### `create_task(cls, username, requirements, params) -> str`

创建分析任务记录（写入MySQL `analysis_tasks` 表）。

| 参数 | 类型 | 说明 |
|------|------|------|
| username | str | 用户名 |
| requirements | list[dict] | 需求列表 |
| params | dict | 任务参数 `{document_ids, enable_web_search, enable_sql_validation, sql_db_types, llm_config_id, temp_file}` |

**返回值：** `str` — 任务ID（格式: `task_{timestamp}_{username}`）

---

#### `start_task(cls, task_id, flask_app) -> None`

启动后台分析线程。

| 参数 | 类型 | 说明 |
|------|------|------|
| task_id | str | 任务ID |
| flask_app | Flask | Flask应用实例（用于获取app context） |

**内部调用：** 创建 `threading.Thread(target=_run_task)` 并启动

---

#### `_run_task(cls, task_id, flask_app)` (内部方法)

后台线程执行体。

**调用链：**
```
_run_task()
  ├─ 从DB读取 requirements_json, params_json
  ├─ 创建 RequirementAnalyzer(llm_config_id)
  ├─ 逐条调用 analyzer.analyze_requirement()
  │   ├─ _update_status(task_id, current=i, current_title=...)
  │   ├─ _append_result(task_id, result)
  │   └─ 检查 cancel_event → 如已取消则退出
  ├─ 生成 summary_json
  └─ _update_status(task_id, status='completed', summary_json=...)
```

---

#### `get_task_status(cls, task_id) -> dict | None`

| 参数 | 类型 | 说明 |
|------|------|------|
| task_id | str | 任务ID |

**返回值：**
```python
{
    "task_id": "task_xxx",
    "status": "running",              # pending|running|completed|failed|cancelled
    "total": 25,
    "current": 10,
    "current_title": "当前处理的需求",
    "created_at": "2025-01-01 12:00:00",
    "started_at": "...",
    "completed_at": None,
    "error": None
}
```

---

#### `get_task_results(cls, task_id) -> dict | None`

获取完整任务结果（包含 `results_json` 和 `summary_json`）。

---

#### `get_active_task(cls, username) -> dict | None`

获取用户当前活跃任务（status 为 `pending` 或 `running`）。

---

#### `cancel_task(cls, task_id) -> bool`

取消任务。设置 `cancel_event`，后台线程检测到后退出。

---

#### `list_tasks(cls, username, limit=20) -> list[dict]`

获取用户最近的任务列表。

---

#### `cleanup_stale_tasks(cls) -> int`

清理超过24小时仍为 running 状态的僵死任务。返回清理数量。

---

## 四、SQLValidator — SQL安全验证与执行

**文件：** `file_process/models/sql_validator.py` (612行)

### 4.1 方法列表

#### `validate_sql_safety(sql) -> tuple[bool, str]` (静态方法)

验证SQL语句安全性（禁止 DROP, DELETE, UPDATE, INSERT, ALTER 等）。

| 参数 | 类型 | 说明 |
|------|------|------|
| sql | str | SQL语句 |

**返回值：** `(is_safe: bool, message: str)`

---

#### `validate_test_sql_safety(cls, sql) -> tuple[bool, str]` (类方法)

验证测试SQL安全性（允许 CREATE TEMP TABLE, INSERT, SELECT, DROP TEMP TABLE）。

---

#### `execute_sql_safely(self, sql, db_type) -> dict`

安全执行SQL查询（先验证再执行）。

| 参数 | 类型 | 说明 |
|------|------|------|
| sql | str | SELECT查询语句 |
| db_type | str | 数据库类型（6种之一） |

**返回值：**
```python
{
    "success": True,
    "supported": True,                 # 该数据库类型是否已配置
    "result": [                        # 查询结果行
        {"column1": "value1", "column2": "value2"}
    ],
    "error": None,
    "db_type": "mysql_centralized",
    "db_name": "test_db",
    "rows_count": 5
}
```

---

#### `execute_sql_on_all(self, sql, db_types=None) -> dict`

在多个数据库上并行执行SQL（ThreadPoolExecutor）。

| 参数 | 类型 | 说明 |
|------|------|------|
| sql | str | SQL查询语句 |
| db_types | list[str]/None | 要执行的数据库类型列表，None则执行全部已启用 |

**返回值：** `{db_type: execute_sql_safely返回的dict}` — 每个数据库类型一个结果

---

#### `execute_test_sql_safely(self, sql_statements, db_type) -> dict`

执行测试SQL序列（CREATE TEMP → INSERT → SELECT → DROP TEMP）。

| 参数 | 类型 | 说明 |
|------|------|------|
| sql_statements | list[str] | SQL语句序列 |
| db_type | str | 数据库类型 |

**返回值：**
```python
{
    "success": True,
    "supported": True,
    "results": [                       # 每条SQL的执行结果
        {"sql": "CREATE ...", "success": True, "rows_affected": 0},
        {"sql": "INSERT ...", "success": True, "rows_affected": 3},
        {"sql": "SELECT ...", "success": True, "result": [...], "rows_count": 3}
    ],
    "error": None,
    "db_type": "mysql_centralized",
    "db_name": "test_db",
    "cleaned_tables": ["tmp_test_xxx"]
}
```

---

#### `execute_test_sql_on_all(self, sql_statements, db_types=None) -> dict`

在多个数据库上并行执行测试SQL序列。返回格式同 `execute_sql_on_all`。

---

#### `detect_sql_requirements(text) -> bool` (静态方法)

检测文本是否包含SQL相关需求（关键词匹配：数据库、SQL、表、字段等）。

---

#### `format_results_for_llm(results) -> str` (静态方法)

将执行结果格式化为LLM可读的文本摘要。

---

#### `format_test_results_for_llm(results) -> str` (静态方法)

将测试执行结果格式化为LLM可读的文本摘要。

---

## 五、function_tools — Function Calling 工具

**文件：** `file_process/models/function_tools.py` (314行)

### 5.1 工具Schema定义

```python
# 工具1: execute_sql — 执行只读SQL查询
{
    "type": "function",
    "function": {
        "name": "execute_sql",
        "description": "在指定数据库上执行SQL查询...",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SELECT查询语句"},
                "db_type": {"type": "string", "enum": ["mysql_centralized", ...]}
            },
            "required": ["sql"]
        }
    }
}

# 工具2: execute_sql_test — 执行SQL测试序列
{
    "type": "function",
    "function": {
        "name": "execute_sql_test",
        "description": "执行SQL测试用例序列...",
        "parameters": {
            "type": "object",
            "properties": {
                "sql_statements": {"type": "array", "items": {"type": "string"}},
                "db_type": {"type": "string"}
            },
            "required": ["sql_statements"]
        }
    }
}

# 工具3: web_search — 网络搜索
{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取信息...",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "description": "最大结果数"}
            },
            "required": ["query"]
        }
    }
}
```

### 5.2 公开函数

| 函数 | 签名 | 作用 |
|------|------|------|
| `get_all_tools()` | `-> list[dict]` | 返回全部3个工具的Schema定义 |
| `get_tools_by_names(tool_names)` | `(list[str]) -> list[dict]` | 按名称获取指定工具 |
| `execute_tool(tool_name, arguments)` | `(str, dict) -> dict` | 执行工具并返回结果 |
| `get_tool_names()` | `-> list[str]` | 返回所有工具名列表 |

### 5.3 内部执行函数

| 函数 | 作用 |
|------|------|
| `_execute_sql(sql, db_type=None)` | 调用 `SQLValidator.execute_sql_on_all()` |
| `_execute_sql_test(sql_statements, db_type=None)` | 调用 `SQLValidator.execute_test_sql_on_all()` |
| `_web_search(query, max_results=5)` | 调用 `WebSearchConfigManager` 获取搜索引擎配置后执行搜索 |

---

## 六、配置管理层

### 6.1 SkillsConfigManager — Prompt/技能配置

**文件：** `file_process/models/mcp_skills_config.py`

| 方法 | 签名 | 作用 |
|------|------|------|
| `list_configs(scene_type=None)` | `(str/None) -> list[dict]` | 获取配置列表，可按场景类型过滤 |
| `get_config(config_id)` | `(int) -> dict/None` | 获取单个配置 |
| `create_config(...)` | `(**kwargs) -> int` | 创建配置，返回ID |
| `update_config(config_id, ...)` | `(int, **kwargs) -> bool` | 更新配置 |
| `delete_config(config_id)` | `(int) -> bool` | 删除配置 |
| `get_prompt_for_scene(scene_type)` | `(str) -> str/None` | 获取指定场景的默认Prompt模板 |
| `render_prompt(template, variables)` | `(str, dict) -> str` | 渲染Prompt模板（替换变量） |
| `get_scene_types()` | `-> list[dict]` | 返回5种场景类型定义 |

**场景类型枚举：**
| scene_type | 说明 | 用途 |
|------------|------|------|
| `requirement_analysis` | 需求分析 | Stage 1 精确匹配后的LLM分析 |
| `sql_extraction` | SQL提取 | Stage 2 从需求中提取SQL |
| `sql_validation` | SQL验证 | Stage 2 验证结果的LLM总结 |
| `web_search_summary` | 搜索总结 | Stage 3 搜索结果的LLM总结 |
| `general` | 通用 | 其他通用场景 |

---

### 6.2 SQLDBConfigManager — SQL数据库配置

**文件：** `file_process/models/mcp_skills_config.py`

| 方法 | 签名 | 作用 |
|------|------|------|
| `list_configs()` | `-> list[dict]` | 获取所有数据库配置 |
| `get_config(config_id)` | `(int) -> dict/None` | 获取单个配置 |
| `upsert_config(db_type, **kwargs)` | `(str, **kwargs) -> int` | 插入或更新配置 |
| `delete_config(config_id)` | `(int) -> bool` | 删除配置 |
| `test_connection(db_type, host, port, database, username, password)` | `(...) -> dict` | 测试连接 |
| `get_connection_params(db_type)` | `(str) -> dict/None` | 获取连接参数 |
| `get_enabled_db_types()` | `-> list[str]` | 获取已启用的数据库类型列表 |

**6种数据库类型：**
| db_type | 说明 |
|---------|------|
| `mysql_centralized` | MySQL集中式 |
| `mysql_distributed` | MySQL分布式(TDSQL) |
| `pg_centralized` | PostgreSQL集中式 |
| `pg_distributed` | PG分布式(TDSQL-PG) |
| `oracle_centralized` | Oracle集中式 |
| `oracle_distributed` | Oracle分布式 |

---

### 6.3 LLMConfigManager — LLM配置

**文件：** `file_process/models/llm_config.py`

| 方法 | 签名 | 作用 |
|------|------|------|
| `list_configs()` | `-> list[dict]` | 获取所有LLM配置 |
| `get_config(config_id)` | `(int) -> dict/None` | 获取单个配置 |
| `get_default_config()` | `-> dict/None` | 获取默认配置 |
| `create_config(...)` | `(**kwargs) -> int` | 创建配置 |
| `update_config(config_id, ...)` | `(int, **kwargs) -> bool` | 更新配置 |
| `delete_config(config_id)` | `(int) -> bool` | 删除配置 |
| `get_supported_models()` | `-> dict` | 返回8种模型类型的元数据 |

**`SUPPORTED_MODELS` 字典：**
```python
{
    "openai": {"name": "OpenAI", "supports_pdf": False, "supports_tools": True},
    "gemini": {"name": "Gemini", "supports_pdf": True, "supports_tools": True},
    "qianwen": {"name": "通义千问", "supports_pdf": False, "supports_tools": True},
    "wenxin": {"name": "文心一言", "supports_pdf": False, "supports_tools": False},
    "zhipu": {"name": "智谱", "supports_pdf": True, "supports_tools": True},
    "deepseek": {"name": "DeepSeek", "supports_pdf": False, "supports_tools": True},
    "ollama": {"name": "Ollama", "supports_pdf": False, "supports_tools": True},
    "custom": {"name": "自定义", "supports_pdf": False, "supports_tools": True}
}
```

---

### 6.4 WebSearchConfigManager — 搜索引擎配置

**文件：** `file_process/models/llm_config.py`

| 方法 | 签名 | 作用 |
|------|------|------|
| `list_configs()` | `-> list[dict]` | 获取所有搜索配置 |
| `get_config(config_id)` | `(int) -> dict/None` | 获取单个配置 |
| `get_default_config()` | `-> dict/None` | 获取默认配置 |
| `create_config(...)` | `(**kwargs) -> int` | 创建配置 |
| `update_config(config_id, ...)` | `(int, **kwargs) -> bool` | 更新配置 |
| `delete_config(config_id)` | `(int) -> bool` | 删除配置 |

**搜索引擎类型：** `duckduckgo`, `google`, `baidu`, `bing`, `custom`

---

## 七、EmbeddingConfigManager / VectorStore — 向量化服务

**文件：** `file_process/models/embedding_service.py`

### 7.1 EmbeddingConfigManager

| 方法 | 签名 | 作用 |
|------|------|------|
| `get_all_configs()` | `-> list[dict]` | 获取所有Embedding配置 |
| `get_config(config_id)` | `(int) -> dict/None` | 获取单个配置 |
| `get_default_config()` | `-> dict/None` | 获取默认配置 |
| `create_config(...)` | `(**kwargs) -> int` | 创建配置 |
| `update_config(config_id, ...)` | `(int, **kwargs) -> bool` | 更新配置 |
| `delete_config(config_id)` | `(int) -> bool` | 删除配置 |
| `set_default(config_id)` | `(int) -> bool` | 设为默认 |
| `test_config(config_id=None, config_data=None)` | `(...) -> dict` | 测试配置可用性 |
| `get_providers()` | `-> dict` | 获取支持的提供商列表 |

### 7.2 VectorStore

**工厂函数：** `get_vector_store(config_id=None) -> VectorStore`

| 方法 | 签名 | 作用 |
|------|------|------|
| `add_document_embeddings(doc_id, chapters)` | `(int, list[dict]) -> int` | 向量化文档章节，返回成功数量 |
| `search_similar(query, document_ids, top_k, threshold)` | `(...) -> list[dict]` | 相似度搜索 |
| `get_embedding_stats(doc_id=None)` | `(int/None) -> dict` | 获取向量统计信息 |
| `delete_document_embeddings(doc_id)` | `(int) -> int` | 删除文档向量数据，返回删除数量 |

---

## 八、PDFParser / DocumentParser — 文档解析

**文件：** `file_process/models/pdf_parser.py` (1692行)

### 8.1 PDFParser

| 方法 | 签名 | 作用 |
|------|------|------|
| `__init__(file_path)` | `(str)` | 初始化PDF解析器 |
| `parse()` | `-> list[PDFChapter]` | 基于规则的PDF章节解析 |
| `parse_with_llm(use_cache, llm_config_id)` | `(bool, int/None) -> list[PDFChapter]` | 使用LLM智能解析PDF |
| `get_chapter_by_title(title)` | `(str) -> PDFChapter/None` | 按标题获取章节 |
| `get_chapters_by_range(start, end)` | `(int, int) -> list[PDFChapter]` | 按范围获取章节 |
| `get_content_for_qa()` | `-> str` | 获取用于QA的完整内容 |
| `get_summary()` | `-> str` | 获取PDF摘要 |

### 8.2 DocumentParser

| 方法 | 签名 | 作用 |
|------|------|------|
| `parse(file_path, use_llm, llm_config_id)` | `(str, bool, int/None) -> dict` | 统一文档解析入口（自动识别格式） |
| `parse_docx(docx_path)` | `(str) -> dict` | 解析DOCX文档 |

### 8.3 `PDFChapter` 数据类

```python
@dataclass
class PDFChapter:
    title: str           # 章节标题
    content: str         # 章节内容
    level: int           # 层级（1-6）
    page_start: int      # 起始页码
    page_end: int        # 结束页码
    parent: str = None   # 父章节标题
    children: list = None # 子章节列表
```

---

## 九、BidRequirementExtractor — 招标需求提取

**文件：** `file_process/models/bid_requirement_extractor.py` (1128行)

### 9.1 BidRequirementExtractor

| 方法 | 签名 | 作用 |
|------|------|------|
| `extract_from_document(file_path, section_filter)` | `(str, list/None) -> dict` | 从文档提取招标需求 |
| `extract_with_llm(content, table_data, section_info)` | `(str, list, dict) -> dict` | 使用LLM智能提取需求 |

### 9.2 BidRequirementWordExporter

| 方法 | 签名 | 作用 |
|------|------|------|
| `export_structured_requirements(data, title)` | `(dict, str) -> tuple[str,str]` | 导出结构化需求为Word |
| `export_as_checklist(data, title)` | `(dict, str) -> tuple[str,str]` | 导出为检查清单格式Word |

### 9.3 模块级函数

| 函数 | 签名 | 作用 |
|------|------|------|
| `extract_bid_requirements(file_path)` | `(str) -> dict` | 快捷提取招标需求 |
| `export_requirements_to_word(data, title)` | `(dict, str) -> tuple` | 快捷导出Word |
| `extract_requirements_from_pdf(pdf_path)` | `(str) -> dict` | 从PDF提取需求 |

---

## 十、MCPServerConfigManager — MCP服务器配置

**文件：** `file_process/models/mcp_skills_config.py`

| 方法 | 签名 | 作用 |
|------|------|------|
| `list_configs()` | `-> list[dict]` | 获取所有MCP服务器配置 |
| `get_config(config_id)` | `(int) -> dict/None` | 获取单个配置 |
| `create_config(...)` | `(**kwargs) -> int` | 创建配置 |
| `update_config(config_id, ...)` | `(int, **kwargs) -> bool` | 更新配置 |
| `delete_config(config_id)` | `(int) -> bool` | 删除配置 |

> MCP配置管理的CRUD由 `/llm/mcp-config` 路由调用，但当前 `chat_doc.html` 前端未直接调用此API。

---

## 服务间调用关系总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        路由层 (Routes)                          │
│  chatdoc Blueprint (chat_db_doc.py)                             │
│  llm_bp Blueprint (llm_routes.py)                               │
└─────────────┬───────────────────────────────────────────────────┘
              │ 调用
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      服务层 (Services)                          │
│                                                                 │
│  RequirementAnalyzer ──────┬──→ LLMService                      │
│   (核心分析引擎)            │    (统一LLM调用)                    │
│                            │                                     │
│                            ├──→ SQLValidator                     │
│                            │    (SQL验证与执行)                   │
│                            │                                     │
│                            ├──→ SkillsConfigManager              │
│                            │    (Prompt模板管理)                  │
│                            │                                     │
│                            └──→ function_tools                   │
│                                 (工具执行)                       │
│                                                                 │
│  AnalysisTaskManager ─────────→ RequirementAnalyzer              │
│   (后台任务管理)                (在后台线程中调用)                │
│                                                                 │
│  EmbeddingConfigManager / VectorStore                           │
│   (向量化与搜索)                                                │
│                                                                 │
│  BidDocumentParser / BidAnswerGenerator                         │
│   (招标文档解析与作答)                                           │
│                                                                 │
│  PDFParser / DocumentParser                                      │
│   (文档解析)                                                     │
│                                                                 │
│  LLMConfigManager / WebSearchConfigManager / SQLDBConfigManager  │
│   (配置CRUD)                                                     │
└─────────────────────────────────────────────────────────────────┘
              │ 调用
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      外部依赖层                                  │
│                                                                 │
│  MySQL数据库 (配置存储、任务记录、文档记录、章节数据)             │
│  6种SQL数据库 (SQL验证执行: MySQL/PG/Oracle × 集中式/分布式)     │
│  LLM API (8种: OpenAI/Gemini/千问/文心/智谱/DeepSeek/Ollama/自定义) │
│  搜索引擎 (5种: DuckDuckGo/Google/Baidu/Bing/自定义)            │
│  Embedding API (OpenAI/Ollama等)                                │
│  文件系统 (临时文件、导出Word)                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

> 配合上篇的API路由映射表，本文档为您提供了完整的服务层函数重写参考。
