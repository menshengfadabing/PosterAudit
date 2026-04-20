"""当前登录身份接口"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from web.auth import Identity, get_current_identity
from web.deps import get_session, verify_api_key
from web.models.db import User

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/me")
async def get_me(
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(get_session),
):
    role = None
    status = None

    if identity.username:
        user = session.get(User, identity.username)
        if user:
            role = user.role
            status = user.status

    if not role:
        role = "admin" if identity.is_admin else ("user" if identity.username else "anonymous")

    return {
        "username": identity.username,
        "real_name": identity.real_name,
        "is_admin": identity.is_admin,
        "role": role,
        "status": status,
        "source": identity.source,
    }
