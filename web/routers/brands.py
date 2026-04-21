"""品牌规则 + 参考图片路由"""

import asyncio
import base64
import mimetypes
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from src.services.document_parser import document_parser
from src.services.rules_context import rules_context
from src.utils.config import get_app_dir
from src.utils.object_storage import object_storage
from web.auth import Identity, get_current_identity, require_admin
from web.deps import engine, get_session, verify_api_key
from web.models.db import AuditTask, Brand, BrandParseTask, ReferenceImage

router = APIRouter(dependencies=[Depends(verify_api_key)])

TASK_DIR = get_app_dir() / "data" / "brand_parse_tasks"


def _persist_brand(session: Session, brand_name: str, source: str, brand_rules) -> dict:
    brand_id = f"brand_{uuid.uuid4().hex[:8]}"
    brand_rules.brand_id = brand_id
    brand_rules.brand_name = brand_name or brand_rules.brand_name

    rules_context.add_rules(brand_rules, brand_id=brand_id)

    db_brand = Brand(
        id=brand_id,
        name=brand_rules.brand_name,
        version=brand_rules.version,
        source=source,
        rules_json=brand_rules.model_dump(mode="json"),
        raw_text=brand_rules.raw_text,
    )
    session.add(db_brand)
    session.commit()
    session.refresh(db_brand)
    return {"brand_id": brand_id, "brand_name": db_brand.name, "version": db_brand.version}


def _run_brand_parse_task(task_id: str) -> None:
    with Session(engine) as session:
        task = session.get(BrandParseTask, task_id)
        if not task:
            return

        task.status = "running"
        task.updated_at = datetime.now()
        session.add(task)
        session.commit()

        meta = task.input_meta or {}
        mode = task.mode
        brand_name = task.brand_name

        try:
            files = meta.get("files") or []
            if not files:
                raise RuntimeError("任务缺少输入文件")

            if mode == "single":
                f = files[0]
                file_path = Path(f["path"])
                file_name = f.get("name") or file_path.name
                content = file_path.read_bytes()
                brand_rules = document_parser.parse(content, file_name)
                brand_rules.brand_name = brand_name or brand_rules.brand_name or file_name
                result = _persist_brand(session, brand_rules.brand_name, brand_rules.source or file_name, brand_rules)
            else:
                all_texts: list[str] = []
                source_names: list[str] = []
                for f in files:
                    file_path = Path(f["path"])
                    file_name = f.get("name") or file_path.name
                    source_names.append(file_name)
                    text = document_parser.extract_text_only(file_path.read_bytes(), file_name)
                    if text:
                        all_texts.append(f"=== 文件: {file_name} ===\n{text}")

                if not all_texts:
                    raise RuntimeError("所有文档均未提取到文本内容")

                combined_text = "\n\n".join(all_texts)
                brand_rules = document_parser._extract_rules_with_llm(combined_text, brand_name)
                brand_rules.brand_name = brand_name
                brand_rules.raw_text = combined_text
                result = _persist_brand(session, brand_name, ", ".join(source_names), brand_rules)

            task.status = "completed"
            task.result = result
            task.error = None
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

        finally:
            try:
                shutil.rmtree(TASK_DIR / task_id, ignore_errors=True)
            except Exception:
                pass


# ── 品牌规则 ──────────────────────────────────────────────────────────────────

@router.post("/brands", status_code=201, dependencies=[Depends(require_admin)])
async def create_brand(
    file: UploadFile = File(..., description="品牌规范文档（PDF/DOCX/XLSX/MD/TXT）"),
    brand_name: str = Form(...),
    session: Session = Depends(get_session),
):
    """上传品牌规范文档，解析并创建品牌规则"""
    content = await file.read()
    try:
        brand_rules = await asyncio.wait_for(document_parser.async_parse(content, file.filename or "upload"), timeout=120)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, detail="规则解析超时，请精简文档后重试")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"规则解析失败: {e}")

    brand_id = f"brand_{uuid.uuid4().hex[:8]}"
    brand_rules.brand_id = brand_id
    brand_rules.brand_name = brand_name or brand_rules.brand_name or file.filename

    rules_context.add_rules(brand_rules, brand_id=brand_id)

    db_brand = Brand(
        id=brand_id,
        name=brand_rules.brand_name,
        version=brand_rules.version,
        source=brand_rules.source,
        rules_json=brand_rules.model_dump(mode="json"),
        raw_text=brand_rules.raw_text,
    )
    session.add(db_brand)
    session.commit()
    session.refresh(db_brand)

    return {"brand_id": brand_id, "brand_name": db_brand.name, "version": db_brand.version}


