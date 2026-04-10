"""后台统计路由（2 个接口）"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func, desc

from web.deps import get_session, verify_api_key
from web.models.db import AuditTask, User

router = APIRouter(dependencies=[Depends(verify_api_key)])


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

    # 按品牌统计（取 top 5）
    brand_query = (
        select(AuditTask.brand_id, func.count().label("count"))
        .where(AuditTask.created_at >= cutoff_date)
        .group_by(AuditTask.brand_id)
        .order_by(desc("count"))
        .limit(5)
    )
    brand_stats = session.exec(brand_query).all()

    return {
        "days": days,
        "total_tasks": total_count,
        "status_breakdown": status_counts,
        "result_breakdown": {
            "passed": pass_count,
            "failed": fail_count,
            "manual_review": review_count,
        },
        "top_brands": [
            {"brand_id": b[0], "count": b[1]} for b in brand_stats
        ],
    }
