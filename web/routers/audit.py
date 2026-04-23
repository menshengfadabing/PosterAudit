"""审核提交 + 任务查询 + 历史记录路由（3个接口）"""

import asyncio
import mimetypes
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session, desc, func, select

from src.services.audit_service import audit_service
from src.services.rules_context import rules_context
from src.utils.config import get_app_dir, settings
from src.utils.object_storage import object_storage
from src.utils.redis_client import get_task_status, set_task_status
from web.auth import Identity, get_current_identity
from web.deps import get_session, verify_api_key
from web.models.db import AuditTask, Brand, User

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _is_admin(identity: Identity) -> bool:
    return identity.is_admin

def _ensure_task_access(task: AuditTask, identity: Identity) -> None:
    if _is_admin(identity) or not settings.enable_user_isolation:
        return
    if not identity.username:
        raise HTTPException(403, detail="缺少用户身份，无法访问该任务")
    if task.created_by and task.created_by != identity.username:
        raise HTTPException(403, detail="无权限访问该任务")


def _legacy_upload_dir() -> Path:
    """本地文件兜底目录（兼容历史任务/未启用对象存储场景）"""
    custom_dir = (settings.upload_dir or "").strip()
    if custom_dir:
        return Path(custom_dir)
    return get_app_dir() / "data" / "uploads"

# ── 审核提交 ────────────────────────────────────────────────────��─────────────