@router.post("/brands/async", status_code=202, dependencies=[Depends(require_admin)])
async def create_brand_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="品牌规范文档（PDF/DOCX/XLSX/MD/TXT）"),
    brand_name: str = Form(...),
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(get_session),
):
    """异步创建品牌规范：立即返回 task_id，由前端轮询任务状态。"""
    task_id = str(uuid.uuid4())
    task_path = TASK_DIR / task_id
    task_path.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "upload"
    safe_name = Path(filename).name
    content = await file.read()
    file_path = task_path / safe_name
    file_path.write_bytes(content)

    task = BrandParseTask(
        id=task_id,
        mode="single",
        status="pending",
        brand_name=brand_name,
        created_by=identity.username,
        input_meta={"files": [{"name": safe_name, "path": str(file_path)}]},
    )
    session.add(task)
    session.commit()

    background_tasks.add_task(_run_brand_parse_task, task_id)
    return {"task_id": task_id, "status": "pending"}


@router.post("/brands/merge/async", status_code=202, dependencies=[Depends(require_admin)])
async def merge_brands_async(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="多个规范文档，合并解析为一个品牌规范"),
    brand_name: str = Form(...),
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(get_session),
):
    """异步合并创建品牌规范：立即返回 task_id。"""
    task_id = str(uuid.uuid4())
    task_path = TASK_DIR / task_id
    task_path.mkdir(parents=True, exist_ok=True)

    stored_files = []
    for i, f in enumerate(files):
        filename = f.filename or f"upload_{i+1}.txt"
        safe_name = Path(filename).name
        content = await f.read()
        file_path = task_path / safe_name
        file_path.write_bytes(content)
        stored_files.append({"name": safe_name, "path": str(file_path)})

    task = BrandParseTask(
        id=task_id,
        mode="merge",
        status="pending",
        brand_name=brand_name,
        created_by=identity.username,
        input_meta={"files": stored_files},
    )
    session.add(task)
    session.commit()

    background_tasks.add_task(_run_brand_parse_task, task_id)
    return {"task_id": task_id, "status": "pending"}


@router.get("/brands/tasks/{task_id}", dependencies=[Depends(require_admin)])
def get_brand_parse_task(task_id: str, session: Session = Depends(get_session)):
    task = session.get(BrandParseTask, task_id)
    if not task:
        raise HTTPException(404, detail="任务不存在")
    return {
        "task_id": task.id,
        "status": task.status,
        "brand_name": task.brand_name,
        "created_by": task.created_by,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@router.get("/brands")
def list_brands(session: Session = Depends(get_session)):
    """列出所有品牌"""
    brands = session.exec(select(Brand)).all()
    return [
        {
            "brand_id": b.id,
            "brand_name": b.name,
            "version": b.version,
            "source": b.source,
            "status": b.status,
            "created_at": b.created_at,
            "rules_json": b.rules_json,
        }
        for b in brands
    ]


@router.post("/brands/merge", status_code=201, dependencies=[Depends(require_admin)])
async def merge_brands(
    files: list[UploadFile] = File(..., description="多个规范文档，合并解析为一个品牌规范"),
    brand_name: str = Form(...),
    session: Session = Depends(get_session),
):
    """上传多个规范文档，合并文本后用 LLM 解析为统一品牌规范"""
    from pathlib import Path as _Path

    all_texts: list[str] = []
    for f in files:
        content = await f.read()
        try:
            text = await asyncio.wait_for(document_parser.async_extract_text_only(content, f.filename or "upload"), timeout=90)
        except ValueError as e:
            raise HTTPException(400, detail=str(e))
        except asyncio.TimeoutError:
            raise HTTPException(504, detail=f"文档提取超时({f.filename or 'upload'})")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, detail=f"文档提取失败({f.filename or 'upload'}): {e}")
        if text:
            all_texts.append(f"=== 文件: {_Path(f.filename or 'upload').name} ===\n{text}")

    if not all_texts:
        raise HTTPException(400, detail="所有文档均未提取到文本内容")

    combined_text = "\n\n".join(all_texts)
    try:
        brand_rules = await asyncio.wait_for(document_parser.async_extract_rules_with_llm(combined_text, brand_name), timeout=120)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except asyncio.TimeoutError:
        raise HTTPException(504, detail="规则解析超时，请拆分文档后重试")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"规则解析失败: {e}")
    brand_rules.brand_name = brand_name
    brand_rules.raw_text = combined_text

    brand_id = f"brand_{uuid.uuid4().hex[:8]}"
    brand_rules.brand_id = brand_id
    rules_context.add_rules(brand_rules, brand_id=brand_id)

    db_brand = Brand(
        id=brand_id,
        name=brand_name,
        version=brand_rules.version,
        source=", ".join(f.filename or "" for f in files),
        rules_json=brand_rules.model_dump(mode="json"),
        raw_text=combined_text,
    )
    session.add(db_brand)
    session.commit()
    session.refresh(db_brand)

    return {"brand_id": brand_id, "brand_name": db_brand.name, "version": db_brand.version}


