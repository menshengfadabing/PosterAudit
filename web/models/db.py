"""Web 层数据库模型 - SQLModel"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Brand(SQLModel, table=True):
    """品牌规则表"""
    __tablename__ = "brands"

    id: str                    = Field(primary_key=True)
    name: str                  = Field(index=True)
    version: Optional[str]     = None
    source: Optional[str]      = None
    rules_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # BrandRules.model_dump()
    raw_text: Optional[str]    = None
    created_at: datetime       = Field(default_factory=datetime.now)
    updated_at: datetime       = Field(default_factory=datetime.now)


class AuditTask(SQLModel, table=True):
    """审核任务表"""
    __tablename__ = "audit_tasks"

    id: str                         = Field(primary_key=True)   # UUID，由应用层生成
    brand_id: str                   = Field(foreign_key="brands.id", index=True)
    status: str                     = Field(default="pending")  # pending/running/completed/failed
    input_meta: Optional[dict]      = Field(default=None, sa_column=Column(JSON))   # 图片数量、压缩参数等
    results: Optional[list[Any]]    = Field(default=None, sa_column=Column(JSON))   # AuditReport 列表
    error: Optional[str]            = None
    created_at: datetime            = Field(default_factory=datetime.now)
    updated_at: datetime            = Field(default_factory=datetime.now)


class ReferenceImage(SQLModel, table=True):
    """参考图片表（Logo 标准件等）"""
    __tablename__ = "reference_images"

    id: Optional[int]  = Field(default=None, primary_key=True)
    brand_id: str      = Field(foreign_key="brands.id", index=True)
    filename: str
    image_type: str    = Field(default="logo")
    description: str   = Field(default="")
    file_path: str
    file_size: int     = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
