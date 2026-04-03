# db连接池 dbutils
from __future__ import annotations
from typing import Any
from dbutils.pooled_db import PooledDB
import pymysql
from .app_config import Config

# 从统一配置文件获取数据库配置
db_config = Config.get_mysql_config_dict()

# 构建连接池参数（unix_socket 仅在路径存在时使用，否则走 TCP）
import os as _os
_pool_kwargs = dict(
    creator=pymysql,
    maxconnections=Config.MYSQL_POOL_MAX_CONNECTIONS,
    mincached=Config.MYSQL_POOL_MIN_CACHED,
    blocking=Config.MYSQL_POOL_BLOCKING,
    maxcached=Config.MYSQL_POOL_MAX_CACHED,
    maxshared=Config.MYSQL_POOL_MAX_SHARED,
    setsession=[],
    ping=Config.MYSQL_POOL_PING,
    host=db_config['host'],
    port=db_config['port'],
    user=db_config['user'],
    password=db_config['password'],
    database=db_config['database'],
    charset=db_config['charset'],
)
# 仅当 unix_socket 配置了且文件存在时才使用
_unix_sock = db_config.get('unix_socket')
if _unix_sock and _os.path.exists(_unix_sock):
    _pool_kwargs['unix_socket'] = _unix_sock

pool = PooledDB(**_pool_kwargs)

def get_conn():
    conn = pool.connection()
    return conn

def dml_sql(sql: str, parameters: tuple[Any, ...] | list[Any] | None = None) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    if parameters:
        cursor.execute(sql, parameters)
    else:
        cursor.execute(sql)
    conn.commit()
    affected_rows = cursor.rowcount
    cursor.close()
    conn.close()
    return affected_rows

def query_sql(sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> list[dict[str, Any]]:
    """
    执行查询语句，返回字典列表
    """
    conn = get_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor) # 使用 DictCursor 让结果以字典形式返回
    try:
        cursor.execute(sql, params or ())
        result = cursor.fetchall()
        return result
    except Exception as e:
        print(f"查询出错: {e}")
        return []
    finally:
        cursor.close()
        close_db_connection(conn) # 修正：这里需要传入当前连接

def close_db_connection(conn: Any = None) -> None:
    """
    关闭数据库连接（如果是从连接池获取的，则为归还连接）
    """
    if conn:
        try:
            conn.close()
        except Exception as e:
            print(f"归还连接池出错: {e}")

def fetch_one(sql: str, parameters: tuple[Any, ...] | list[Any] | None = None) -> dict[str, Any] | None:
    conn = get_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    if parameters:
        cursor.execute(sql, parameters)
    else:
        cursor.execute(sql)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

def fetch_all(sql: str, parameters: tuple[Any, ...] | list[Any] | None = None) -> list[dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    if parameters:
        cursor.execute(sql, parameters)
    else:
        cursor.execute(sql)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result

def dml_sql_with_insert_id(sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> tuple[int | None, int]:
    """
    执行插入语句，并返回新产生的自增 ID
    """
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params or ())
        conn.commit()
        last_id = cursor.lastrowid # 获取自增 ID
        affected_rows = cursor.rowcount
        return last_id, affected_rows
    except Exception as e:
        conn.rollback()
        print(f"执行带ID插入出错: {e}")
        return None, 0
    finally:
        cursor.close()
        close_db_connection(conn)