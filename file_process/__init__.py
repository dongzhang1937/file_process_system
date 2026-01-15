import os
import sys
from flask import Flask
from .models.auth import au
from .models.documents import docu
from .models.fileprocess import docp
#from .models.fileupload import upload_bp
from flask import request,session,redirect
from extensions import db, celery # 导入扩展
from config.logging_config import setup_logging, logger

# 添加父目录到路径，以便导入统一配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.app_config import Config

# 登录验证
def auth_required():
    #auth_required也要将static目录排除掉，不然before_request会将里面的css样式都给禁用掉了
    if (request.path == '/' or 
        request.path == '/register' or 
        request.path.startswith('/static') or 
        request.path.startswith('/images') or
        request.path == '/logout'):
        return
    
    user_info = session.get('user')
    if user_info is None:
        # 如果是 API 请求，返回 JSON 错误而不是重定向
        if request.path.startswith('/api/'):
            from flask import jsonify
            return jsonify({
                'success': False,
                'error': '用户未登录',
                'code': 'UNAUTHORIZED'
            }), 401
        else:
            return redirect('/')


def myapp():
    # 1. 在 app 创建前就初始化日志，确保能捕获启动过程的日志
    setup_logging()
    # 获取项目根目录
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    app = Flask(__name__)
    # 使用绝对路径加载配置文件
    app.config.from_pyfile(os.path.join(basedir, 'config', 'app_config.py'))

# 1. 加载配置 - 使用统一配置
    app.config['SECRET_KEY'] = Config.SECRET_KEY
    app.config['DEBUG'] = Config.DEBUG
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.get_mysql_uri()
    app.config['CELERY_BROKER_URL'] = Config.get_redis_uri()
    app.config['CELERY_RESULT_BACKEND'] = Config.get_mysql_celery_uri()
    # 优化 Celery Redis 连接池设置 (可选)
    app.config['CELERY_BROKER_TRANSPORT_OPTIONS'] = {
        'visibility_timeout': 3600,
        'max_connections': Config.REDIS_POOL_MAX_CONNECTIONS, # 使用统一配置
    }
    # 添加上传所需的配置
    app.config['UPLOAD_FOLDER'] = 'uploads/temp'
    app.config['FINAL_FOLDER'] = 'uploads/final'

# 2. 初始化扩展
    db.init_app(app)
    
    # 初始化 Celery
    # 【核心修改】初始化 Celery 配置
    # 不要直接 update(app.config)，而是显式指定 key，确保 Celery 能认出来
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],        # 映射到 broker_url
        result_backend=app.config['CELERY_RESULT_BACKEND'],# 映射到 result_backend
        broker_connection_retry_on_startup=True,           # 建议加上这个，防止启动警告
        # 如果还有其他配置，比如连接池，也可以在这里加上
        broker_transport_options = {
            'visibility_timeout': 3600,
            'max_connections': Config.REDIS_POOL_MAX_CONNECTIONS,
        }
    )
    # 在 celery 配置完成后再导入 upload_bp
    from .models.fileupload import upload_bp  # ← 添加到这里
    from .models.prodetail import doc_proc, recover_orphaned_tasks
    from .models.static_files import static_bp  # 添加静态文件蓝图
    from .models.chat_db_doc import chatdoc
    from .models.llm_routes import llm_bp  # LLM功能蓝图
    app.register_blueprint(au)
    app.register_blueprint(docu)
    app.register_blueprint(docp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(doc_proc)
    app.register_blueprint(static_bp)  # 注册静态文件蓝图
    app.register_blueprint(chatdoc)
    app.register_blueprint(llm_bp)  # 注册LLM功能蓝图 
    app.before_request(auth_required)

    # 应用启动时恢复孤儿任务
    try:
        with app.app_context():
            recover_orphaned_tasks()
            logger.info("应用启动时任务恢复检查完成")
    except Exception as e:
        logger.error(f"应用启动时任务恢复失败: {e}")

    return app





# if __name__ == '__main__':
#     app.run(debug=True)