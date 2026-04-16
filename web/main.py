"""FastAPI 应用入口"""

import base64
import mimetypes
import os
from pathlib import Path

# 优先加载 .env 文件中的索引 Key（MLLM_API_KEY_0/1/2...）
# 系统环境变量中的单 Key 可能是旧值，不覆盖已有的索引 key
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        # 只注入 .env 中有值且系统环境变量中不存在的 key
        # 对于索引 key（MLLM_API_KEY_0 等）强制覆盖
        if k.startswith("MLLM_API_KEY_") or k not in os.environ:
            os.environ[k] = v

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlmodel import SQLModel

from web.deps import engine
from web.routers import audit, brands, review, stats

app = FastAPI(
    title="品牌合规审核 API",
    description="品牌视觉合规智能审核平台 REST API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(brands.router, prefix="/api/v1", tags=["品牌规则"])
app.include_router(audit.router,  prefix="/api/v1", tags=["审核"])
app.include_router(review.router, prefix="/api/v1", tags=["人工复核"])
app.include_router(stats.router,  prefix="/api/v1", tags=["统计"])


def _migrate_reference_images_table() -> None:
    """轻量迁移：将参考图切换为 DB base64 存储，并兼容旧 file_path 数据。"""
    with engine.begin() as conn:
        inspector = inspect(conn)
        if not inspector.has_table("reference_images"):
            return

        columns = {c["name"] for c in inspector.get_columns("reference_images")}
        if "mime_type" not in columns:
            conn.execute(text("ALTER TABLE reference_images ADD COLUMN mime_type VARCHAR(255) DEFAULT 'image/png'"))
        if "image_base64" not in columns:
            conn.execute(text("ALTER TABLE reference_images ADD COLUMN image_base64 TEXT"))

        # 兼容旧数据：从 file_path 回填 image_base64
        columns = {c["name"] for c in inspect(conn).get_columns("reference_images")}
        if "file_path" in columns:
            rows = conn.execute(
                text(
                    "SELECT id, file_path, mime_type FROM reference_images "
                    "WHERE (image_base64 IS NULL OR image_base64 = '') "
                    "AND file_path IS NOT NULL AND file_path <> ''"
                )
            ).fetchall()
            for row in rows:
                file_path = Path(row.file_path)
                if not file_path.exists():
                    continue
                image_bytes = file_path.read_bytes()
                guessed_mime = (mimetypes.guess_type(file_path.name)[0] or "image/png").strip()
                conn.execute(
                    text(
                        "UPDATE reference_images "
                        "SET image_base64 = :image_base64, file_size = :file_size, mime_type = COALESCE(NULLIF(mime_type, ''), :mime_type) "
                        "WHERE id = :id"
                    ),
                    {
                        "id": row.id,
                        "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                        "file_size": len(image_bytes),
                        "mime_type": guessed_mime,
                    },
                )
            conn.execute(text("ALTER TABLE reference_images DROP COLUMN IF EXISTS file_path"))


@app.on_event("startup")
def on_startup():
    """启动时自动建表"""
    SQLModel.metadata.create_all(engine)
    _migrate_reference_images_table()


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok"}
