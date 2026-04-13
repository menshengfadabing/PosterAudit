"""审核提交 + 任务查询 + 历史记录路由（3个接口）"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
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
    preconditions: Optional[str] = Form(None, description="前置条件 JSON 字符串"),
    image_purpose: Optional[str] = Form(None, description="图片用途"),
    project_type: Optional[str] = Form(None, description="项目类型"),
    project_desc: Optional[str] = Form(None, description="项目描述"),
    session: Session = Depends(get_session),
):
    """
    提交审核任务，待审核图片随请求内联上传。

    - `mode=async`：立即返回 task_id，客户端通过 GET /tasks/{task_id} 轮询结果
    - `mode=sync`：等待审核完成后直接返回结果（适合单张小图快速测试）
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
        "preconditions": preconditions_dict,
    }

    # 取第一个文件名作为素材名称
    material_name = images[0].filename if images else None

    # 写入任务记录
    task = AuditTask(
        id=task_id,
        brand_id=brand_id,
        name=material_name,
        image_purpose=image_purpose,
        project_type=project_type,
        project_desc=project_desc,
        status="pending",
        input_meta=input_meta,
    )
    session.add(task)
    session.commit()

    if mode == "sync":
        # 同步模式：直接在当前线程中运行，等待完成
        results = await _run_audit(task_id, brand_id, image_paths, batch_size, compression, preconditions_dict)
        # 刷新获取最新结果
        session.refresh(task)
        return {"task_id": task_id, "status": task.status, "results": task.results}

    # 异步模式：在后台任务中运行
    background_tasks.add_task(_run_audit, task_id, brand_id, image_paths, batch_size, compression, preconditions_dict)
    return {"task_id": task_id, "status": "pending", "created_at": task.created_at}


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

    def _do_audit():
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

        start_time = _datetime.now()
        try:
            reports = audit_service.batch_audit_merged(
                image_paths=image_paths,
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

            # 计算耗时
            elapsed_seconds = int((_datetime.now() - start_time).total_seconds())

            # 生成 formatted_report 和 machine_result
            formatted_report = _generate_formatted_report(results)
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
            raise

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_audit)


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
def get_task(task_id: str, session: Session = Depends(get_session)):
    """查询任务状态和结果（客户端轮询）"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")

    resp = {
        "task_id": task.id,
        "brand_id": task.brand_id,
        "name": task.name,
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
    return resp


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, session: Session = Depends(get_session)):
    """删除单条审核历史记录"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    session.delete(task)
    session.commit()


@router.get("/tasks/{task_id}/images/{filename}")
def get_task_image(task_id: str, filename: str):
    """获取审核任务上传的海报图片（用于前端缩略图展示）"""
    image_path = UPLOAD_DIR / task_id / filename
    if not image_path.exists():
        raise HTTPException(404, detail="图片不存在")
    return FileResponse(str(image_path))




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
                "name": t.name,
                "brand_id": t.brand_id,
                "machine_result": t.machine_result,
                "created_at": t.created_at,
                "duration": t.duration_seconds,
                "status": t.status,
                "input_meta": t.input_meta,
                "formatted_report": t.formatted_report,
                "results": t.results,
            }
            for t in tasks
        ],
    }


@router.post("/tasks/{task_id}/request-review")
def request_review(task_id: str, session: Session = Depends(get_session)):
    """申请人工复核"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
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
    session: Session = Depends(get_session),
):
    """导出审核报告（json 或 markdown 格式）"""
    task = session.get(AuditTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
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