@router.post("/audit")
async def submit_audit(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] = File(..., description="待审核设计稿，可批量上传"),
    brand_id: str = Form(...),
    mode: str = Form("async", description="async=异步（返回task_id轮询）；sync=同步（直接等待结果）"),
    batch_size: Optional[int] = Form(None, description="每批图片数，默认 auto"),
    compression: str = Form("balanced", description="压缩预设：high_quality/balanced/high_compression/no_compression"),
    preconditions: Optional[str] = Form(None, description="前置条件 JSON 字符串"),
    same_series_material: Optional[str] = Form(None, description="是否为同一系列物料：yes/no"),
    image_purpose: Optional[str] = Form(None, description="图片用途"),
    project_type: Optional[str] = Form(None, description="项目类型"),
    project_desc: Optional[str] = Form(None, description="项目描述"),
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(get_session),
):
    """
    提交审核任务，待审核图片随请求内联上传。

    - `mode=async`：立即返回 task_id，客户端通过 GET /tasks/{task_id} 轮询结果
    - `mode=sync`：等待审核完成后直接返回结果（适合单张小图快速测试）
    - `same_series_material=yes`：启用合并审核策略，每批次至少 2 张，禁用多 Key 轮询
    """
    import json as _json

    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")

    # 解析前置条件
    preconditions_dict: Optional[dict] = None
    if preconditions:
        try:
            preconditions_dict = _json.loads(preconditions)
        except Exception:
            raise HTTPException(400, detail="preconditions 格式错误，需要合法的 JSON 字符串")

    # 将 same_series_material 注入到前置条件中（供后端策略使用）
    if same_series_material and preconditions_dict is not None:
        preconditions_dict["is_same_series_material"] = same_series_material

    # 为同系列物料生成 batch_id
    is_same_series = same_series_material == "yes"
    batch_id = str(uuid.uuid4()) if is_same_series else None

    # 为每张图片创建独立的任务
    task_ids: list[str] = []
    all_image_data: list[tuple[str, str, str]] = []  # (task_id, filename, image_path)

    upload_dir: Optional[Path] = None
    if not object_storage.enabled:
        upload_dir = _legacy_upload_dir()
        upload_dir.mkdir(parents=True, exist_ok=True)

    for img_file in images:
        content = await img_file.read()
        filename = Path(img_file.filename or f"{uuid.uuid4().hex}.jpg").name
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)

        # 上传图片到对象存储或本地
        if object_storage.enabled:
            mime_type = (img_file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream")
            object_key = object_storage.build_task_image_key(task_id, filename)
            object_storage.put_bytes(object_key, content, mime_type)
            image_path = filename  # 对象存储模式下，异步任务仅传文件名
        else:
            task_dir = upload_dir / task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            dest = task_dir / filename
            dest.write_bytes(content)
            image_path = str(dest)

        all_image_data.append((task_id, filename, image_path))

        # 为每张图片创建独立的任务记录
        input_meta = {
            "image_count": 1,
            "batch_size": batch_size,
            "compression": compression,
            "filenames": [filename],
            "preconditions": preconditions_dict,
            "same_series_material": same_series_material,
        }

        task = AuditTask(
            id=task_id,
            batch_id=batch_id,
            brand_id=brand_id,
            name=filename,
            created_by=identity.username,
            image_purpose=image_purpose,
            project_type=project_type,
            project_desc=project_desc,
            status="pending",
            input_meta=input_meta,
        )
        session.add(task)

    # 同步提交用户信息（用于后续列表显示中文姓名）
    if identity.username:
        creator = session.get(User, identity.username)
        if creator is None:
            creator = User(
                id=identity.username,
                name=identity.real_name or identity.username,
                role="user",
                status="active",
            )
        elif identity.real_name and creator.name != identity.real_name:
            creator.name = identity.real_name
            creator.updated_at = datetime.now()
        session.add(creator)

    session.commit()

    if mode == "sync":
        # 同步模式：逐张审核
        for tid, filename, image_path in all_image_data:
            await _run_audit(tid, brand_id, [image_path], batch_size, compression, preconditions_dict)
        return {"task_ids": task_ids, "status": "pending"}

    # 异步模式：为每张图片分别提交后台任务
    if is_same_series and len(task_ids) > 1:
        # 同系列物料：合并审核，一次性处理所有图片
        image_paths_list = [d[2] for d in all_image_data]
        if settings.use_celery:
            try:
                from web.tasks.audit_task import run_batch_audit_task
                for tid in task_ids:
                    set_task_status(tid, "pending")
                run_batch_audit_task.delay(task_ids, brand_id, image_paths_list, batch_size, compression, preconditions_dict)
                return {"task_ids": task_ids, "status": "pending", "executor": "celery"}
            except Exception:
                pass
        background_tasks.add_task(_run_batch_audit, task_ids, brand_id, image_paths_list, batch_size, compression, preconditions_dict)
        for tid in task_ids:
            set_task_status(tid, "pending")
    else:
        # 非同系列：每张图片独立审核
        for tid, filename, image_path in all_image_data:
            if settings.use_celery:
                try:
                    from web.tasks.audit_task import run_audit_task
                    set_task_status(tid, "pending")
                    run_audit_task.delay(tid, brand_id, [image_path], batch_size, compression, preconditions_dict)
                    continue
                except Exception:
                    pass
            background_tasks.add_task(_run_audit, tid, brand_id, [image_path], batch_size, compression, preconditions_dict)
            set_task_status(tid, "pending")

    return {"task_ids": task_ids, "status": "pending", "executor": "background_tasks"}


async def _run_audit(
    task_id: str,
    brand_id: str,
    image_paths: list[str],
    batch_size: Optional[int],
    compression: str,
    preconditions: Optional[dict] = None,
) -> list:
    """在线程池中执行同步审核，不阻塞事件循环"""
    from sqlmodel import Session as SyncSession
    from web.deps import engine
    from datetime import datetime as _datetime

    temp_work_dir: Optional[Path] = None

    def _do_audit():
        nonlocal temp_work_dir
        # 设置压缩预设
        preset = audit_service.COMPRESSION_PRESETS.get(compression, audit_service.COMPRESSION_PRESETS["balanced"])
        audit_service.set_compression_config(preset)

        # 更新任务状态为 running
        with SyncSession(engine) as s:
            task = s.get(AuditTask, task_id)
            if task:
                task.status = "running"
                task.updated_at = _datetime.now()
                s.add(task)
                s.commit()
                set_task_status(task_id, "running")

        start_time = _datetime.now()
        try:
            # 对象存储模式下，将文件名/对象拉取为本地临时文件供审核引擎读取
            effective_paths = image_paths
            if object_storage.enabled:
                temp_work_dir = Path(tempfile.mkdtemp(prefix=f"audit-{task_id}-"))
                restored_paths: list[str] = []
                for item in image_paths:
                    p = Path(item)
                    if p.exists():
                        restored_paths.append(str(p))
                        continue

                    filename = p.name
                    object_key = object_storage.build_task_image_key(task_id, filename)
                    content = object_storage.get_bytes(object_key)
                    local_path = temp_work_dir / filename
                    local_path.write_bytes(content)
                    restored_paths.append(str(local_path))
                effective_paths = restored_paths

            reports = audit_service.batch_audit_merged(
                image_paths=effective_paths,
                brand_id=brand_id,
                max_images_per_request=batch_size,
                preconditions=preconditions,
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

            # 至少需要一条带规则检查项的成功结果，否则判定本次审核失败（触发 Celery 重试）
            valid_success_count = 0
            for item in results:
                if item.get("status") != "success":
                    continue
                report = item.get("report") or {}
                if report.get("rule_checks"):
                    valid_success_count += 1
            if valid_success_count == 0:
                raise RuntimeError("审核失败：未生成有效规则检查结果")

            # 计算耗时
            elapsed_seconds = int((_datetime.now() - start_time).total_seconds())

            # 生成 formatted_report 和 machine_result
            formatted_report = _generate_formatted_report(results)
            if not formatted_report.get("rule_checks"):
                raise RuntimeError("审核失败：格式化报告为空")
            machine_result = _determine_machine_result(formatted_report)

            with SyncSession(engine) as s:
                task = s.get(AuditTask, task_id)
                if task:
                    task.status = "completed"
                    task.results = results
                    task.formatted_report = formatted_report
                    task.duration_seconds = elapsed_seconds
                    task.machine_result = machine_result
                    task.updated_at = _datetime.now()
                    s.add(task)
                    s.commit()
                    set_task_status(task_id, "completed")

            return results

        except Exception as e:
            with SyncSession(engine) as s:
                task = s.get(AuditTask, task_id)
                if task:
                    task.status = "failed"
                    task.error = str(e)
                    task.updated_at = _datetime.now()
                    s.add(task)
                    s.commit()
                    set_task_status(task_id, "failed")
            raise

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _do_audit)
    finally:
        if temp_work_dir and temp_work_dir.exists():
            for p in temp_work_dir.iterdir():
                if p.is_file():
                    p.unlink(missing_ok=True)
            temp_work_dir.rmdir()


async def _run_batch_audit(
    task_ids: list[str],
    brand_id: str,
    image_paths: list[str],
    batch_size: Optional[int],
    compression: str,
    preconditions: Optional[dict] = None,
) -> None:
    """批量审核：一次模型调用处理多张同系列图片，结果分发到各个独立任务"""
    from sqlmodel import Session as SyncSession
    from web.deps import engine
    from datetime import datetime as _datetime

    temp_work_dir: Optional[Path] = None

    def _do_batch_audit():
        nonlocal temp_work_dir
        preset = audit_service.COMPRESSION_PRESETS.get(compression, audit_service.COMPRESSION_PRESETS["balanced"])
        audit_service.set_compression_config(preset)

        with SyncSession(engine) as s:
            for tid in task_ids:
                task = s.get(AuditTask, tid)
                if task:
                    task.status = "running"
                    task.updated_at = _datetime.now()
                    s.add(task)
                    set_task_status(tid, "running")
            s.commit()

        start_time = _datetime.now()
        try:
            effective_paths = image_paths
            if object_storage.enabled:
                temp_work_dir = Path(tempfile.mkdtemp(prefix=f"audit-batch-{task_ids[0]}-"))
                restored_paths: list[str] = []
                for idx, item in enumerate(image_paths):
                    p = Path(item)
                    if p.exists():
                        restored_paths.append(str(p))
                        continue
                    filename = p.name
                    object_key = object_storage.build_task_image_key(task_ids[idx], filename)
                    content = object_storage.get_bytes(object_key)
                    local_path = temp_work_dir / filename
                    local_path.write_bytes(content)
                    restored_paths.append(str(local_path))
                effective_paths = restored_paths

            reports = audit_service.batch_audit_merged(
                image_paths=effective_paths,
                brand_id=brand_id,
                max_images_per_request=batch_size,
                preconditions=preconditions,
            )

            def _serialize(r):
                if not isinstance(r, dict):
                    return r.model_dump(mode="json") if hasattr(r, "model_dump") else r
                out = dict(r)
                if "report" in out and hasattr(out["report"], "model_dump"):
                    out["report"] = out["report"].model_dump(mode="json")
                return out

            all_results = [_serialize(r) for r in reports]

            valid_success_count = sum(
                1 for item in all_results
                if item.get("status") == "success" and (item.get("report") or {}).get("rule_checks")
            )
            if valid_success_count == 0:
                raise RuntimeError("审核失败：未生成有效规则检查结果")

            elapsed_seconds = int((_datetime.now() - start_time).total_seconds())

            # 将结果按图片索引分发到各个独立任务
            with SyncSession(engine) as s:
                for idx, tid in enumerate(task_ids):
                    task_result = [all_results[idx]] if idx < len(all_results) else []
                    formatted_report = _generate_formatted_report(task_result)
                    machine_result = _determine_machine_result(formatted_report)

                    task = s.get(AuditTask, tid)
                    if task:
                        task.status = "completed"
                        task.results = task_result
                        task.formatted_report = formatted_report
                        task.duration_seconds = elapsed_seconds
                        task.machine_result = machine_result
                        task.updated_at = _datetime.now()
                        s.add(task)
                        set_task_status(tid, "completed")
                s.commit()

        except Exception as e:
            with SyncSession(engine) as s:
                for tid in task_ids:
                    task = s.get(AuditTask, tid)
                    if task:
                        task.status = "failed"
                        task.error = str(e)
                        task.updated_at = _datetime.now()
                        s.add(task)
                        set_task_status(tid, "failed")
                s.commit()
            raise

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _do_batch_audit)
    finally:
        if temp_work_dir and temp_work_dir.exists():
            for p in temp_work_dir.iterdir():
                if p.is_file():
                    p.unlink(missing_ok=True)
            temp_work_dir.rmdir()


