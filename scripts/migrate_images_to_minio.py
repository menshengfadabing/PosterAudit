#!/usr/bin/env python3
"""迁移审核图片/参考图片到 MinIO。"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

# 允许直接从 scripts/ 启动脚本时导入项目包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlmodel import Session, select

from src.utils.config import get_app_dir, settings
from src.utils.object_storage import object_storage
from web.deps import engine
from web.models.db import AuditTask, ReferenceImage


def legacy_upload_dir() -> Path:
    custom_dir = (settings.upload_dir or "").strip()
    if custom_dir:
        return Path(custom_dir)
    return get_app_dir() / "data" / "uploads"


def migrate_reference_images(clear_base64: bool) -> None:
    uploaded = 0
    skipped = 0
    missing = 0

    with Session(engine) as session:
        items = session.exec(select(ReferenceImage)).all()
        for img in items:
            if img.object_key and object_storage.stat_exists(img.object_key):
                skipped += 1
                if clear_base64 and img.image_base64:
                    img.image_base64 = None
                    session.add(img)
                continue

            raw: bytes | None = None
            if img.image_base64:
                raw = base64.b64decode(img.image_base64)

            if not raw:
                missing += 1
                continue

            key = img.object_key or object_storage.build_reference_image_key(img.brand_id, img.filename)
            content_type = (img.mime_type or "application/octet-stream").strip() or "application/octet-stream"
            object_storage.put_bytes(key, raw, content_type)
            img.object_key = key
            if clear_base64:
                img.image_base64 = None
            session.add(img)
            uploaded += 1

        session.commit()

    print(f"[reference] uploaded={uploaded}, skipped={skipped}, missing={missing}, clear_base64={clear_base64}")


def migrate_task_images(prune_local: bool) -> None:
    uploaded = 0
    skipped = 0
    missing = 0
    removed = 0

    upload_root = legacy_upload_dir()

    with Session(engine) as session:
        tasks = session.exec(select(AuditTask)).all()

    for task in tasks:
        input_meta = task.input_meta or {}
        filenames = input_meta.get("filenames") or []
        if not filenames:
            continue

        task_dir = upload_root / task.id
        for name in filenames:
            filename = str(name)
            object_key = object_storage.build_task_image_key(task.id, filename)

            if object_storage.stat_exists(object_key):
                skipped += 1
                if prune_local:
                    local_path = task_dir / filename
                    if local_path.exists() and local_path.is_file():
                        local_path.unlink(missing_ok=True)
                        removed += 1
                continue

            local_path = task_dir / filename
            if not local_path.exists() or not local_path.is_file():
                missing += 1
                continue

            content = local_path.read_bytes()
            content_type = "application/octet-stream"
            object_storage.put_bytes(object_key, content, content_type)
            uploaded += 1

            if prune_local:
                local_path.unlink(missing_ok=True)
                removed += 1

        if prune_local and task_dir.exists() and task_dir.is_dir():
            try:
                next(task_dir.iterdir())
            except StopIteration:
                task_dir.rmdir()

    print(f"[task] uploaded={uploaded}, skipped={skipped}, missing={missing}, removed_local={removed}, prune_local={prune_local}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate images to MinIO")
    parser.add_argument("--reference", action="store_true", help="迁移 reference_images")
    parser.add_argument("--tasks", action="store_true", help="迁移审核任务上传图片")
    parser.add_argument("--all", action="store_true", help="迁移全部")
    parser.add_argument("--clear-base64", action="store_true", help="reference 图片迁移后清空 image_base64")
    parser.add_argument("--prune-local", action="store_true", help="task 图片迁移后删除本地文件")
    args = parser.parse_args()

    if not object_storage.enabled:
        raise SystemExit("MinIO 未启用，请先设置 ENABLE_MINIO_STORAGE=true 并配置 MINIO_* 环境变量")

    do_ref = args.all or args.reference
    do_tasks = args.all or args.tasks
    if not do_ref and not do_tasks:
        raise SystemExit("请至少指定 --reference / --tasks / --all")

    if do_ref:
        migrate_reference_images(clear_base64=args.clear_base64)
    if do_tasks:
        migrate_task_images(prune_local=args.prune_local)


if __name__ == "__main__":
    main()
