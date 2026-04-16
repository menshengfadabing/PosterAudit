"""Redis 客户端与任务状态缓存辅助"""

from __future__ import annotations

from functools import lru_cache

import redis

from src.utils.config import settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_cache_url, decode_responses=True)


def set_task_status(task_id: str, status: str) -> None:
    try:
        r = get_redis()
        r.setex(f"task:{task_id}:status", settings.task_status_ttl_seconds, status)
    except Exception:
        # 状态缓存失败不应影响主流程
        return


def get_task_status(task_id: str) -> str | None:
    try:
        r = get_redis()
        return r.get(f"task:{task_id}:status")
    except Exception:
        return None
