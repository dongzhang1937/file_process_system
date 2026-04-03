from flask_sqlalchemy import SQLAlchemy

# 这里只创建对象，不绑定 app
# Celery 实例已统一到 file_process/models/celery_app.py
db = SQLAlchemy()