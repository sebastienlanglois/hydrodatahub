import logging
from logging.handlers import SMTPHandler, RotatingFileHandler
import os
from flask import Flask, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from redis import Redis
import rq
from config import Config
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from app.tasks.cehq import main as cehq_task

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)


    def job_function():
        print('tests')


    sched = BackgroundScheduler(daemon=True)
    # Explicitly kick off the background thread
    sched.add_job(cehq_task, 'interval', hours=24)
    sched.start()



    # Shutdown your cron thread if the web process is stopped
    atexit.register(lambda: sched.shutdown(wait=False))
    db.init_app(app)
    MIGRATION_DIR = os.path.join('migrations')
    migrate.init_app(app, db, directory=MIGRATION_DIR)
    app.redis = Redis.from_url(app.config['REDIS_URL'])
    app.task_queue = rq.Queue('microblog-tasks', connection=app.redis)

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    if not app.debug and not app.testing:
        if app.config['LOG_TO_STDOUT']:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
            app.logger.addHandler(stream_handler)
        else:
            if not os.path.exists('logs'):
                os.mkdir('logs')
            file_handler = RotatingFileHandler('logs/hydrodatahub.log',
                                               maxBytes=10240, backupCount=10)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s '
                '[in %(pathname)s:%(lineno)d]'))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('hydro-datahub startup')

    return app


from app import models