def _generate_formatted_report(results: list) -> dict:
    """生成格式化后的审核报告。
    - per_image: 每张图片独立的审核结果列表
    - rule_checks / violations / passed_rules: 跨图最差原则汇总（兼容旧逻辑）
    """
    if not results:
        return {"per_image": [], "rule_checks": [], "violations": [], "passed_rules": [], "issues": [], "summary": ""}

    STATUS_ORDER = {"fail": 0, "review": 1, "warning": 1, "pass": 2}

    per_image = []
    all_issues = []
    summaries = []
    # 跨图最差合并
    merged: dict[str, dict] = {}

    for result in results:
        report = result.get("report", {})
        file_name = result.get("file_name", "")
        rule_checks = report.get("rule_checks", [])
        issues = report.get("issues", [])
        summary = report.get("summary", "")

        if summary:
            summaries.append(summary)

        img_issues = []
        for issue in issues:
            if isinstance(issue, dict):
                entry = {
                    "title": issue.get("type", ""),
                    "description": issue.get("description", issue.get("detail", "")),
                }
                img_issues.append(entry)
                all_issues.append(entry)

        img_rule_checks = []
        img_violations = []
        img_passed = []
        for rc in rule_checks:
            rule_id = rc.get("rule_id", "")
            status = rc.get("status", "").lower()
            entry = {
                "rule_id": rule_id,
                "rule_content": rc.get("rule_content", ""),
                "status": status,
                "confidence": rc.get("confidence", 0.0),
                "detail": rc.get("detail", ""),
                "reference": rc.get("reference", ""),
            }
            img_rule_checks.append(entry)
            if status == "fail":
                img_violations.append({
                    "id": rule_id,
                    "type": "hard",
                    "rule": rc.get("rule_content", ""),
                    "description": rc.get("detail", ""),
                    "severity": "high" if rc.get("confidence", 0.0) > 0.8 else "medium",
                })
            elif status == "pass":
                img_passed.append(rc.get("rule_content", ""))

            # 跨图最差合并
            if rule_id:
                existing = merged.get(rule_id)
                if existing is None:
                    merged[rule_id] = dict(entry)
                else:
                    if STATUS_ORDER.get(status, 2) < STATUS_ORDER.get(existing["status"], 2):
                        merged[rule_id].update({"status": status, "confidence": entry["confidence"], "detail": entry["detail"]})

        # 单图状态
        img_statuses = [rc.get("status", "").lower() for rc in rule_checks]
        if any(s == "fail" for s in img_statuses):
            img_status = "failed"
        elif any(s in ("review", "warning") for s in img_statuses):
            img_status = "manual_review"
        elif img_statuses and all(s == "pass" for s in img_statuses):
            img_status = "passed"
        else:
            img_status = "manual_review"

        per_image.append({
            "file_name": file_name,
            "status": img_status,
            "rule_checks": img_rule_checks,
            "violations": img_violations,
            "passed_rules": img_passed,
            "issues": img_issues,
            "summary": summary,
        })

    # 跨图汇总
    all_rule_checks = list(merged.values())
    violations = []
    passed_rules = set()
    for rc in all_rule_checks:
        if rc["status"] == "fail":
            violations.append({"id": rc["rule_id"], "type": "hard", "rule": rc["rule_content"],
                                "description": rc["detail"], "severity": "high" if rc["confidence"] > 0.8 else "medium"})
        elif rc["status"] == "pass":
            passed_rules.add(rc["rule_content"])

    return {
        "per_image": per_image,
        "rule_checks": all_rule_checks,
        "violations": violations,
        "passed_rules": list(passed_rules),
        "issues": all_issues,
        "summary": " ".join(summaries),
    }


