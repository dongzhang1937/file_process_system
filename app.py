from file_process import myapp
from file_process.models.celery_app import celery as _celery

celery = _celery
app = myapp()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