@router.get("/brands/{brand_id}")
def get_brand(brand_id: str, session: Session = Depends(get_session)):
    """获取单个品牌完整规则"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")
    return {
        "brand_id": brand.id,
        "brand_name": brand.name,
        "version": brand.version,
        "source": brand.source,
        "status": brand.status,
        "created_at": brand.created_at,
        "rules_json": brand.rules_json,
        "raw_text": brand.raw_text,
    }


@router.put("/brands/{brand_id}", dependencies=[Depends(require_admin)])
async def update_brand(
    brand_id: str,
    action: str = Form("update", description="update=更新元信息；reparse=重新解析规则"),
    brand_name: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    """更新品牌信息或重新解析规则"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")

    if action == "reparse":
        reparsed = await rules_context.async_reparse_rules_from_raw_text(brand_id)
        if reparsed is None:
            raise HTTPException(400, detail="重新解析失败，请检查 raw_text 是否存在")
        brand.rules_json = reparsed.model_dump(mode="json")
        brand.raw_text = reparsed.raw_text

    if brand_name:
        brand.name = brand_name

    brand.updated_at = datetime.now()
    session.add(brand)
    session.commit()
    session.refresh(brand)

    return {"brand_id": brand.id, "brand_name": brand.name, "action": action, "status": "ok"}


@router.patch("/brands/{brand_id}/status", dependencies=[Depends(require_admin)])
def update_brand_status(
    brand_id: str,
    status: str = Form(..., description="品牌状态：active/inactive/archived"),
    session: Session = Depends(get_session),
):
    """更新品牌状态"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")

    allowed = ("active", "inactive", "archived")
    if status not in allowed:
        raise HTTPException(400, detail=f"status 必须是 {allowed} 之一")

    brand.status = status
    brand.updated_at = datetime.now()
    session.add(brand)
    session.commit()
    session.refresh(brand)

    return {"brand_id": brand.id, "brand_name": brand.name, "status": brand.status}


@router.delete("/brands/{brand_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_brand(brand_id: str, session: Session = Depends(get_session)):
    """删除品牌规则"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")

    audit_tasks = session.exec(select(AuditTask).where(AuditTask.brand_id == brand_id)).all()
    for task in audit_tasks:
        session.delete(task)

    ref_imgs = session.exec(select(ReferenceImage).where(ReferenceImage.brand_id == brand_id)).all()
    for img in ref_imgs:
        if img.object_key:
            object_storage.delete(img.object_key)
        session.delete(img)
    session.flush()

    session.delete(brand)
    session.commit()

    rules_context.delete_rules(brand_id)


