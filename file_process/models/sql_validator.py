"""
SQL 多数据库验证服务模块
支持6种数据库类型的SQL执行验证：
- MySQL集中式 / MySQL分布式(TDSQL) - pymysql驱动
- PG集中式 / PG分布式(TDSQL-PG) - psycopg2驱动
- Oracle集中式 / Oracle分布式 - psycopg2驱动(复用PG连接)
"""
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from config.logging_config import logger
from .mcp_skills_config import SQLDBConfigManager


class SQLValidator:
    """SQL 多数据库验证器"""

    # 6种数据库类型常量（直接引用 SQLDBConfigManager.DB_TYPES）
    DB_TYPES = SQLDBConfigManager.DB_TYPES

    # SQL 安全白名单：仅允许 SELECT 和 EXPLAIN
    ALLOWED_SQL_PREFIXES = ('SELECT', 'EXPLAIN', 'SHOW', 'DESCRIBE', 'DESC')

    # 测试模式白名单：允许 DDL / DML 用于验证数据库特性
    TEST_ALLOWED_SQL_PREFIXES = (
        'SELECT', 'EXPLAIN', 'SHOW', 'DESCRIBE', 'DESC',
        'CREATE', 'ALTER', 'DROP', 'TRUNCATE',
        'INSERT', 'UPDATE', 'DELETE', 'SET',
        'BEGIN', 'COMMIT', 'ROLLBACK', 'CALL',
        'USE', 'LOAD',
    )

    # 测试表名前缀（所有测试 DDL 必须使用此前缀，确保不影响业务表）
    TEST_TABLE_PREFIX = '_mcp_test_'

    # 执行超时（秒）
    EXECUTION_TIMEOUT = 5

    def __init__(self):
        pass

    def _get_connection(self, db_type):
        """
        工厂方法：根据 db_type 创建数据库连接

        Oracle 类型若 use_independent=False，则从对应 PG 配置取 host/port/user/password + 自身 database

        Returns:
            数据库连接对象
        """
        params = SQLDBConfigManager.get_connection_params(db_type)
        if not params:
            raise ConnectionError(f"未找到 {db_type} 的有效连接配置")

        driver = params.get('driver_type', 'pymysql')

        if driver == 'pymysql':
            import pymysql
            conn = pymysql.connect(
                host=params['host'],
                port=int(params['port']),
                user=params['username'],
                password=params['password'],
                database=params['database_name'],
                connect_timeout=self.EXECUTION_TIMEOUT,
                read_timeout=self.EXECUTION_TIMEOUT,
                write_timeout=self.EXECUTION_TIMEOUT,
                charset='utf8mb4'
            )
            return conn

        elif driver == 'psycopg2':
            try:
                import psycopg2
            except ImportError:
                raise ImportError("psycopg2 驱动未安装，请执行: pip install psycopg2-binary")

            conn = psycopg2.connect(
                host=params['host'],
                port=int(params['port']),
                user=params['username'],
                password=params['password'],
                dbname=params['database_name'],
                connect_timeout=self.EXECUTION_TIMEOUT,
                options=f'-c statement_timeout={self.EXECUTION_TIMEOUT * 1000}'
            )
            conn.autocommit = True
            return conn

        else:
            raise ValueError(f"不支持的驱动类型: {driver}")

    @staticmethod
    def validate_sql_safety(sql):
        """
        SQL 安全校验：只允许白名单前缀

        Args:
            sql: SQL语句

        Returns:
            (is_safe: bool, message: str)
        """
        if not sql or not sql.strip():
            return False, "SQL语句为空"

        clean_sql = sql.strip().upper()
        # 去掉注释
        clean_sql = re.sub(r'--.*$', '', clean_sql, flags=re.MULTILINE)
        clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
        clean_sql = clean_sql.strip()

        if not clean_sql:
            return False, "SQL语句为空（去除注释后）"

        allowed = ('SELECT', 'EXPLAIN', 'SHOW', 'DESCRIBE', 'DESC')
        if not any(clean_sql.startswith(prefix) for prefix in allowed):
            return False, f"仅允许 {', '.join(allowed)} 语句，不允许修改数据的操作"

        # 检测危险模式
        dangerous_patterns = [
            r'\bINTO\s+OUTFILE\b',
            r'\bINTO\s+DUMPFILE\b',
            r'\bLOAD_FILE\b',
            r'\bBENCHMARK\b',
            r'\bSLEEP\b',
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, clean_sql):
                return False, f"SQL包含不允许的操作: {pattern}"

        return True, "安全"

    @classmethod
    def validate_test_sql_safety(cls, sql):
        """
        测试模式的 SQL 安全校验：允许 DDL/DML，但表名必须使用 _mcp_test_ 前缀

        Args:
            sql: SQL语句

        Returns:
            (is_safe: bool, message: str)
        """
        if not sql or not sql.strip():
            return False, "SQL语句为空"

        clean_sql = sql.strip().upper()
        # 去掉注释
        clean_sql = re.sub(r'--.*$', '', clean_sql, flags=re.MULTILINE)
        clean_sql = re.sub(r'/\*.*?\*/', '', clean_sql, flags=re.DOTALL)
        clean_sql = clean_sql.strip()

        if not clean_sql:
            return False, "SQL语句为空（去除注释后）"

        # 白名单检测
        if not any(clean_sql.startswith(prefix) for prefix in cls.TEST_ALLOWED_SQL_PREFIXES):
            return False, (
                f"测试模式仅允许 {', '.join(cls.TEST_ALLOWED_SQL_PREFIXES)} 语句"
            )

        # 对 DDL/DML 语句，必须操作测试表（以 _mcp_test_ 开头）
        ddl_dml_prefixes = ('CREATE', 'ALTER', 'DROP', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'LOAD')
        if any(clean_sql.startswith(p) for p in ddl_dml_prefixes):
            original_sql = sql.strip()
            
            # 排除不涉及表名检查的语句
            non_table_stmts = ('CREATE DATABASE', 'CREATE SCHEMA', 'DROP DATABASE', 'DROP SCHEMA')
            if any(clean_sql.startswith(s) for s in non_table_stmts):
                pass  # 跳过表名检查
            else:
                # 提取表名：支持 `table`, "table", schema.table 等格式
                # INSERT 变体：INSERT INTO / INSERT IGNORE INTO / INSERT OR IGNORE INTO / REPLACE INTO
                table_patterns = [
                    r'(?i)CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    r'(?i)ALTER\s+TABLE\s+(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    r'(?i)DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    r'(?i)TRUNCATE\s+(?:TABLE\s+)?(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    r'(?i)(?:INSERT|REPLACE)\s+(?:OR\s+\w+\s+)?(?:IGNORE\s+)?INTO\s+(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    r'(?i)UPDATE\s+(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    r'(?i)DELETE\s+FROM\s+(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    # CREATE [FULLTEXT|SPATIAL|UNIQUE|CLUSTERED] INDEX ... ON table_name
                    r'(?i)CREATE\s+(?:FULLTEXT|SPATIAL|UNIQUE|CLUSTERED|NONCLUSTERED)?\s*INDEX\s+\S+\s+ON\s+(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    # DROP INDEX (MySQL: DROP INDEX idx ON table)
                    r'(?i)DROP\s+INDEX\s+\S+\s+ON\s+(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                    # LOAD DATA ... INTO TABLE table_name
                    r'(?i)LOAD\s+DATA\s+.*?INTO\s+TABLE\s+(?:\w+\.)?[`"\']?(\w+)[`"\']?',
                ]
                table_name = None
                for pattern in table_patterns:
                    m = re.search(pattern, original_sql)
                    if m:
                        table_name = m.group(1)
                        break

                if not table_name:
                    return False, f"无法从DDL/DML语句中提取表名, SQL: {original_sql[:120]}"

                if not table_name.lower().startswith(cls.TEST_TABLE_PREFIX):
                    return False, (
                        f"测试模式的DDL/DML语句中表名必须以 '{cls.TEST_TABLE_PREFIX}' 前缀开头，"
                        f"当前表名: {table_name}"
                    )
        
        # USE 语句无需表名检查（切换数据库），直接放行
        # (已通过白名单检测)

        # 检测危险模式（同只读模式）
        dangerous_patterns = [
            r'\bINTO\s+OUTFILE\b',
            r'\bINTO\s+DUMPFILE\b',
            r'\bLOAD_FILE\b',
            r'\bBENCHMARK\b',
            r'\bSLEEP\b',
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, clean_sql):
                return False, f"SQL包含不允许的操作: {pattern}"

        return True, "安全"

    def execute_test_sql_safely(self, sql_statements, db_type):
        """
        在指定数据库上执行一组测试 SQL 语句（支持 DDL/DML），最后自动清理测试表

        Args:
            sql_statements: SQL 语句列表（按顺序执行）
            db_type: 数据库类型标识

        Returns:
            dict: {success, supported, results: [{sql, success, result, error}], db_type, db_name, cleaned_tables}
        """
        type_info = self.DB_TYPES.get(db_type, {})
        db_name = type_info.get('name', db_type)

        overall = {
            'db_type': db_type,
            'db_name': db_name,
            'success': False,
            'supported': False,
            'results': [],
            'error': '',
            'cleaned_tables': []
        }

        # 收集需要清理的测试表名
        test_tables = set()
        for sql in sql_statements:
            m = re.search(
                r'(?i)CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\']?(\w+)',
                sql
            )
            if m:
                test_tables.add(m.group(1))

        conn = None
        try:
            conn = self._get_connection(db_type)
            cursor = conn.cursor()

            any_success = False
            for sql in sql_statements:
                stmt_result = {'sql': sql, 'success': False, 'result': '', 'error': ''}

                # 每条语句都做测试模式安全校验
                is_safe, safety_msg = self.validate_test_sql_safety(sql)
                if not is_safe:
                    stmt_result['error'] = f"安全校验失败: {safety_msg}"
                    overall['results'].append(stmt_result)
                    continue

                try:
                    cursor.execute(sql)

                    if cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        rows = cursor.fetchall()
                        max_rows = 20
                        display_rows = rows[:max_rows]
                        result_lines = [' | '.join(columns)]
                        result_lines.append('-' * len(result_lines[0]))
                        for row in display_rows:
                            result_lines.append(' | '.join(str(v) for v in row))
                        if len(rows) > max_rows:
                            result_lines.append(f'... (共 {len(rows)} 行，仅显示前 {max_rows} 行)')
                        stmt_result['result'] = '\n'.join(result_lines)
                    else:
                        stmt_result['result'] = '语句执行成功（无返回数据）'

                    stmt_result['success'] = True
                    any_success = True

                except Exception as e:
                    stmt_result['error'] = str(e)

                overall['results'].append(stmt_result)

            overall['success'] = any_success
            overall['supported'] = any_success

            # 清理测试表
            for table_name in test_tables:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                    overall['cleaned_tables'].append(table_name)
                    logger.info(f"[SQLValidator] 清理测试表: {table_name} on {db_name}")
                except Exception as e:
                    logger.warning(f"[SQLValidator] 清理测试表失败: {table_name} on {db_name}: {e}")

            # 确保提交（对于非 autocommit 连接）
            try:
                conn.commit()
            except Exception:
                pass

            cursor.close()
            logger.info(f"[SQLValidator] {db_name} 测试执行完成: {len(sql_statements)} 条语句")

        except Exception as e:
            error_msg = str(e)
            overall['error'] = error_msg
            logger.warning(f"[SQLValidator] {db_name} 测试执行失败: {error_msg[:200]}")

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return overall

    def execute_test_sql_on_all(self, sql_statements, db_types=None):
        """
        在所有已启用的数据库上并行执行测试 SQL 语句组

        Args:
            sql_statements: SQL 语句列表（按顺序执行）
            db_types: 指定数据库类型列表，None 则使用所有已启用的

        Returns:
            dict: {db_type: {success, supported, results: [...], ...}}
        """
        if db_types is None:
            db_types = SQLDBConfigManager.get_enabled_db_types()

        if not db_types:
            logger.warning("[SQLValidator] 没有已启用的数据库配置")
            return {}

        logger.info(
            f"[SQLValidator] 开始在 {len(db_types)} 种数据库上执行测试SQL: "
            f"{len(sql_statements)} 条语句"
        )

        results = {}

        with ThreadPoolExecutor(max_workers=min(len(db_types), 6)) as executor:
            future_to_type = {
                executor.submit(self.execute_test_sql_safely, sql_statements, dt): dt
                for dt in db_types
            }

            for future in as_completed(future_to_type):
                db_type = future_to_type[future]
                try:
                    result = future.result(timeout=self.EXECUTION_TIMEOUT + 10)
                    results[db_type] = result
                except Exception as e:
                    results[db_type] = {
                        'db_type': db_type,
                        'db_name': self.DB_TYPES.get(db_type, {}).get('name', db_type),
                        'success': False,
                        'supported': False,
                        'results': [],
                        'error': f'执行异常: {str(e)}',
                        'cleaned_tables': []
                    }

        success_count = sum(1 for r in results.values() if r.get('success'))
        logger.info(f"[SQLValidator] 测试执行完成: {success_count}/{len(results)} 成功")

        return results

    @staticmethod
    def format_test_results_for_llm(results):
        """
        将测试模式多数据库执行结果格式化为 LLM 可读文本

        Args:
            results: execute_test_sql_on_all 返回的结果字典

        Returns:
            str: 格式化的结果文本
        """
        if not results:
            return "无执行结果"

        lines = []
        for db_type, db_result in results.items():
            db_name = db_result.get('db_name', db_type)
            if db_result.get('error') and not db_result.get('results'):
                lines.append(f"【{db_name}】❌ 连接/执行异常: {db_result['error'][:200]}")
                lines.append("")
                continue

            overall_ok = db_result.get('success', False)
            lines.append(f"【{db_name}】{'✅ 支持' if overall_ok else '❌ 不支持'}")

            for stmt in db_result.get('results', []):
                sql_short = stmt.get('sql', '')[:80]
                if stmt.get('success'):
                    lines.append(f"  ✅ {sql_short}")
                    if stmt.get('result'):
                        lines.append(f"     输出: {stmt['result'][:300]}")
                else:
                    lines.append(f"  ❌ {sql_short}")
                    lines.append(f"     错误: {stmt.get('error', '')[:300]}")

            if db_result.get('cleaned_tables'):
                lines.append(f"  🧹 已清理测试表: {', '.join(db_result['cleaned_tables'])}")
            lines.append("")

        return '\n'.join(lines)

    def execute_sql_safely(self, sql, db_type):
        """
        在指定数据库上安全执行 SQL

        Args:
            sql: SQL语句
            db_type: 数据库类型标识

        Returns:
            dict: {success, supported, result, error, db_type, db_name}
        """
        type_info = self.DB_TYPES.get(db_type, {})
        db_name = type_info.get('name', db_type)

        result = {
            'db_type': db_type,
            'db_name': db_name,
            'success': False,
            'supported': False,
            'result': '',
            'error': '',
            'rows_count': 0
        }

        # 安全校验
        is_safe, safety_msg = self.validate_sql_safety(sql)
        if not is_safe:
            result['error'] = f"安全校验失败: {safety_msg}"
            return result

        conn = None
        try:
            conn = self._get_connection(db_type)
            cursor = conn.cursor()
            cursor.execute(sql)

            # 获取结果
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result['success'] = True
                result['supported'] = True
                result['rows_count'] = len(rows)

                # 格式化结果（限制行数避免过大）
                max_rows = 20
                display_rows = rows[:max_rows]
                result_lines = [' | '.join(columns)]
                result_lines.append('-' * len(result_lines[0]))
                for row in display_rows:
                    result_lines.append(' | '.join(str(v) for v in row))
                if len(rows) > max_rows:
                    result_lines.append(f'... (共 {len(rows)} 行，仅显示前 {max_rows} 行)')
                result['result'] = '\n'.join(result_lines)
            else:
                # 无返回结果的语句（如 EXPLAIN）
                result['success'] = True
                result['supported'] = True
                result['result'] = '语句执行成功（无返回数据）'

            cursor.close()
            logger.info(f"[SQLValidator] {db_name} 执行成功: {sql[:80]}... -> {result['rows_count']} 行")

        except Exception as e:
            error_msg = str(e)
            result['error'] = error_msg
            result['success'] = False
            # 根据错误信息判断是否是"不支持"还是"连接/配置错误"
            result['supported'] = False
            logger.warning(f"[SQLValidator] {db_name} 执行失败: {sql[:80]}... -> {error_msg[:200]}")

        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return result

    def execute_sql_on_all(self, sql, db_types=None):
        """
        在所有已启用的数据库上并行执行 SQL

        Args:
            sql: SQL语句
            db_types: 指定数据库类型列表，None 则使用所有已启用的

        Returns:
            dict: {db_type: {success, supported, result, error, ...}}
        """
        if db_types is None:
            db_types = SQLDBConfigManager.get_enabled_db_types()

        if not db_types:
            logger.warning("[SQLValidator] 没有已启用的数据库配置")
            return {}

        logger.info(f"[SQLValidator] 开始在 {len(db_types)} 种数据库上执行SQL: {sql[:100]}...")

        results = {}

        # 使用线程池并行执行
        with ThreadPoolExecutor(max_workers=min(len(db_types), 6)) as executor:
            future_to_type = {
                executor.submit(self.execute_sql_safely, sql, dt): dt
                for dt in db_types
            }

            for future in as_completed(future_to_type):
                db_type = future_to_type[future]
                try:
                    result = future.result(timeout=self.EXECUTION_TIMEOUT + 5)
                    results[db_type] = result
                except Exception as e:
                    results[db_type] = {
                        'db_type': db_type,
                        'db_name': self.DB_TYPES.get(db_type, {}).get('name', db_type),
                        'success': False,
                        'supported': False,
                        'result': '',
                        'error': f'执行异常: {str(e)}',
                        'rows_count': 0
                    }

        # 统计结果
        success_count = sum(1 for r in results.values() if r.get('success'))
        logger.info(f"[SQLValidator] 执行完成: {success_count}/{len(results)} 成功")

        return results

    @staticmethod
    def detect_sql_requirements(text):
        """
        检测文本中是否包含 SQL 语法要求（正则预筛选）

        Args:
            text: 需求文本

        Returns:
            bool: 是否可能包含 SQL 相关要求
        """
        sql_pattern = re.compile(
            r'(?i)\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXPLAIN|'
            r'INDEX|VIEW|TRIGGER|PROCEDURE|FUNCTION|'
            r'JOIN|UNION|SUBQUERY|CTE|WITH\s+RECURSIVE|'
            r'PARTITION|SHARD|DISTRIBUTE|'
            r'TRANSACTION|COMMIT|ROLLBACK|SAVEPOINT|'
            r'GRANT|REVOKE|'
            r'VARCHAR|INTEGER|DECIMAL|TIMESTAMP|BOOLEAN|TEXT|BLOB|CLOB|'
            r'PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|NOT\s+NULL|DEFAULT|CHECK|'
            r'AUTO_INCREMENT|SERIAL|SEQUENCE|'
            r'GROUP\s+BY|ORDER\s+BY|HAVING|WINDOW|OVER|'
            r'JSON|JSONB|ARRAY|XML|'
            r'MVCC|ACID|WAL|REDO|UNDO|'
            r'FULLTEXT|LOAD\s+DATA|INSERT\s+IGNORE|'
            r'REGEXP|NOT_REGEXP|RLIKE|'
            r'SET\s+@|SET\s+GLOBAL|SET\s+SESSION|'
            r'CROSS\s+JOIN|CROSS\s+DATABASE|'
            r'ON\s+UPDATE|ON\s+DELETE|CASCADE|'
            r'REPLACE\s+INTO|TRUNCATE|MERGE|'
            r'CURSOR|DECLARE|FETCH|'
            r'TABLESPACE|ENGINE|CHARSET|COLLATE)\b|'
            r'(?:跨库|自增|全文索引|正则表达式|存储过程|触发器|分区表|分布式)'
        )
        return bool(sql_pattern.search(text))

    @staticmethod
    def format_results_for_llm(results):
        """
        将多数据库执行结果格式化为 LLM 可读的文本

        Args:
            results: execute_sql_on_all 返回的结果字典

        Returns:
            str: 格式化的结果文本
        """
        if not results:
            return "无执行结果"

        lines = []
        for db_type, result in results.items():
            db_name = result.get('db_name', db_type)
            if result.get('success'):
                status = "✅ 执行成功"
                detail = result.get('result', '')
                if result.get('rows_count'):
                    detail = f"返回 {result['rows_count']} 行\n{detail}"
            else:
                status = "❌ 执行失败"
                detail = result.get('error', '未知错误')

            lines.append(f"【{db_name}】{status}")
            if detail:
                lines.append(f"  {detail[:500]}")
            lines.append("")

        return '\n'.join(lines)


def get_sql_validator():
    """获取 SQL 验证器实例"""
    return SQLValidator()
