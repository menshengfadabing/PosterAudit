"""Web 层数据库模型 - SQLModel"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class Brand(SQLModel, table=True):
    """品牌规则表"""
    __tablename__ = "brands"

    id: str                    = Field(primary_key=True)
    name: str                  = Field(index=True)
    version: Optional[str]     = None
    source: Optional[str]      = None
    status: str                = Field(default="active", index=True)  # active/inactive/archived
    rules_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # BrandRules.model_dump()
    raw_text: Optional[str]    = None
    created_at: datetime       = Field(default_factory=datetime.now)
    updated_at: datetime       = Field(default_factory=datetime.now)


class AuditTask(SQLModel, table=True):
    """审核任务表"""
    __tablename__ = "audit_tasks"

    id: str                         = Field(primary_key=True)   # UUID，由应用层生成
    brand_id: str                   = Field(foreign_key="brands.id", index=True)
    name: Optional[str]             = None  # 素材名称（文件名）
    created_by: Optional[str]       = Field(default=None, index=True)  # 任务创建者（用户名/域账号）
    image_purpose: Optional[str]    = None  # 图片用途
    project_type: Optional[str]     = None  # 项目类型
    project_desc: Optional[str]     = None  # 项目描述
    status: str                     = Field(default="pending")  # pending/running/completed/failed/pending_review
    input_meta: Optional[dict]      = Field(default=None, sa_column=Column(JSON))   # 图片数量、压缩参数等
    results: Optional[list[Any]]    = Field(default=None, sa_column=Column(JSON))   # AuditReport 列表
    formatted_report: Optional[dict] = Field(default=None, sa_column=Column(JSON))  # 格式化后的报告（机器结果摘要）
    duration_seconds: Optional[int] = None  # 耗时（秒）
    machine_result: Optional[str] = Field(default=None, index=True)  # 机审结果：passed/failed/manual_review
    review_result: Optional[str] = None  # 人工复核结果：passed/failed（整体）
    reviewer_id: Optional[str] = None  # 复核人 ID
    reviewer_ids: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))  # 当日复核人 ID 列表（关联排班）
    review_comment: Optional[str] = None  # 复核意见（整体）
    review_at: Optional[datetime] = None  # 复核时间
    per_image_reviews: Optional[list[dict]] = Field(default=None, sa_column=Column(JSON))  # 每张图片的复核结果 [{"image_index": 0, "result": "passed", "comment": "..."}]
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
    mime_type: str     = Field(default="image/png")
    object_key: Optional[str] = Field(default=None, index=True)
    image_base64: Optional[str] = Field(default=None, sa_column=Column(Text))
    file_size: int     = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)


class BrandParseTask(SQLModel, table=True):
    """品牌规范解析异步任务"""
    __tablename__ = "brand_parse_tasks"

    id: str = Field(primary_key=True)
    mode: str = Field(default="single", index=True)  # single/merge
    status: str = Field(default="pending", index=True)  # pending/running/completed/failed
    brand_name: str = Field(default="")
    created_by: Optional[str] = Field(default=None, index=True)
    input_meta: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)



class User(SQLModel, table=True):
    """用户表"""
    __tablename__ = "users"

    id: str             = Field(primary_key=True)  # 用户 ID，如 user_xxx
    name: str           = Field(index=True)  # 姓名
    dept: Optional[str] = None  # 部门
    role: str           = Field(default="user", index=True)  # user/reviewer/admin
    status: str         = Field(default="active", index=True)  # active/inactive
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Schedule(SQLModel, table=True):
    """复核排班表"""
    __tablename__ = "schedules"

    id: str             = Field(primary_key=True)
    date: str           = Field(index=True, description="日期，格式 YYYY-MM-DD")
    reviewer_ids: list[str] = Field(default=None, sa_column=Column(JSON))  # 当日复核人 ID 列表
    created_at: datetime = Field(default_factory=datetime.now)
