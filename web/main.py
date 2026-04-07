"""FastAPI 应用入口"""

import os
from pathlib import Path

# 优先加载 .env 文件中的索引 Key（OPENAI_API_KEY_0/1/2...）
# 系统环境变量中的 OPENAI_API_KEY 可能是旧值，不覆盖已有的索引 key
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        # 只注入 .env 中有值且系统环境变量中不存在的 key
        # 对于索引 key（OPENAI_API_KEY_0 等）强制覆盖
        if k.startswith("OPENAI_API_KEY_") or k not in os.environ:
            os.environ[k] = v

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from web.deps import engine
from web.routers import audit, brands

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


@app.on_event("startup")
def on_startup():
    """启动时自动建表"""
    SQLModel.metadata.create_all(engine)


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok"}
