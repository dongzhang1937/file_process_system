"""
Function Calling 工具注册中心
定义 OpenAI 格式的 tool schema，提供统一的工具执行接口

工具列表：
1. execute_sql - 在多种数据库上执行SQL验证
2. web_search - 网络搜索
"""
import json
from config.logging_config import logger


# ==================== OpenAI 格式 Tool Schema ====================

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "在指定的数据库上执行SQL语句进行验证。支持6种数据库类型：MySQL集中式、MySQL分布式(TDSQL)、PG集中式、PG分布式(TDSQL-PG)、Oracle集中式、Oracle分布式。仅允许SELECT和EXPLAIN等只读语句。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的SQL语句（仅允许SELECT/EXPLAIN/SHOW/DESCRIBE）"
                    },
                    "db_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "mysql_centralized",
                                "mysql_distributed",
                                "pg_centralized",
                                "pg_distributed",
                                "oracle_centralized",
                                "oracle_distributed"
                            ]
                        },
                        "description": "目标数据库类型列表。不指定则在所有已启用的数据库上执行。"
                    }
                },
                "required": ["sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql_test",
            "description": (
                "在指定数据库上执行一组测试SQL语句来验证数据库特性。"
                "支持DDL/DML（CREATE TABLE, ALTER TABLE, INSERT, SELECT等），"
                "但所有表名必须以 '_mcp_test_' 前缀开头。"
                "执行完毕后自动清理测试表。\n\n"
                "使用场景：当需求涉及数据库特性验证时（如'支持自动更新时间字段'），"
                "生成包含 CREATE TABLE + INSERT/SELECT 的测试SQL序列来验证该特性在各数据库上的支持情况。\n\n"
                "注意：所有表名必须以 '_mcp_test_' 开头，例如 '_mcp_test_timestamp'。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_statements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "要按顺序执行的SQL语句列表。例如：\n"
                            "1. CREATE TABLE _mcp_test_xxx (...)\n"
                            "2. INSERT INTO _mcp_test_xxx ...\n"
                            "3. SELECT ... FROM _mcp_test_xxx\n"
                            "测试表会在执行后自动清理（DROP）。"
                        )
                    },
                    "db_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "mysql_centralized",
                                "mysql_distributed",
                                "pg_centralized",
                                "pg_distributed",
                                "oracle_centralized",
                                "oracle_distributed"
                            ]
                        },
                        "description": "目标数据库类型列表。不指定则在所有已启用的数据库上执行。"
                    },
                    "expected_behavior": {
                        "type": "string",
                        "description": "预期行为描述，用于对比实际执行结果。例如：'update_time字段应自动更新为当前时间'"
                    }
                },
                "required": ["sql_statements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "使用网络搜索引擎搜索信息。用于查找数据库特性、SQL语法兼容性等技术问题的答案。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "返回结果数量，默认5",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# ==================== 工具执行函数 ====================

def _execute_sql_tool(arguments):
    """执行 execute_sql 工具"""
    from .sql_validator import get_sql_validator

    sql = arguments.get('sql', '')
    db_types = arguments.get('db_types', None)

    if not sql:
        return json.dumps({"error": "SQL语句为空"}, ensure_ascii=False)

    validator = get_sql_validator()

    # 安全校验
    is_safe, safety_msg = validator.validate_sql_safety(sql)
    if not is_safe:
        return json.dumps({"error": f"安全校验失败: {safety_msg}"}, ensure_ascii=False)

    # 执行
    results = validator.execute_sql_on_all(sql, db_types)

    # 格式化结果
    formatted = {}
    for db_type, result in results.items():
        formatted[db_type] = {
            'db_name': result.get('db_name', db_type),
            'success': result.get('success', False),
            'supported': result.get('supported', False),
            'result': result.get('result', ''),
            'error': result.get('error', ''),
            'rows_count': result.get('rows_count', 0)
        }

    return json.dumps(formatted, ensure_ascii=False)


def _execute_sql_test_tool(arguments):
    """执行 execute_sql_test 工具（测试模式，支持DDL/DML）"""
    from .sql_validator import get_sql_validator

    sql_statements = arguments.get('sql_statements', [])
    db_types = arguments.get('db_types', None)
    expected_behavior = arguments.get('expected_behavior', '')

    if not sql_statements:
        return json.dumps({"error": "SQL语句列表为空"}, ensure_ascii=False)

    if isinstance(sql_statements, str):
        # 兼容 LLM 传入单条SQL字符串的情况
        sql_statements = [sql_statements]

    validator = get_sql_validator()

    # 对每条语句做测试模式安全校验
    for sql in sql_statements:
        is_safe, safety_msg = validator.validate_test_sql_safety(sql)
        if not is_safe:
            return json.dumps({
                "error": f"安全校验失败: {safety_msg}",
                "failed_sql": sql
            }, ensure_ascii=False)

    # 执行测试SQL
    results = validator.execute_test_sql_on_all(sql_statements, db_types)

    # 格式化结果
    formatted = {}
    for db_type, result in results.items():
        formatted[db_type] = {
            'db_name': result.get('db_name', db_type),
            'success': result.get('success', False),
            'supported': result.get('supported', False),
            'results': result.get('results', []),
            'error': result.get('error', ''),
            'cleaned_tables': result.get('cleaned_tables', [])
        }

    output = {
        'test_results': formatted,
        'expected_behavior': expected_behavior,
        'sql_count': len(sql_statements)
    }

    return json.dumps(output, ensure_ascii=False)


def _execute_web_search_tool(arguments):
    """执行 web_search 工具"""
    from .web_search import WebSearchService

    query = arguments.get('query', '')
    num_results = arguments.get('num_results', 5)

    if not query:
        return json.dumps({"error": "搜索关键词为空"}, ensure_ascii=False)

    try:
        search_service = WebSearchService()
        results = search_service.search(query, num_results=num_results)

        if not results:
            return json.dumps({"results": [], "message": "未找到相关结果"}, ensure_ascii=False)

        formatted = []
        for r in results:
            formatted.append({
                'title': r.get('title', ''),
                'snippet': r.get('snippet', ''),
                'url': r.get('url', '')
            })

        return json.dumps({"results": formatted}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[Function Tools] web_search 执行失败: {e}")
        return json.dumps({"error": f"搜索失败: {str(e)}"}, ensure_ascii=False)


# ==================== 工具注册表 ====================

_TOOL_EXECUTORS = {
    'execute_sql': _execute_sql_tool,
    'execute_sql_test': _execute_sql_test_tool,
    'web_search': _execute_web_search_tool,
}


# ==================== 公开接口 ====================

def get_all_tools():
    """
    获取所有工具的 OpenAI 格式 schema

    Returns:
        list: tool schema 列表
    """
    return TOOL_SCHEMAS


def get_tools_by_names(tool_names):
    """
    根据名称获取指定工具的 schema

    Args:
        tool_names: 工具名称列表

    Returns:
        list: 匹配的 tool schema 列表
    """
    return [
        t for t in TOOL_SCHEMAS
        if t['function']['name'] in tool_names
    ]


def execute_tool(tool_name, arguments):
    """
    执行指定工具

    Args:
        tool_name: 工具名称
        arguments: 参数字典或 JSON 字符串

    Returns:
        str: 工具执行结果（JSON字符串）
    """
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return json.dumps({"error": f"参数解析失败: {arguments}"}, ensure_ascii=False)

    executor = _TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    try:
        logger.info(f"[Function Tools] 执行工具: {tool_name}, 参数: {json.dumps(arguments, ensure_ascii=False)[:200]}")
        result = executor(arguments)
        logger.info(f"[Function Tools] 工具 {tool_name} 执行完成，结果长度: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"[Function Tools] 工具 {tool_name} 执行异常: {e}")
        return json.dumps({"error": f"工具执行异常: {str(e)}"}, ensure_ascii=False)

