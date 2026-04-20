"""后台统计路由（2 个接口）"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func, desc, and_, or_

from web.auth import require_admin
from web.deps import get_session, verify_api_key
from web.models.db import AuditTask, Brand, Schedule, User

router = APIRouter(dependencies=[Depends(verify_api_key), Depends(require_admin)])


class ScheduleUpsert(BaseModel):
    date: str  # YYYY-MM-DD
    reviewer_ids: list[str]


def _pending_review_expr():
    return or_(
        AuditTask.status == "pending_review",
        and_(
            AuditTask.machine_result == "manual_review",
            AuditTask.review_result.is_(None),
        ),
    )


@router.get("/queue/status")
def get_queue_status(session: Session = Depends(get_session)):
    """获取当前复核队列状态"""
    pending_query = select(func.count()).select_from(AuditTask).where(_pending_review_expr())
    pending_count = session.exec(pending_query).first() or 0

    reviewers_query = select(User).where(User.role == "admin", User.status == "active")
    reviewers = session.exec(reviewers_query).all()

    reviewers_info = []
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for r in reviewers:
        task_count_query = (
            select(func.count())
            .select_from(AuditTask)
            .where(AuditTask.reviewer_id == r.id, AuditTask.review_at >= today_start)
        )
        task_count = session.exec(task_count_query).first() or 0

        reviewers_info.append({
            "user_id": r.id,
            "name": r.name,
            "status": "空闲" if task_count < 5 else "忙碌",
            "pending_count": task_count,
        })

    return {
        "current_queue": pending_count,
        "reviewers_on_duty": len(reviewers_info),
        "reviewers": reviewers_info,
    }


@router.get("/history/stats")
def get_history_stats(
    days: int = 7,
    session: Session = Depends(get_session),
):
    """获取历史统计数据（最近 N 天）"""
    cutoff_date = datetime.now() - timedelta(days=days)

    total_count_query = select(func.count()).select_from(AuditTask).where(AuditTask.created_at >= cutoff_date)
    total_count = session.exec(total_count_query).first() or 0

    status_counts = {}
    for status in ("pending", "running", "completed", "failed", "pending_review"):
        q = select(func.count()).select_from(AuditTask).where(
            AuditTask.status == status,
            AuditTask.created_at >= cutoff_date,
        )
        status_counts[status] = session.exec(q).first() or 0

    q = select(func.count()).select_from(AuditTask).where(
        AuditTask.machine_result == "passed",
        AuditTask.created_at >= cutoff_date,
    )
    pass_count = session.exec(q).first() or 0

    q = select(func.count()).select_from(AuditTask).where(
        AuditTask.machine_result == "failed",
        AuditTask.created_at >= cutoff_date,
    )
    fail_count = session.exec(q).first() or 0

    q = select(func.count()).select_from(AuditTask).where(
        AuditTask.machine_result == "manual_review",
        AuditTask.created_at >= cutoff_date,
    )
    review_count = session.exec(q).first() or 0

    pending_review_count_q = select(func.count()).select_from(AuditTask).where(_pending_review_expr())
    pending_review_count = session.exec(pending_review_count_q).first() or 0

    brand_query = (
        select(AuditTask.brand_id, func.count().label("count"))
        .where(AuditTask.created_at >= cutoff_date)
        .group_by(AuditTask.brand_id)
        .order_by(desc("count"))
        .limit(5)
    )
    brand_stats = session.exec(brand_query).all()

    brand_ids = [b[0] for b in brand_stats]
    brands_map: dict[str, str] = {}
    if brand_ids:
        brands_q = select(Brand).where(Brand.id.in_(brand_ids))
        for brand in session.exec(brands_q).all():
            brands_map[brand.id] = brand.name

    return {
        "days": days,
        "total_tasks": total_count,
        "status_breakdown": status_counts,
        "result_breakdown": {
            "passed": pass_count,
            "failed": fail_count,
            "manual_review": review_count,
        },
        "pending_review_count": pending_review_count,
        "top_brands": [
            {"brand_id": b[0], "brand_name": brands_map.get(b[0], b[0]), "count": b[1]} for b in brand_stats
        ],
    }


# ── 排班管理 ──────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    """获取用户列表（管理员）"""
    query = select(User)

    role_filter = (role or "").strip().lower()
    if role_filter:
        query = query.where(User.role == role_filter)

    ql = (q or "").strip()
    if ql:
        like = f"%{ql}%"
        query = query.where(
            or_(
                User.id.ilike(like),
                User.name.ilike(like),
                User.dept.ilike(like),
            )
        )

    query = query.order_by(User.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    users = session.exec(query).all()

    return [
        {
            "user_id": u.id,
            "name": u.name,
            "dept": u.dept,
            "role": u.role,
            "status": u.status,
            "updated_at": u.updated_at,
        }
        for u in users
    ]


@router.get("/reviewers")
def list_reviewers(session: Session = Depends(get_session)):
    """获取所有复核员列表"""
    reviewers = session.exec(select(User).where(User.role == "admin")).all()
    return [{"user_id": r.id, "name": r.name, "dept": r.dept, "status": r.status} for r in reviewers]


@router.post("/reviewers")
def create_reviewer(
    user_id: str,
    name: Optional[str] = None,
    dept: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """新增复核员；若用户已存在则升级为 reviewer。"""
    existing = session.get(User, user_id)
    if existing:
        existing.role = "admin"
        existing.status = "active"
        if name is not None and name.strip():
            existing.name = name.strip()
        if dept is not None:
            existing.dept = dept
        existing.updated_at = datetime.now()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return {"user_id": existing.id, "name": existing.name, "dept": existing.dept, "status": existing.status}

    user = User(id=user_id, name=(name or user_id), dept=dept, role="admin", status="active")
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"user_id": user.id, "name": user.name, "dept": user.dept, "status": user.status}


@router.put("/reviewers/{user_id}")
def update_reviewer(
    user_id: str,
    name: Optional[str] = None,
    dept: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """更新复核员信息"""
    user = session.get(User, user_id)
    if not user or user.role != "admin":
        raise HTTPException(404, detail="复核员不存在")
    if name is not None:
        user.name = name
    if dept is not None:
        user.dept = dept
    if status is not None:
        user.status = status
    user.updated_at = datetime.now()
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"user_id": user.id, "name": user.name, "dept": user.dept, "status": user.status}


@router.delete("/reviewers/{user_id}", status_code=204)
def delete_reviewer(user_id: str, session: Session = Depends(get_session)):
    """删除复核员权限（降级为普通用户，幂等）"""
    user = session.get(User, user_id)
    if not user:
        return

    if user.role == "admin":
        user.role = "user"
        user.updated_at = datetime.now()
        session.add(user)

        schedules = session.exec(select(Schedule)).all()
        for s in schedules:
            ids = list(s.reviewer_ids or [])
            if user_id in ids:
                s.reviewer_ids = [i for i in ids if i != user_id]
                session.add(s)

        session.commit()


@router.get("/schedules")
def list_schedules(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """获取排班列表，可按日期范围筛选"""
    query = select(Schedule).order_by(Schedule.date)
    if start_date:
        query = query.where(Schedule.date >= start_date)
    if end_date:
        query = query.where(Schedule.date <= end_date)
    schedules = session.exec(query).all()

    all_ids: set[str] = set()
    for s in schedules:
        all_ids.update(s.reviewer_ids or [])
    name_map: dict[str, str] = {}
    if all_ids:
        for u in session.exec(select(User).where(User.id.in_(list(all_ids)))).all():
            name_map[u.id] = u.name

    return [
        {
            "id": s.id,
            "date": s.date,
            "reviewer_ids": s.reviewer_ids or [],
            "reviewers": [{"user_id": uid, "name": name_map.get(uid, uid)} for uid in (s.reviewer_ids or [])],
        }
        for s in schedules
    ]


@router.post("/schedules")
def upsert_schedule(body: ScheduleUpsert, session: Session = Depends(get_session)):
    """新增或更新某日排班（同一日期只保留一条记录）"""
    existing = session.exec(select(Schedule).where(Schedule.date == body.date)).first()
    if existing:
        existing.reviewer_ids = body.reviewer_ids
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return {"id": existing.id, "date": existing.date, "reviewer_ids": existing.reviewer_ids}
    schedule = Schedule(id=str(uuid.uuid4()), date=body.date, reviewer_ids=body.reviewer_ids)
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return {"id": schedule.id, "date": schedule.date, "reviewer_ids": schedule.reviewer_ids}


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, session: Session = Depends(get_session)):
    """删除排班记录"""
    schedule = session.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(404, detail="排班记录不存在")
    session.delete(schedule)
    session.commit()
