"""后台统计路由（2 个接口）"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, func, desc

from web.deps import get_session, verify_api_key
from web.models.db import AuditTask, Brand, Schedule, User

router = APIRouter(dependencies=[Depends(verify_api_key)])


class ScheduleUpsert(BaseModel):
    date: str  # YYYY-MM-DD
    reviewer_ids: list[str]


@router.get("/queue/status")
def get_queue_status(session: Session = Depends(get_session)):
    """获取当前复核队列状态"""
    # 统计待复核任务数量
    pending_query = select(func.count()).select_from(AuditTask).where(AuditTask.status == "pending_review")
    pending_count = session.exec(pending_query).first() or 0

    # 获取今日待复核复核人（简化实现：暂从 User 表中查询 active 状态的 reviewer）
    reviewers_query = select(User).where(User.role == "reviewer", User.status == "active")
    reviewers = session.exec(reviewers_query).all()

    reviewers_info = []
    for r in reviewers:
        # 统计该复核人当日待复核数量（简化实现）
        today = datetime.now().strftime("%Y-%m-%d")
        task_count_query = (
            select(func.count())
            .select_from(AuditTask)
            .where(AuditTask.reviewer_id == r.id, AuditTask.review_at >= today)
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
    from datetime import timedelta

    cutoff_date = datetime.now() - timedelta(days=days)

    # 总数统计
    total_count_query = select(func.count()).select_from(AuditTask).where(AuditTask.created_at >= cutoff_date)
    total_count = session.exec(total_count_query).first() or 0

    # 按状态统计
    status_counts = {}
    for status in ("pending", "running", "completed", "failed", "pending_review"):
        q = select(func.count()).select_from(AuditTask).where(
            AuditTask.status == status,
            AuditTask.created_at >= cutoff_date,
        )
        status_counts[status] = session.exec(q).first() or 0

    # 按机审结果统计
    pass_count = 0
    fail_count = 0
    review_count = 0

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

    # 待人工复核数量（按任务状态，不是机审结果）
    pending_review_count_q = select(func.count()).select_from(AuditTask).where(
        AuditTask.status == "pending_review",
    )
    pending_review_count = session.exec(pending_review_count_q).first() or 0

    # 按品牌统计（取 top 5），关联品牌名称
    brand_query = (
        select(AuditTask.brand_id, func.count().label("count"))
        .where(AuditTask.created_at >= cutoff_date)
        .group_by(AuditTask.brand_id)
        .order_by(desc("count"))
        .limit(5)
    )
    brand_stats = session.exec(brand_query).all()

    # 查询品牌名称
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

@router.get("/reviewers")
def list_reviewers(session: Session = Depends(get_session)):
    """获取所有复核员列表"""
    reviewers = session.exec(select(User).where(User.role == "reviewer")).all()
    return [{"user_id": r.id, "name": r.name, "dept": r.dept, "status": r.status} for r in reviewers]


@router.post("/reviewers")
def create_reviewer(
    user_id: str,
    name: str,
    dept: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """新增复核员"""
    existing = session.get(User, user_id)
    if existing:
        raise HTTPException(400, detail="用户 ID 已存在")
    user = User(id=user_id, name=name, dept=dept, role="reviewer", status="active")
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
    if not user or user.role != "reviewer":
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
    """删除复核员（幂等：不存在时也返回 204）"""
    user = session.get(User, user_id)
    if not user or user.role != "reviewer":
        return
    session.delete(user)
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

    # 批量查询复核员名称
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
