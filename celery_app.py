"""Celery 应用配置"""

from celery import Celery

from src.utils.config import settings


celery = Celery("audit")
celery.conf.update(
    broker_url=settings.redis_url,
    result_backend=settings.redis_result_url,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    worker_concurrency=settings.celery_worker_concurrency,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=480,
    task_default_retry_delay=30,
    task_max_retries=2,
    result_expires=3600,
    # 显式包含任务模块，避免 worker 启动后出现 "Received unregistered task"
    imports=("web.tasks.audit_task",),
)

# 再做一次自动发现，兼容后续新增任务文件
celery.autodiscover_tasks(["web.tasks"])
