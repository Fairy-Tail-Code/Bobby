"""
Celery Worker 入口
使用方式: celery -A app.celery_worker worker --loglevel=info
"""
from app.celery_app import celery_app

if __name__ == "__main__":
    celery_app.start()