@router.get("/brands/{brand_id}/checklist")
def get_brand_checklist(brand_id: str, session: Session = Depends(get_session)):
    """获取品牌规则检查清单（供前端预览和导出）"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")
    checklist = rules_context.get_rules_checklist(brand_id)
    return {
        "brand_id": brand_id,
        "brand_name": brand.name,
        "total": len(checklist),
        "checklist": checklist,
    }


# ── 参考图片 ──────────────────────────────────────────────────────────────────

@router.post("/brands/{brand_id}/images", status_code=201, dependencies=[Depends(require_admin)])
async def upload_reference_images(
    brand_id: str,
    files: list[UploadFile] = File(..., description="参考图片（Logo 标准件等），可批量上传"),
    image_type: str = Form("logo"),
    description: str = Form(""),
    session: Session = Depends(get_session),
):
    """上传参考图片（优先存 MinIO，不再占用 DB 大字段）"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")

    existing = session.exec(select(ReferenceImage).where(ReferenceImage.brand_id == brand_id)).all()
    max_reference_images = 5
    if len(existing) >= max_reference_images:
        raise HTTPException(400, detail=f"参考图片数量已达上限: {max_reference_images}")

    added = []
    for file in files:
        content = await file.read()
        if not content:
            continue
        if len(existing) + len(added) >= max_reference_images:
            break

        filename = file.filename or f"{uuid.uuid4().hex}.png"
        duplicate = session.exec(
            select(ReferenceImage).where(
                ReferenceImage.brand_id == brand_id,
                ReferenceImage.filename == filename,
            )
        ).first()
        if duplicate:
            name, dot, ext = filename.rpartition(".")
            stem = name if dot else filename
            suffix = f".{ext}" if dot else ""
            filename = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"

        mime_type = (file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream").strip()

        object_key = None
        image_base64 = None
        if object_storage.enabled:
            object_key = object_storage.build_reference_image_key(brand_id, filename)
            object_storage.put_bytes(object_key, content, mime_type)
        else:
            # 兼容未启用 MinIO 的本地场景
            image_base64 = base64.b64encode(content).decode("ascii")

        db_img = ReferenceImage(
            brand_id=brand_id,
            filename=filename,
            image_type=image_type,
            description=description,
            mime_type=mime_type,
            object_key=object_key,
            image_base64=image_base64,
            file_size=len(content),
        )
        session.add(db_img)
        added.append(filename)

    session.commit()
    return {"brand_id": brand_id, "added": added}


@router.delete("/brands/{brand_id}/images/{filename}", status_code=204, dependencies=[Depends(require_admin)])
def delete_reference_image(
    brand_id: str,
    filename: str,
    session: Session = Depends(get_session),
):
    """删除参考图片"""
    db_img = session.exec(
        select(ReferenceImage).where(
            ReferenceImage.brand_id == brand_id,
            ReferenceImage.filename == filename,
        )
    ).first()
    if not db_img:
        raise HTTPException(404, detail="参考图片不存在")

    if db_img.object_key:
        object_storage.delete(db_img.object_key)

    session.delete(db_img)
    session.commit()


@router.get("/brands/{brand_id}/images")
def list_reference_images(brand_id: str, session: Session = Depends(get_session)):
    """获取品牌参考图片列表"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")
    images = session.exec(select(ReferenceImage).where(ReferenceImage.brand_id == brand_id)).all()
    return {
        "brand_id": brand_id,
        "items": [
            {
                "filename": img.filename,
                "image_type": img.image_type,
                "description": img.description,
                "mime_type": img.mime_type,
                "file_size": img.file_size,
                "object_key": img.object_key,
                "created_at": img.created_at,
            }
            for img in images
        ],
    }


@router.get("/brands/{brand_id}/images/{filename}")
def get_reference_image_file(brand_id: str, filename: str, session: Session = Depends(get_session)):
    """获取品牌参考图片文件（优先 MinIO）"""
    img = session.exec(
        select(ReferenceImage).where(
            ReferenceImage.brand_id == brand_id,
            ReferenceImage.filename == filename,
        )
    ).first()
    if not img:
        raise HTTPException(404, detail="图片不存在")

    content = None
    if img.object_key and object_storage.enabled:
        try:
            content = object_storage.get_bytes(img.object_key)
        except Exception as e:
            raise HTTPException(500, detail=f"MinIO 读取失败: {e}") from e
    elif img.image_base64:
        try:
            content = base64.b64decode(img.image_base64)
        except Exception as e:
            raise HTTPException(500, detail=f"图片数据损坏: {e}") from e

    if not content:
        raise HTTPException(404, detail="图片不存在")

    ascii_name = "".join(ch if (32 <= ord(ch) < 127 and ch not in {'"', '\\'}) else "_" for ch in img.filename)
    if not ascii_name:
        ascii_name = "image"
    disposition = f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(img.filename)}"

    return Response(
        content=content,
        media_type=img.mime_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )
