"""FastAPI 应用入口"""

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
