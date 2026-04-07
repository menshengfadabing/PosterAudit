"""品牌合规审核平台 - 数据模型"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============== 枚举类型 ==============

class AuditStatus(str, Enum):
    """审核状态"""
    PASS = "pass"
    WARNING = "warning"
    REVIEW = "review"
    FAIL = "fail"


class IssueSeverity(str, Enum):
    """问题严重程度"""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class IssueType(str, Enum):
    """问题类型"""
    COLOR = "color"
    LOGO = "logo"
    FONT = "font"
    COPYWRITING = "copywriting"
    LAYOUT = "layout"
    STYLE = "style"


# ============== 审核相关模型 ==============

class ColorInfo(BaseModel):
    """颜色信息"""
    hex: str = Field(..., description="十六进制颜色值")
    name: str = Field(default="", description="颜色名称")
    percent: float = Field(default=0.0, description="占比百分比")


class LogoInfo(BaseModel):
    """Logo信息"""
    found: bool = Field(default=False, description="是否找到Logo")
    position: str = Field(default="", description="位置描述")
    position_correct: Optional[bool] = Field(default=None, description="位置是否正确")
    size_percent: Optional[float] = Field(default=None, description="尺寸占比")
    size_correct: Optional[bool] = Field(default=None, description="尺寸是否正确")
    color_type: str = Field(default="", description="颜色类型")
    color_correct: Optional[bool] = Field(default=None, description="颜色是否正确")
    safe_margin_ok: Optional[bool] = Field(default=None, description="安全间距是否合规")
    deformed: Optional[bool] = Field(default=None, description="是否变形")


class FontInfo(BaseModel):
    """字体信息"""
    text: str = Field(default="", description="文字内容")
    font_family: str = Field(default="", description="字体名称")
    font_size: str = Field(default="", description="字体大小估算")
    font_weight: str = Field(default="", description="字重")
    font_style: str = Field(default="", description="字体风格")
    is_forbidden: Optional[bool] = Field(default=False, description="是否禁用字体")


class LayoutInfo(BaseModel):
    """布局信息"""
    has_clear_focus: Optional[bool] = Field(default=None, description="是否有清晰焦点")
    text_on_subject: Optional[bool] = Field(default=None, description="文字是否压主体")
    contrast_sufficient: Optional[bool] = Field(default=None, description="对比度是否足够")
    alignment_correct: Optional[bool] = Field(default=None, description="对齐是否正确")


class StyleScore(BaseModel):
    """风格评分"""
    score: int = Field(default=7, description="评分1-10")
    issues: list[str] = Field(default_factory=list, description="问题列表")


class DetectionResult(BaseModel):
    """检测结果"""
    colors: list[ColorInfo] = Field(default_factory=list, description="颜色列表")
    logo: LogoInfo = Field(default_factory=LogoInfo, description="Logo信息")
    texts: list[str] = Field(default_factory=list, description="文字列表")
    fonts: list[FontInfo] = Field(default_factory=list, description="字体列表")
    layout: LayoutInfo = Field(default_factory=LayoutInfo, description="布局信息")
    style: dict[str, StyleScore] = Field(default_factory=dict, description="风格评分")


class RuleCheckItem(BaseModel):
    """规则检查项 - 用于规则检查清单"""
    rule_id: str = Field(..., description="规则ID: Rule_1, Rule_2...")
    rule_content: str = Field(..., description="规则内容")
    status: str = Field(default="pass", description="状态: pass/fail/review")
    reference: str = Field(default="", description="参考文档来源")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度 0-1")
    detail: str = Field(default="", description="详细说明")


class Issue(BaseModel):
    """问题项"""
    type: IssueType = Field(..., description="问题类型")
    severity: IssueSeverity = Field(..., description="严重程度")
    code: str = Field(default="", description="规则编号")
    description: str = Field(..., description="问题描述")
    suggestion: str = Field(default="", description="修改建议")
    action: str = Field(default="", description="建议动作")


class AuditReport(BaseModel):
    """审核报告"""
    score: int = Field(default=0, ge=0, le=100, description="合规分数（已废弃，不再使用）")
    status: AuditStatus = Field(..., description="审核状态")
    detection: DetectionResult = Field(default_factory=DetectionResult, description="检测结果")
    rule_checks: list[RuleCheckItem] = Field(default_factory=list, description="规则检查清单")
    issues: list[Issue] = Field(default_factory=list, description="问题列表")
    summary: str = Field(default="", description="总体评价")

    def to_json(self) -> str:
        """导出为JSON"""
        import json
        return json.dumps(self.model_dump(), ensure_ascii=False, indent=2, default=str)


# ============== 规范文档相关模型 ==============

class ColorRule(BaseModel):
    """色彩规范"""
    name: str = Field(default="", description="颜色名称")
    value: str = Field(default="", description="颜色值")
    tolerance: Optional[int] = Field(default=None, description="容差")
    reason: Optional[str] = Field(default=None, description="原因（禁用色）")


class ColorRules(BaseModel):
    """色彩规范集合"""
    primary: Optional[ColorRule] = Field(default=None, description="主色")
    secondary: list[ColorRule] = Field(default_factory=list, description="辅助色")
    forbidden: list[ColorRule] = Field(default_factory=list, description="禁用色")
    additional_rules: list[str] = Field(default_factory=list, description="其他色彩相关规则")
    description: Optional[str] = Field(default=None, description="整体描述")


class LogoRules(BaseModel):
    """Logo规范"""
    position: str = Field(default="", description="位置标识")
    position_description: str = Field(default="", description="位置描述")
    size_range: dict[str, int] = Field(default_factory=lambda: {"min": 5, "max": 10}, description="尺寸范围")
    safe_margin_px: int = Field(default=20, description="安全间距")
    additional_rules: list[str] = Field(default_factory=list, description="其他Logo相关规则")
    min_display_ratio: Optional[str] = Field(default=None, description="最小显示比例")
    color_requirements: list[str] = Field(default_factory=list, description="颜色要求")
    background_requirements: list[str] = Field(default_factory=list, description="背景要求")


class FontRules(BaseModel):
    """字体规范"""
    allowed: list[str] = Field(default_factory=list, description="允许字体")
    forbidden: list[str] = Field(default_factory=list, description="禁用字体")
    size_rules: dict[str, str] = Field(default_factory=dict, description="字号规则")
    weight_rules: list[str] = Field(default_factory=list, description="允许的字重")
    style_rules: list[str] = Field(default_factory=list, description="允许的字体风格")
    note: Optional[str] = Field(default=None, description="备注")
    additional_rules: list[str] = Field(default_factory=list, description="其他字体相关规则")


class ForbiddenWord(BaseModel):
    """禁用词"""
    word: str = Field(..., description="词语")
    category: str = Field(default="", description="分类")


class CopywritingRules(BaseModel):
    """文案规范"""
    forbidden_words: list[ForbiddenWord] = Field(default_factory=list, description="禁用词列表")
    required_content: list[str] = Field(default_factory=list, description="必须内容")


class LayoutRules(BaseModel):
    """布局规范"""
    margin_min: int = Field(default=20, description="最小边距")
    description: str = Field(default="", description="描述")


class SecondaryRule(BaseModel):
    """次要规范项"""
    category: str = Field(default="", description="分类：排版、文案、风格、高风险标签等")
    name: str = Field(default="", description="规则名称")
    content: str = Field(default="", description="规则内容")
    priority: int = Field(default=1, description="优先级: 1=重要, 2=一般, 3=参考")
    # 结构化规则表字段（从Excel等结构化文档提取）
    output_level: Optional[str] = Field(default=None, description="输出级别: FAIL/WARN/REVIEW等，None=未指定")
    threshold: Optional[str] = Field(default=None, description="判定阈值/检测条件，如'长宽比偏差>2%'")
    feedback_text: Optional[str] = Field(default=None, description="失败反馈文案")
    rule_source_id: Optional[str] = Field(default=None, description="原始规则ID，如LOGO-01、COLOR-01、RISK-01")


class ReferenceImage(BaseModel):
    """标准参考图片（Logo等）"""
    filename: str = Field(..., description="文件名")
    description: str = Field(default="", description="图片描述（如：标准Logo、Logo变体等）")
    image_type: str = Field(default="logo", description="图片类型：logo/logo_variant/icon等")
    file_size: int = Field(default=0, description="文件大小(字节)")
    upload_time: Optional[datetime] = Field(default=None, description="上传时间")


class BrandRules(BaseModel):
    """品牌规范"""
    brand_id: str = Field(default="", description="品牌ID")
    brand_name: str = Field(default="", description="品牌名称")
    version: str = Field(default="1.0", description="版本")
    source: Optional[str] = Field(default=None, description="来源文件")
    upload_time: Optional[datetime] = Field(default=None, description="上传时间")

    # 主要规范（固定结构）
    color: Optional[ColorRules] = Field(default=None, description="色彩规范")
    logo: Optional[LogoRules] = Field(default=None, description="Logo规范")
    font: Optional[FontRules] = Field(default=None, description="字体规范")

    # 次要规范（动态列表）
    secondary_rules: list[SecondaryRule] = Field(default_factory=list, description="次要规范列表")

    # 标准参考图片（Logo等）
    reference_images: list[ReferenceImage] = Field(default_factory=list, description="标准参考图片列表")

    # 兼容旧字段
    copywriting: Optional[CopywritingRules] = Field(default=None, description="文案规范")
    layout: Optional[LayoutRules] = Field(default=None, description="布局规范")

    # 原始文本（备份）
    raw_text: Optional[str] = Field(default=None, description="原始文本")

    def to_json(self) -> str:
        """导出为JSON"""
        import json
        return json.dumps(self.model_dump(), ensure_ascii=False, indent=2, default=str)