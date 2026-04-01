# simple_rules_oracle.py
# Oracle 静态拦截规则：特征词匹配 → 跳过 LLM 直接生成标准格式测试用例

SIMPLE_ORACLE_RULES = [
    {
        "特征词": ["数值", "字符串", "日期", "大对象", "blob", "clob"],
        "测试名": "Oracle综合数据类型建表测试",
        "前置SQL": """
            BEGIN
               EXECUTE IMMEDIATE 'DROP TABLE _mcp_test_ora_types';
            EXCEPTION
               WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
            END;
        """,
        "验证SQL": """
            CREATE TABLE _mcp_test_ora_types (
                id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                num_val NUMBER(10,2), 
                str_val VARCHAR2(255), 
                dt_val TIMESTAMP, 
                blob_val BLOB, 
                clob_val CLOB
            )
        """
    },
    {
        "特征词": ["自增", "正则表达式", "REGEXP_LIKE"],
        "测试名": "Oracle特性综合验证",
        "前置SQL": """
            BEGIN
               EXECUTE IMMEDIATE 'DROP TABLE _mcp_test_ora_features';
            EXCEPTION
               WHEN OTHERS THEN NULL;
            END;
            CREATE TABLE _mcp_test_ora_features (id NUMBER, cat VARCHAR2(20));
            INSERT INTO _mcp_test_ora_features VALUES (1, 'DB');
        """,
        "验证SQL": "SELECT cat, COUNT(*) FROM _mcp_test_ora_features WHERE REGEXP_LIKE(cat, '^[A-Z]+$') GROUP BY cat"
    },
    {
        "特征词": ["truncate", "abs", "nvl", "ifnull", "sysdate", "now"],
        "测试名": "Oracle高频函数组合测试",
        "前置SQL": "",
        "验证SQL": "SELECT TRUNC(123.456, 2), ABS(-50), NVL(NULL, '默认值'), TO_CHAR(SYSDATE, 'YYYY-MM-DD') FROM DUAL"
    }
]
