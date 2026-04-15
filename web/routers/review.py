"""人工复核路由（4 个接口）"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, desc

from web.deps import get_session, verify_api_key
from web.models.db import AuditTask, Schedule, User

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/review/tasks")
def list_review_tasks(
    status: Optional[str] = Query(None, description="待复核 pending_review/已复核 completed_review"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """
    获取复核队列中的任务列表。

    - `status=pending_review`: 待复核任务
    - `status=completed_review`: 已复核任务
    """
    query = select(AuditTask).order_by(desc(AuditTask.created_at))

    if status == "pending_review":
        query = query.where(AuditTask.status == "pending_review")
    elif status == "completed_review":
        query = query.where(AuditTask.review_at.isnot(None))

    total = len(session.exec(query).all())
    tasks = session.exec(query.offset((page - 1) * page_size).limit(page_size)).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "task_id": t.id,
                "name": t.name,
                "brand_id": t.brand_id,
                "status": t.status,
                "machine_result": t.machine_result,
                "created_at": t.created_at,
                "input_meta": t.input_meta,
                "formatted_report": t.formatted_report,
                "review_result": t.review_result,
                "review_comment": t.review_comment,
            }
            for t in tasks
        ],
    }


@router.get("/review/tasks/{task_id}")
def get_review_task(task_id: str, session: Session = Depends(get_session)):
    """获取单个复核任务的详细信息，包括原始报告"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")

    return {
        "task_id": task.id,
        "name": task.name,
        "brand_id": task.brand_id,
        "status": task.status,
        "machine_result": task.machine_result,
        "created_at": task.created_at,
        "input_meta": task.input_meta,
        "formatted_report": task.formatted_report,
        "results": task.results,
        "review_result": task.review_result,
        "review_comment": task.review_comment,
        "review_at": task.review_at,
        "per_image_reviews": task.per_image_reviews or [],
    }


@router.post("/review/tasks/{task_id}/image-decision")
def submit_image_review_decision(
    task_id: str,
    image_index: int = Query(..., ge=0, description="图片索引（0起始）"),
    decision: str = Query(..., description="复核结果：passed/failed"),
    comment: Optional[str] = Query(None, description="复核意见"),
    session: Session = Depends(get_session),
):
    """提交单张图片的复核结果。所有图片复核完毕后自动生成整体结论。"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    if task.status != "pending_review":
        raise HTTPException(400, detail="当前任务状态不支持提交复核结果")
    if decision not in ("passed", "failed"):
        raise HTTPException(400, detail="decision 必须是 passed 或 failed")

    total_images = len((task.input_meta or {}).get("filenames", []))
    if total_images > 0 and image_index >= total_images:
        raise HTTPException(400, detail="图片索引超出范围")

    # 更新 per_image_reviews
    reviews: list[dict] = list(task.per_image_reviews or [])
    existing = next((r for r in reviews if r.get("image_index") == image_index), None)
    if existing:
        existing["result"] = decision
        existing["comment"] = comment or ""
    else:
        reviews.append({"image_index": image_index, "result": decision, "comment": comment or ""})
    task.per_image_reviews = reviews

    # 如果所有图片都已复核，自动提交整体结论（最差原则：有 failed → failed，否则 passed）
    reviewed_indices = {r["image_index"] for r in reviews}
    all_done = total_images > 0 and reviewed_indices == set(range(total_images))
    if all_done:
        overall = "failed" if any(r["result"] == "failed" for r in reviews) else "passed"
        task.review_result = overall
        task.review_comment = "; ".join(
            f"图片{r['image_index']+1}: {r['comment']}" for r in sorted(reviews, key=lambda x: x["image_index"]) if r.get("comment")
        ) or None
        task.review_at = datetime.now()
        task.status = "completed"
        task.updated_at = datetime.now()

        # 关联当日排班：查找今日的 Schedule，写入 reviewer_ids
        today = datetime.now().strftime("%Y-%m-%d")
        schedule = session.exec(select(Schedule).where(Schedule.date == today)).first()
        if schedule and schedule.reviewer_ids:
            task.reviewer_ids = schedule.reviewer_ids

    session.add(task)
    session.commit()
    session.refresh(task)

    return {
        "task_id": task_id,
        "image_index": image_index,
        "result": decision,
        "all_done": all_done,
        "review_result": task.review_result,
        "per_image_reviews": task.per_image_reviews,
    }


@router.get("/review/tasks/{task_id}/image")
def get_review_task_image(
    task_id: str,
    index: int = Query(0, ge=0, description="图片索引，多张图片时使用"),
    session: Session = Depends(get_session),
):
    """获取任务的图片流（用于前端展示）"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")

    input_meta = task.input_meta or {}
    filenames = input_meta.get("filenames", [])
    if not filenames:
        raise HTTPException(404, detail="未找到图片文件")

    if index >= len(filenames):
        raise HTTPException(400, detail="图片索引超出范围")

    # 返回文件名，实际实现中应返回文件流或 URL
    return {
        "task_id": task_id,
        "index": index,
        "filename": filenames[index],
        "total_images": len(filenames),
    }


@router.post("/review/tasks/{task_id}/decision")
def submit_review_decision(
    task_id: str,
    decision: str = Query(..., description="复核结果：passed/failed"),
    comment: Optional[str] = Query(None, description="复核意见"),
    session: Session = Depends(get_session),
):
    """
    提交人工复核结果。

    - `decision=passed`: 复核通过
    - `decision=failed`: 复核不通过
    """
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    if task.status != "pending_review":
        raise HTTPException(400, detail="当前任务状态不支持提交复核结果")

    if decision not in ("passed", "failed"):
        raise HTTPException(400, detail="decision 必须是 passed 或 failed")

    task.review_result = decision
    task.review_comment = comment
    task.review_at = datetime.now()
    task.status = "completed"
    task.machine_result = decision  # 更新机审结果为复核结果
    task.updated_at = datetime.now()

    # 关联当日排班：查找今日的 Schedule，写入 reviewer_ids
    today = datetime.now().strftime("%Y-%m-%d")
    schedule = session.exec(select(Schedule).where(Schedule.date == today)).first()
    if schedule and schedule.reviewer_ids:
        task.reviewer_ids = schedule.reviewer_ids

    session.add(task)
    session.commit()
    session.refresh(task)

    return {
        "task_id": task_id,
        "review_result": task.review_result,
        "message": "复核结果已提交",
    }
