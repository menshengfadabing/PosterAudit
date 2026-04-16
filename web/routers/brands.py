"""品牌规则 + 参考图片路由（6个接口）"""

import shutil
import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from src.services.document_parser import document_parser
from src.services.rules_context import rules_context
from src.utils.config import get_app_dir
from web.auth import require_admin
from web.deps import get_session, verify_api_key
from web.models.db import AuditTask, Brand, ReferenceImage

router = APIRouter(dependencies=[Depends(verify_api_key)])

IMAGES_BASE = get_app_dir() / "data" / "rules"


# ── 品牌规则 ──────────────────────────────────────────────────────────────────

@router.post("/brands", status_code=201, dependencies=[Depends(require_admin)])
async def create_brand(
    file: UploadFile = File(..., description="品牌规范文档（PDF/DOCX/XLSX/MD/TXT）"),
    brand_name: str = Form(...),
    session: Session = Depends(get_session),
):
    """上传品牌规范文档，解析并创建品牌规则"""
    content = await file.read()
    brand_rules = await document_parser.async_parse(content, file.filename or "upload")

    brand_id = f"brand_{uuid.uuid4().hex[:8]}"
    brand_rules.brand_id = brand_id
    brand_rules.brand_name = brand_name or brand_rules.brand_name or file.filename

    # 持久化到 JSON 文件（复用现有 rules_context）
    rules_context.add_rules(brand_rules, brand_id=brand_id)

    # 写入数据库
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
        text = await document_parser.async_extract_text_only(content, f.filename or "upload")
        if text:
            all_texts.append(f"=== 文件: {_Path(f.filename or 'upload').name} ===\n{text}")

    if not all_texts:
        raise HTTPException(400, detail="所有文档均未提取到文本内容")

    combined_text = "\n\n".join(all_texts)
    brand_rules = await document_parser.async_extract_rules_with_llm(combined_text, brand_name)
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
    """
    更新品牌信息或重新解析规则。

    - `action=update`：更新品牌名称等元信息
    - `action=reparse`：用已保存的 raw_text 重新调用 LLM 解析规则
    """
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

    from datetime import datetime
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
    from datetime import datetime
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

    # 删除关联审核任务
    audit_tasks = session.exec(
        select(AuditTask).where(AuditTask.brand_id == brand_id)
    ).all()
    for task in audit_tasks:
        session.delete(task)

    # 删除关联参考图片记录（先 flush，确保外键约束顺序正确）
    ref_imgs = session.exec(
        select(ReferenceImage).where(ReferenceImage.brand_id == brand_id)
    ).all()
    for img in ref_imgs:
        session.delete(img)
    session.flush()  # 先执行子表 DELETE，再删父表

    session.delete(brand)
    session.commit()

    # 同时清理文件系统（JSON + 图片目录）
    rules_context.delete_rules(brand_id)


@router.get("/brands/{brand_id}/checklist")
def get_brand_checklist(brand_id: str, session: Session = Depends(get_session)):
    """获取品牌规则检查清单（供前端预览和导出使用）"""
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
    """上传参考图片（Logo 标准件）��有独立生命周期，可被所有审核任务复用"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")

    added = []
    for file in files:
        content = await file.read()
        ref = rules_context.add_reference_image(
            brand_id=brand_id,
            image_data=content,
            filename=file.filename or f"{uuid.uuid4().hex}.png",
            description=description,
            image_type=image_type,
        )
        if ref is None:
            continue

        # 同步写入数据库
        images_dir = IMAGES_BASE / brand_id / "images"
        db_img = ReferenceImage(
            brand_id=brand_id,
            filename=ref.filename,
            image_type=ref.image_type,
            description=ref.description,
            file_path=str(images_dir / ref.filename),
            file_size=ref.file_size,
        )
        session.add(db_img)
        added.append(ref.filename)

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
    if db_img:
        session.delete(db_img)
        session.commit()

    ok = rules_context.delete_reference_image(brand_id, filename)
    if not ok and db_img is None:
        raise HTTPException(404, detail="参考图片不存在")


@router.get("/brands/{brand_id}/images")
def list_reference_images(brand_id: str, session: Session = Depends(get_session)):
    """获取品牌参考图片列表"""
    brand = session.get(Brand, brand_id)
    if not brand:
        raise HTTPException(404, detail="品牌不存在")
    images = session.exec(
        select(ReferenceImage).where(ReferenceImage.brand_id == brand_id)
    ).all()
    return {
        "brand_id": brand_id,
        "items": [
            {
                "filename": img.filename,
                "image_type": img.image_type,
                "description": img.description,
                "file_size": img.file_size,
                "created_at": img.created_at,
            }
            for img in images
        ],
    }


@router.get("/brands/{brand_id}/images/{filename}")
def get_reference_image_file(brand_id: str, filename: str):
    """获取品牌参考图片文件（用于前端展示）"""
    image_path = IMAGES_BASE / brand_id / "images" / filename
    if not image_path.exists():
        raise HTTPException(404, detail="图片不存在")
    return FileResponse(str(image_path))
