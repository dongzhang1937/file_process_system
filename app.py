from file_process import myapp
from file_process.models.auth import au
from file_process.models.documents import docu
from extensions import celery
app = myapp()
celery = app.extensions.get('celery', celery)
if __name__ == '__main__':
    # print(app.config)

    app.run()