# db连接池 dbutils
import socket
from dbutils.pooled_db import PooledDB
import pymysql
from .app_config import Config

# 从统一配置文件获取数据库配置
db_config = Config.get_mysql_config_dict()

pool = PooledDB(
    #列出pooledb常用的参数，并给出相应的中文注释
    creator=pymysql,  # 数据库连接模块
    maxconnections=Config.MYSQL_POOL_MAX_CONNECTIONS,  # 最大连接数
    mincached=Config.MYSQL_POOL_MIN_CACHED,  # 初始化时，链接池中至少创建的空闲的链接，0表示不创建
    blocking=Config.MYSQL_POOL_BLOCKING,  # 连接池中如果没有可用连接后，是否阻塞等待。True，等待；False，不等待然后报错
    maxcached=Config.MYSQL_POOL_MAX_CACHED,  # 最大空闲连接数
    maxshared=Config.MYSQL_POOL_MAX_SHARED,  # 共享连接数
    setsession=[],  # 开始会话前执行的命令列表。如：["set datestyle to ...", "set time zone ..."]
    ping=Config.MYSQL_POOL_PING,  # 连接的ping值
    host=db_config['host'],
    port=db_config['port'],
    user=db_config['user'],
    password=db_config['password'],
    database=db_config['database'],
    charset=db_config['charset'],
    unix_socket=db_config['unix_socket']
)

def get_conn():
    conn = pool.connection()
    return conn

def dml_sql(sql, parameters=None):
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

def query_sql(sql, params=None):
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

def close_db_connection(conn=None):
    """
    关闭数据库连接（如果是从连接池获取的，则为归还连接）
    """
    if conn:
        try:
            conn.close()
        except Exception as e:
            print(f"归还连接池出错: {e}")

def fetch_one(sql, parameters=None):
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

def fetch_all(sql, parameters=None):
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

def dml_sql_with_insert_id(sql, params=None):
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