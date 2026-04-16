"""Web 鉴权辅助：用户身份解析与管理员权限校验"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx
from fastapi import Depends, Header, HTTPException

from src.utils.config import settings


@dataclass
class Identity:
    """当前请求身份信息"""

    username: Optional[str] = None
    real_name: Optional[str] = None
    is_admin: bool = False
    source: str = "anonymous"


async def _fetch_java_user_info(token: str) -> dict[str, Any]:
    """回源 Java 主服务获取 userInfo（含 admin 字段）"""
    url = settings.java_userinfo_url.strip()
    if not url:
        raise HTTPException(status_code=500, detail="JAVA_USERINFO_URL 未配置")

    headers = {settings.java_token_header: token}
    async with httpx.AsyncClient(timeout=settings.java_auth_timeout_seconds) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code >= 400:
        raise HTTPException(status_code=401, detail="用户身份验证失败")

    try:
        payload = resp.json()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=401, detail="用户身份响应解析失败") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise HTTPException(status_code=401, detail="用户身份响应缺少 data 字段")
    return data


def _parse_bool(value: Optional[str]) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


async def get_current_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    token_header: str | None = Header(default=None, alias="Token"),
    x_username: str | None = Header(default=None, alias="X-Username"),
    x_real_name: str | None = Header(default=None, alias="X-Real-Name"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_user_admin: str | None = Header(default=None, alias="X-User-Admin"),
) -> Identity:
    """解析当前用户身份。

    优先级：
    1. ENABLE_JAVA_AUTH=true 时，使用 Token/Authorization 回源 Java。
    2. 否则使用透传 Header（X-Username/X-User-Role/X-User-Admin）作为开发/网关模式兜底。
    """
    token: Optional[str] = None
    if token_header:
        token = token_header.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if settings.enable_java_auth:
        if not token:
            raise HTTPException(status_code=401, detail="缺少用户凭证")
        data = await _fetch_java_user_info(token)
        return Identity(
            username=data.get("username") or data.get("account") or data.get("userName"),
            real_name=data.get("realName") or data.get("name"),
            is_admin=bool(data.get("admin") is True),
            source="java",
        )

    # 非强校验模式：允许通过 Header 透传用户上下文
    is_admin = _parse_bool(x_user_admin) or (x_user_role or "").strip().lower() == "admin"
    return Identity(
        username=(x_username or "").strip() or None,
        real_name=(x_real_name or "").strip() or None,
        is_admin=is_admin,
        source="header" if (x_username or x_user_admin or x_user_role) else "anonymous",
    )


async def require_admin(identity: Identity = Depends(get_current_identity)) -> Identity:
    """管理员权限校验"""
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return identity
