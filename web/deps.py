"""Web 层依赖注入 - DB session、认证"""

import os
from typing import AsyncGenerator

from fastapi import Header, HTTPException
from sqlmodel import Session, create_engine

from src.utils.config import settings

# ── 数据库引擎 ────────────────────────────────────────────────────────────────
# 同步引擎（BackgroundTasks 中的 audit_service 是同步代码，统一用同步 session 即可）
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres123456@localhost:5432/app",
)
# asyncpg URL 格式转为 psycopg2（同步）
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


def get_session() -> Session:
    """获取数据库 Session（用于路由依赖注入）"""
    with Session(engine) as session:
        yield session


# ── API Key 认证 ──────────────────────────────────────────────────────────────
_ALLOWED_KEYS: list[str] = []


def _get_allowed_keys() -> list[str]:
    global _ALLOWED_KEYS
    if not _ALLOWED_KEYS:
        raw = os.getenv("ALLOWED_API_KEYS", "")
        _ALLOWED_KEYS = [k.strip() for k in raw.split(",") if k.strip()]
    return _ALLOWED_KEYS


async def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str | None:
    """校验 API Key，Header 名称：X-API-Key。未配置 ALLOWED_API_KEYS 时跳过鉴权。"""
    allowed = _get_allowed_keys()
    if not allowed:
        return x_api_key
    if x_api_key not in allowed:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key
