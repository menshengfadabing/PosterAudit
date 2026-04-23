"""审核任务 Celery worker"""

from __future__ import annotations

import asyncio

from celery_app import celery
from src.utils.redis_client import set_task_status


@celery.task(bind=True, name="audit.run", max_retries=2, queue="audit")
def run_audit_task(
    self,
    task_id: str,
    brand_id: str,
    image_paths: list[str],
    batch_size: int | None,
    compression: str,
    preconditions: dict | None,
):
    """Celery 任务入口：复用现有 _run_audit 逻辑"""
    try:
        set_task_status(task_id, "pending")
        # 延迟导入，避免循环依赖
        from web.routers.audit import _run_audit

        set_task_status(task_id, "running")
        asyncio.run(_run_audit(task_id, brand_id, image_paths, batch_size, compression, preconditions))
        set_task_status(task_id, "completed")
        return {"task_id": task_id, "status": "completed"}
    except Exception as exc:
        set_task_status(task_id, "failed")
        raise self.retry(exc=exc, countdown=30)


@celery.task(bind=True, name="audit.run_batch", max_retries=2, queue="audit")
def run_batch_audit_task(
    self,
    task_ids: list[str],
    brand_id: str,
    image_paths: list[str],
    batch_size: int | None,
    compression: str,
    preconditions: dict | None,
):
    """Celery 任务入口：批量审核（同系列图片合并审核，结果分发到各个独立任务）"""
    try:
        for tid in task_ids:
            set_task_status(tid, "pending")
        from web.routers.audit import _run_batch_audit

        asyncio.run(_run_batch_audit(task_ids, brand_id, image_paths, batch_size, compression, preconditions))
        return {"task_ids": task_ids, "status": "completed"}
    except Exception as exc:
        for tid in task_ids:
            set_task_status(tid, "failed")
        raise self.retry(exc=exc, countdown=30)
