from celery import Celery
import sys
import os

# 添加父目录到路径，以便导入统一配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from config.app_config import Config

# 创建 celery 实例
celery = Celery('file_process')

# 配置 - 使用统一配置
celery.conf.update(
    broker_url=Config.get_redis_uri(),
    result_backend=Config.get_mysql_celery_uri(),
    broker_transport_options={
        'visibility_timeout': 3600,
        'max_connections': Config.REDIS_POOL_MAX_CONNECTIONS,
    }
)

# 手动导入任务模块，确保任务被注册
try:
    from . import fileupload
    from . import prodetail
    from . import word_parser
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    try:
        from file_process.models import fileupload
        from file_process.models import prodetail
        from file_process.models import word_parser
    except ImportError:
        pass  # 任务会在运行时动态导入

'''
完整的工作流程：

Flask 应用启动时，fileupload.py 和 prodetail.py 导入 celery_app.celery，任务使用配置好的 Redis
Worker 启动时，celery -A file_process.models.celery_app 加载同一个 celery 配置
两边都连接到 redis://127.0.0.1:6379/0
'''