def _determine_machine_result(formatted_report: dict) -> str:
    """根据规则检查结果确定机审结论：最差结果为fail→failed，review→manual_review，全pass→passed"""
    rule_checks = formatted_report.get("rule_checks", [])
    if not rule_checks:
        return "manual_review"
    statuses = [rc.get("status", "").lower() for rc in rule_checks]
    if any(s == "fail" for s in statuses):
        return "failed"
    if any(s in ("review", "warning") for s in statuses):
        return "manual_review"
    if all(s == "pass" for s in statuses):
        return "passed"
    return "manual_review"


# ── 任务查询 ──────────────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}")
def get_task(task_id: str, identity: Identity = Depends(get_current_identity), session: Session = Depends(get_session)):
    """查询任务状态和结果（客户端轮询）"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    _ensure_task_access(task, identity)

    cached_status = get_task_status(task_id)
    if cached_status in ("pending", "running"):
        task.status = cached_status

    resp = {
        "task_id": task.id,
        "brand_id": task.brand_id,
        "name": task.name,
        "created_by": task.created_by,
        "image_purpose": task.image_purpose,
        "project_type": task.project_type,
        "project_desc": task.project_desc,
        "status": task.status,
        "input_meta": task.input_meta,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "error": task.error,
    }
    if task.status == "completed":
        resp["results"] = task.results
        resp["formatted_report"] = task.formatted_report
        resp["duration_seconds"] = task.duration_seconds
        resp["machine_result"] = task.machine_result

    # 返回复核员信息
    reviewer_ids = task.reviewer_ids or []
    user_ids = set(reviewer_ids)
    if task.created_by:
        user_ids.add(task.created_by)
    user_name_map: dict[str, str] = {}
    if user_ids:
        for u in session.exec(select(User).where(User.id.in_(list(user_ids)))).all():
            user_name_map[u.id] = u.name
    resp["created_by_name"] = user_name_map.get(task.created_by, task.created_by)
    resp["reviewer_ids"] = reviewer_ids
    resp["reviewers"] = [{"user_id": uid, "name": user_name_map.get(uid, uid)} for uid in reviewer_ids]

    return resp


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, identity: Identity = Depends(get_current_identity), session: Session = Depends(get_session)):
    """删除单条审核历史记录"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    _ensure_task_access(task, identity)

    if object_storage.enabled:
        filenames = (task.input_meta or {}).get("filenames") or []
        for filename in filenames:
            object_key = object_storage.build_task_image_key(task_id, str(filename))
            object_storage.delete(object_key)

    session.delete(task)
    session.commit()


