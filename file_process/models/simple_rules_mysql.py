# simple_rules_mysql.py
# MySQL 静态拦截规则：特征词匹配 → 跳过 LLM 直接生成标准格式测试用例

SIMPLE_MYSQL_RULES = [
    {
        "特征词": ["数值", "字符串", "日期", "大对象", "blob", "clob", "枚举", "集合"],
        "测试名": "MySQL综合数据类型建表测试",
        "前置SQL": "DROP TABLE IF EXISTS _mcp_test_mysql_types;",
        "验证SQL": """
            CREATE TABLE _mcp_test_mysql_types (
                id INT AUTO_INCREMENT PRIMARY KEY, 
                num_val DECIMAL(10,2), 
                str_val VARCHAR(255), 
                dt_val DATETIME, 
                bool_val BOOLEAN, 
                blob_val BLOB, 
                clob_val LONGTEXT,
                enum_val ENUM('A', 'B'), 
                set_val SET('X', 'Y')
            );
        """
    },
    {
        "特征词": ["FULLTEXT", "INSERT IGNORE"],
        "测试名": "全文索引与忽略插入测试",
        "前置SQL": """
            DROP TABLE IF EXISTS _mcp_test_ft;
            CREATE TABLE _mcp_test_ft (id INT PRIMARY KEY, content TEXT, FULLTEXT(content));
            INSERT INTO _mcp_test_ft VALUES (1, '初始文本');
        """,
        "验证SQL": "INSERT IGNORE INTO _mcp_test_ft VALUES (1, '冲突文本');"
    },
    {
        "特征词": ["truncate", "abs", "ifnull", "now", "date_format"],
        "测试名": "MySQL高频函数组合测试",
        "前置SQL": "",
        "验证SQL": "SELECT TRUNCATE(123.456, 2), ABS(-50), IFNULL(NULL, '默认值'), DATE_FORMAT(NOW(), '%Y-%m-%d');"
    }
]
