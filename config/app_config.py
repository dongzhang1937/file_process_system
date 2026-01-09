"""
统一配置文件 - Redis 和 MySQL 配置
所有数据库和缓存相关的配置都在这里统一管理
"""
import os

# ============ 基础配置 ============
class BaseConfig:
    """基础配置类"""
    
    # ============ Flask 基础配置 ============
    SECRET_KEY = 'your-secret-key-change-in-production-2026'
    DEBUG = True
    
    # ============ MySQL 数据库配置 ============
    MYSQL_HOST = '127.0.0.1'
    MYSQL_PORT = 3306
    MYSQL_USER = 'test'
    MYSQL_PASSWORD = 'test'
    MYSQL_DATABASE = 't11'
    MYSQL_CHARSET = 'utf8'
    MYSQL_UNIX_SOCKET = '/var/lib/mysql/mysql.sock'
    
    # ============ Redis 配置 ============
    REDIS_HOST = '127.0.0.1'
    REDIS_PORT = 6379
    REDIS_DB = 0
    REDIS_PASSWORD = None  # 如果Redis设置了密码，在这里配置
    REDIS_DECODE_RESPONSES = True
    
    # ============ 连接池配置 ============
    # MySQL 连接池配置
    MYSQL_POOL_MAX_CONNECTIONS = 10
    MYSQL_POOL_MIN_CACHED = 2
    MYSQL_POOL_MAX_CACHED = 5
    MYSQL_POOL_MAX_SHARED = 8
    MYSQL_POOL_BLOCKING = True
    MYSQL_POOL_PING = 0
    
    # Redis 连接池配置
    REDIS_POOL_MAX_CONNECTIONS = 20
    REDIS_POOL_RETRY_ON_TIMEOUT = True
    
    # ============ 生成连接字符串的方法 ============
    @classmethod
    def get_mysql_uri(cls):
        """获取 MySQL SQLAlchemy 连接字符串"""
        return f"mysql+pymysql://{cls.MYSQL_USER}:{cls.MYSQL_PASSWORD}@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
    
    @classmethod
    def get_mysql_celery_uri(cls):
        """获取 MySQL Celery 结果后端连接字符串"""
        return f"db+mysql+pymysql://{cls.MYSQL_USER}:{cls.MYSQL_PASSWORD}@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
    
    @classmethod
    def get_redis_uri(cls):
        """获取 Redis 连接字符串"""
        if cls.REDIS_PASSWORD:
            return f"redis://:{cls.REDIS_PASSWORD}@{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"
        else:
            return f"redis://{cls.REDIS_HOST}:{cls.REDIS_PORT}/{cls.REDIS_DB}"
    
    @classmethod
    def get_mysql_config_dict(cls):
        """获取 MySQL 配置字典（用于 db_config.py）"""
        return {
            'host': cls.MYSQL_HOST,
            'port': cls.MYSQL_PORT,
            'user': cls.MYSQL_USER,
            'password': cls.MYSQL_PASSWORD,
            'database': cls.MYSQL_DATABASE,
            'charset': cls.MYSQL_CHARSET,
            'unix_socket': cls.MYSQL_UNIX_SOCKET
        }
    
    @classmethod
    def get_redis_config_dict(cls):
        """获取 Redis 配置字典"""
        config = {
            'host': cls.REDIS_HOST,
            'port': cls.REDIS_PORT,
            'db': cls.REDIS_DB,
            'decode_responses': cls.REDIS_DECODE_RESPONSES,
            'max_connections': cls.REDIS_POOL_MAX_CONNECTIONS,
            'retry_on_timeout': cls.REDIS_POOL_RETRY_ON_TIMEOUT
        }
        if cls.REDIS_PASSWORD:
            config['password'] = cls.REDIS_PASSWORD
        return config


class DevelopmentConfig(BaseConfig):
    """开发环境配置"""
    DEBUG = True
    

class ProductionConfig(BaseConfig):
    """生产环境配置"""
    DEBUG = False
    
    # 生产环境可以覆盖基础配置
    # 例如：
    # MYSQL_HOST = 'prod-mysql-server'
    # REDIS_HOST = 'prod-redis-server'


class TestConfig(BaseConfig):
    """测试环境配置"""
    DEBUG = True
    MYSQL_DATABASE = 't11_test'  # 测试数据库
    REDIS_DB = 1  # 测试用的Redis数据库


# ============ 配置选择 ============
def get_config():
    """根据环境变量选择配置"""
    env = os.getenv('FLASK_ENV', 'development')
    
    if env == 'production':
        return ProductionConfig
    elif env == 'testing':
        return TestConfig
    else:
        return DevelopmentConfig


# ============ 导出当前配置 ============
Config = get_config()

# ============ 便捷访问方法 ============
def get_mysql_uri():
    """便捷方法：获取MySQL连接字符串"""
    return Config.get_mysql_uri()

def get_redis_uri():
    """便捷方法：获取Redis连接字符串"""
    return Config.get_redis_uri()

def get_mysql_config():
    """便捷方法：获取MySQL配置字典"""
    return Config.get_mysql_config_dict()

def get_redis_config():
    """便捷方法：获取Redis配置字典"""
    return Config.get_redis_config_dict()