@router.get("/tasks/{task_id}/images/{filename}")
def get_task_image(task_id: str, filename: str, identity: Identity = Depends(get_current_identity), session: Session = Depends(get_session)):
    """获取审核任务上传的海报图片（用于前端缩略图展示）"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    _ensure_task_access(task, identity)

    if object_storage.enabled:
        object_key = object_storage.build_task_image_key(task_id, filename)
        if object_storage.stat_exists(object_key):
            content = object_storage.get_bytes(object_key)
            media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return Response(content=content, media_type=media_type)

    # 兼容历史本地存储
    image_path = _legacy_upload_dir() / task_id / filename
    if image_path.exists():
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return Response(content=image_path.read_bytes(), media_type=media_type)

    raise HTTPException(404, detail="图片不存在")




@router.get("/history")
def list_history(
    brand_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(get_session),
):
    """审核历史列表，支持按品牌筛选和分页"""
    query = select(AuditTask).order_by(desc(AuditTask.created_at))
    count_query = select(func.count()).select_from(AuditTask)
    if brand_id:
        query = query.where(AuditTask.brand_id == brand_id)
        count_query = count_query.where(AuditTask.brand_id == brand_id)

    if settings.enable_user_isolation and not _is_admin(identity):
        if not identity.username:
            raise HTTPException(403, detail="缺少用户身份，无法访问历史记录")
        query = query.where(AuditTask.created_by == identity.username)
        count_query = count_query.where(AuditTask.created_by == identity.username)

    total = session.exec(count_query).one() or 0
    tasks = session.exec(query.offset((page - 1) * page_size).limit(page_size)).all()

    # 批量查询复核员名称
    all_reviewer_ids: set[str] = set()
    all_creator_ids: set[str] = set()
    for t in tasks:
        all_reviewer_ids.update(t.reviewer_ids or [])
        if t.created_by:
            all_creator_ids.add(t.created_by)
    user_ids = list(all_reviewer_ids.union(all_creator_ids))
    user_name_map: dict[str, str] = {}
    if user_ids:
        for u in session.exec(select(User).where(User.id.in_(user_ids))).all():
            user_name_map[u.id] = u.name

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "task_id": t.id,
                "name": t.name,
                "brand_id": t.brand_id,
                "created_by": t.created_by,
                "created_by_name": user_name_map.get(t.created_by, t.created_by),
                "machine_result": t.machine_result,
                "created_at": t.created_at,
                "duration": t.duration_seconds,
                "status": t.status,
                "input_meta": t.input_meta,
                "formatted_report": t.formatted_report,
                "results": t.results,
                "review_result": t.review_result,
                "review_comment": t.review_comment,
                "review_at": t.review_at,
                "per_image_reviews": t.per_image_reviews or [],
                "reviewer_ids": t.reviewer_ids or [],
                "reviewers": [{"user_id": uid, "name": user_name_map.get(uid, uid)} for uid in (t.reviewer_ids or [])],
            }
            for t in tasks
        ],
    }


@router.post("/tasks/{task_id}/request-review")
def request_review(task_id: str, identity: Identity = Depends(get_current_identity), session: Session = Depends(get_session)):
    """申请人工复核"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    _ensure_task_access(task, identity)
    if task.status != "completed":
        raise HTTPException(400, detail="只有已完成的任务才能申请人工复核")

    task.status = "pending_review"
    task.updated_at = datetime.now()
    session.add(task)
    session.commit()
    session.refresh(task)

    return {"task_id": task_id, "status": "pending_review", "message": "已提交人工复核"}


