from flask_sqlalchemy import SQLAlchemy
from celery import Celery

# 这里只创建对象，不绑定 app
db = SQLAlchemy()
celery = Celery()