"""Web 鉴权辅助：用户身份解析与管理员权限校验"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from urllib.parse import unquote

import httpx
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from src.utils.config import settings
from web.deps import engine
from web.models.db import User

ADMIN_ROLES = {"admin", "super_admin"}


@dataclass
class Identity:
    """当前请求身份信息"""

    username: Optional[str] = None
    real_name: Optional[str] = None
    is_admin: bool = False
    source: str = "anonymous"


async def _fetch_java_user_info(token: str) -> dict[str, Any]:
    """回源 Java 主服务获取 userInfo（通常仅含基础用户信息）"""
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


def _extract_upstream_admin_flag(data: dict[str, Any]) -> bool:
    if bool(data.get("admin") is True):
        return True

    role = str(data.get("role") or "").strip().lower()
    if role in ADMIN_ROLES:
        return True

    roles = data.get("roles")
    if isinstance(roles, list):
        return any(str(r).strip().lower() in ADMIN_ROLES for r in roles)

    return False


def _sync_local_user_and_resolve_admin(
    username: str,
    real_name: Optional[str],
    upstream_is_admin: bool,
    allow_promote_admin: bool,
) -> bool:
    """同步本地 users 表并解析管理员身份。

    规则：
    1. 管理员判定以本地 users.role 为准。
    2. 仅在 Java 鉴权场景（allow_promote_admin=True）允许把上游 admin 同步提升到本地 admin。
    3. Header 透传场景不会因为 X-User-Admin 被写入/提升管理员。
    """
    uname = (username or "").strip()
    if not uname:
        return False

    with Session(engine) as session:
        user = session.get(User, uname)
        changed = False

        if user is None:
            user = User(
                id=uname,
                name=(real_name or uname),
                role="admin" if (allow_promote_admin and upstream_is_admin) else "user",
                status="active",
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return (user.role or "").strip().lower() in ADMIN_ROLES

        if real_name and user.name != real_name:
            user.name = real_name
            changed = True

        if allow_promote_admin and upstream_is_admin and (user.role or "").strip().lower() not in ADMIN_ROLES:
            user.role = "admin"
            changed = True

        if changed:
            user.updated_at = datetime.now()
            session.add(user)
            session.commit()
            session.refresh(user)

        return (user.role or "").strip().lower() in ADMIN_ROLES


async def get_current_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    token_header: str | None = Header(default=None, alias="Token"),
    x_username: str | None = Header(default=None, alias="X-Username"),
    x_real_name: str | None = Header(default=None, alias="X-Real-Name"),
    x_real_name_enc: str | None = Header(default=None, alias="X-Real-Name-Enc"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    x_user_admin: str | None = Header(default=None, alias="X-User-Admin"),
) -> Identity:
    """解析当前用户身份。

    优先级：
    1. ENABLE_JAVA_AUTH=true 时，使用 Token/Authorization 回源 Java。
    2. 否则使用透传 Header（X-Username/X-User-Role/X-User-Admin）作为开发/网关模式兜底。

    最终管理员身份统一从本地 users.role 判定。
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
        username = data.get("username") or data.get("account") or data.get("userName")
        real_name = data.get("realName") or data.get("name")
        upstream_is_admin = _extract_upstream_admin_flag(data)

        if username:
            is_admin = _sync_local_user_and_resolve_admin(
                username=username,
                real_name=real_name,
                upstream_is_admin=upstream_is_admin,
                allow_promote_admin=True,
            )
        else:
            is_admin = False

        return Identity(
            username=username,
            real_name=real_name,
            is_admin=is_admin,
            source="java",
        )

    # 非强校验模式：允许通过 Header 透传用户上下文（可通过配置关闭）
    if not settings.allow_header_auth_fallback:
        return Identity(source="anonymous")

    username = (x_username or "").strip() or None
    real_name = (x_real_name or "").strip() or None
    if not real_name and x_real_name_enc:
        try:
            real_name = unquote(x_real_name_enc).strip() or None
        except Exception:
            real_name = None
    upstream_is_admin = _parse_bool(x_user_admin) or (x_user_role or "").strip().lower() in ADMIN_ROLES

    if username:
        is_admin = _sync_local_user_and_resolve_admin(
            username=username,
            real_name=real_name,
            upstream_is_admin=upstream_is_admin,
            allow_promote_admin=False,
        )
    else:
        is_admin = False

    return Identity(
        username=username,
        real_name=real_name,
        is_admin=is_admin,
        source="header" if (x_username or x_user_admin or x_user_role) else "anonymous",
    )


async def require_admin(identity: Identity = Depends(get_current_identity)) -> Identity:
    """管理员权限校验"""
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return identity
