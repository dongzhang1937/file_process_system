# simple_rules_pg.py
# PostgreSQL 静态拦截规则：特征词匹配 → 跳过 LLM 直接生成标准格式测试用例

SIMPLE_PG_RULES = [
    {
        "特征词": ["数值", "字符串", "日期", "布尔", "大对象", "blob", "clob"],
        "测试名": "PostgreSQL综合数据类型建表测试",
        "前置SQL": "DROP TABLE IF EXISTS _mcp_test_pg_types CASCADE;",
        "验证SQL": """
            CREATE TABLE _mcp_test_pg_types (
                id SERIAL PRIMARY KEY,
                num_val NUMERIC(10,2), 
                str_val VARCHAR(255), 
                dt_val TIMESTAMP, 
                bool_val BOOLEAN, 
                blob_val BYTEA,
                clob_val TEXT
            );
        """
    },
    {
        "特征词": ["忽略插入", "正则表达式", "ON CONFLICT"],
        "测试名": "PG冲突忽略与正则测试",
        "前置SQL": """
            DROP TABLE IF EXISTS _mcp_test_pg_features;
            CREATE TABLE _mcp_test_pg_features (id INT PRIMARY KEY, cat VARCHAR(20));
            INSERT INTO _mcp_test_pg_features VALUES (1, 'ABC');
        """,
        "验证SQL": """
            INSERT INTO _mcp_test_pg_features VALUES (1, 'DEF') ON CONFLICT (id) DO NOTHING;
            SELECT * FROM _mcp_test_pg_features WHERE cat ~ '^[A-Z]+$';
        """
    },
    {
        "特征词": ["truncate", "abs", "coalesce", "ifnull", "now"],
        "测试名": "PG高频函数组合测试",
        "前置SQL": "",
        "验证SQL": "SELECT TRUNC(123.456, 2), ABS(-50), COALESCE(NULL, '默认值'), TO_CHAR(NOW(), 'YYYY-MM-DD');"
    }
]