@router.get("/tasks/{task_id}/export")
def export_report(
    task_id: str,
    format: str = Query("json", description="导出格式：json/markdown"),
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(get_session),
):
    """导出审核报告（json 或 markdown 格式）"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    _ensure_task_access(task, identity)
    if task.status != "completed":
        raise HTTPException(400, detail="任务尚未完成，无法导出报告")

    if format == "json":
        import json
        content = json.dumps({
            "task_id": task.id,
            "name": task.name,
            "brand_id": task.brand_id,
            "machine_result": task.machine_result,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "duration_seconds": task.duration_seconds,
            "formatted_report": task.formatted_report,
            "results": task.results,
        }, ensure_ascii=False, indent=2)
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=audit-report-{task_id}.json"},
        )

    elif format == "markdown":
        report = task.formatted_report or {}
        violations = report.get("violations", [])
        passed_rules = report.get("passed_rules", [])

        lines = [
            f"# 审核报告 - {task.name or task_id}",
            f"",
            f"- **任务 ID**: {task.id}",
            f"- **机审结果**: {task.machine_result or '-'}",
            f"- **审核时间**: {task.created_at.strftime('%Y-%m-%d %H:%M:%S') if task.created_at else '-'}",
            f"- **耗时**: {task.duration_seconds}s" if task.duration_seconds else "- **耗时**: -",
            f"",
            f"## 违规项（{len(violations)}）",
            f"",
        ]
        for v in violations:
            lines.append(f"- [{v.get('type','').upper()}] **{v.get('rule','')}**")
            if v.get("description"):
                lines.append(f"  - 说明：{v['description']}")
        if not violations:
            lines.append("无违规项")

        lines += [f"", f"## 通过规则（{len(passed_rules)}）", f""]
        for r in passed_rules:
            lines.append(f"- ✓ {r}")
        if not passed_rules:
            lines.append("无")

        content = "\n".join(lines)
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=audit-report-{task_id}.md"},
        )

    else:
        raise HTTPException(400, detail="format 必须是 json 或 markdown")
