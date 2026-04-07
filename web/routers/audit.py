"""审核提交 + 任务查询 + 历史记录路由（3个接口）"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select, desc

from src.services.audit_service import audit_service
from src.services.rules_context import rules_context
from src.utils.config import get_app_dir
from web.deps import get_session, verify_api_key
from web.models.db import AuditTask, Brand

router = APIRouter(dependencies=[Depends(verify_api_key)])

UPLOAD_DIR = get_app_dir() / "data" / "uploads"


# ── 审核提交 ────────────────────────────────────────────────────��─────────────

@router.post("/audit")
async def submit_audit(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] = File(..., description="待审核设计稿，可批量上传"),
    brand_id: str = Form(...),
    mode: str = Form("async", description="async=异步（返回task_id轮询）；sync=同步（直接等待结果）"),
    batch_size: Optional[int] = Form(None, description="每批图片数，默认 auto"),
    compression: str = Form("balanced", description="压缩预设：high_quality/balanced/high_compression/no_compression"),
    session: Session = Depends(get_session),
):
    """
    提交审核任务，待审核图片随请求内联上传。

    - `mode=async`：立即返回 task_id，客户端通过 GET /tasks/{task_id} 轮询结果
    - `mode=sync`：等待审核完成后直接返回结果（���合单张小图快速测试）
    """
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")

    # 保存上传文件到临时目录
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    task_id = str(uuid.uuid4())
    task_dir = UPLOAD_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    image_paths = []
    for img_file in images:
        dest = task_dir / (img_file.filename or f"{uuid.uuid4().hex}.jpg")
        content = await img_file.read()
        dest.write_bytes(content)
        image_paths.append(str(dest))

    input_meta = {
        "image_count": len(image_paths),
        "batch_size": batch_size,
        "compression": compression,
        "filenames": [p.split("/")[-1] for p in image_paths],
    }

    # 写入任务记录
    task = AuditTask(
        id=task_id,
        brand_id=brand_id,
        status="pending",
        input_meta=input_meta,
    )
    session.add(task)
    session.commit()

    if mode == "sync":
        # 同步模式：直接在当前线程中运行，等待完成
        results = await _run_audit(task_id, brand_id, image_paths, batch_size, compression)
        # 刷新获取最新结果
        session.refresh(task)
        return {"task_id": task_id, "status": task.status, "results": task.results}

    # 异步模式：在后台任务中运行
    background_tasks.add_task(_run_audit, task_id, brand_id, image_paths, batch_size, compression)
    return {"task_id": task_id, "status": "pending", "created_at": task.created_at}


async def _run_audit(
    task_id: str,
    brand_id: str,
    image_paths: list[str],
    batch_size: Optional[int],
    compression: str,
) -> list:
    """在线程池中执行同步审核，不阻塞事件循环"""
    from sqlmodel import Session as SyncSession
    from web.deps import engine

    def _do_audit():
        # 设置压缩预设
        preset = audit_service.COMPRESSION_PRESETS.get(compression, audit_service.COMPRESSION_PRESETS["balanced"])
        audit_service.set_compression_config(preset)

        # 更新任务状态为 running
        with SyncSession(engine) as s:
            task = s.get(AuditTask, task_id)
            if task:
                task.status = "running"
                task.updated_at = datetime.now()
                s.add(task)
                s.commit()

        try:
            reports = audit_service.batch_audit_merged(
                image_paths=image_paths,
                brand_id=brand_id,
                max_images_per_request=batch_size,
            )
            # batch_audit_merged 返回 [{"file_name": ..., "status": ..., "report": AuditReport}, ...]
            # 需要将嵌套的 Pydantic 模型序列化为 plain dict
            def _serialize(r):
                if not isinstance(r, dict):
                    return r.model_dump(mode="json") if hasattr(r, "model_dump") else r
                out = dict(r)
                if "report" in out and hasattr(out["report"], "model_dump"):
                    out["report"] = out["report"].model_dump(mode="json")
                return out

            results = [_serialize(r) for r in reports]

            with SyncSession(engine) as s:
                task = s.get(AuditTask, task_id)
                if task:
                    task.status = "completed"
                    task.results = results
                    task.updated_at = datetime.now()
                    s.add(task)
                    s.commit()

            return results

        except Exception as e:
            with SyncSession(engine) as s:
                task = s.get(AuditTask, task_id)
                if task:
                    task.status = "failed"
                    task.error = str(e)
                    task.updated_at = datetime.now()
                    s.add(task)
                    s.commit()
            raise

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_audit)


# ── 任务查询 ──────────────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}")
def get_task(task_id: str, session: Session = Depends(get_session)):
    """查询任务状态和结果（客户端轮询）"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")

    resp = {
        "task_id": task.id,
        "brand_id": task.brand_id,
        "status": task.status,
        "input_meta": task.input_meta,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "error": task.error,
    }
    if task.status == "completed":
        resp["results"] = task.results
    return resp


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, session: Session = Depends(get_session)):
    """删除单条审核历史记录"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    session.delete(task)
    session.commit()




@router.get("/history")
def list_history(
    brand_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    session: Session = Depends(get_session),
):
    """审核历史列表，支持按品牌筛选和分页"""
    query = select(AuditTask).order_by(desc(AuditTask.created_at))
    if brand_id:
        query = query.where(AuditTask.brand_id == brand_id)

    total = len(session.exec(query).all())
    tasks = session.exec(query.offset((page - 1) * page_size).limit(page_size)).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "task_id": t.id,
                "brand_id": t.brand_id,
                "status": t.status,
                "image_count": (t.input_meta or {}).get("image_count", 0),
                "created_at": t.created_at,
                "results": t.results,
            }
            for t in tasks
        ],
    }
