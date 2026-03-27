"""品牌合规审核平台 - 规范上下文管理器"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.models.schemas import (
    BrandRules,
    ColorRule,
    ColorRules,
    CopywritingRules,
    ForbiddenWord,
    FontRules,
    LayoutRules,
    LogoRules,
    SecondaryRule,
)
from src.utils.config import settings, get_app_dir

logger = logging.getLogger(__name__)


class RulesContextManager:
    """规范上下文管理器"""

    def __init__(self, data_dir: str = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = get_app_dir() / "data"

        self.rules_dir = self.data_dir / "rules"
        self._cache: dict[str, BrandRules] = {}
        self._current_brand_id: str = ""

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保目录存在"""
        self.rules_dir.mkdir(parents=True, exist_ok=True)

    def _parse_rules_data(self, data: dict, source: str) -> BrandRules:
        """解析规范数据"""
        rules = BrandRules(
            brand_id=data.get("brand_id", "default"),
            brand_name=data.get("brand_name", "默认品牌"),
            version=data.get("version", "1.0"),
            source=source,
        )

        rules_dict = data.get("rules", {})

        # 色彩规范
        if "color" in rules_dict:
            color_data = rules_dict["color"]
            rules.color = ColorRules()
            if "primary" in color_data:
                rules.color.primary = ColorRule(**color_data["primary"])
            if "secondary" in color_data:
                rules.color.secondary = [ColorRule(**c) for c in color_data["secondary"]]
            if "forbidden" in color_data:
                rules.color.forbidden = [ColorRule(**c) for c in color_data["forbidden"]]

        # Logo规范
        if "logo" in rules_dict:
            rules.logo = LogoRules(**rules_dict["logo"])

        # 字体规范
        if "font" in rules_dict:
            rules.font = FontRules(**rules_dict["font"])

        # 文案规范
        if "copywriting" in rules_dict:
            cw_data = rules_dict["copywriting"]
            rules.copywriting = CopywritingRules()
            if "forbidden_words" in cw_data:
                rules.copywriting.forbidden_words = [
                    ForbiddenWord(**w) for w in cw_data["forbidden_words"]
                ]
            if "required_content" in cw_data:
                rules.copywriting.required_content = cw_data["required_content"]

        # 布局规范
        if "layout" in rules_dict:
            rules.layout = LayoutRules(**rules_dict["layout"])

        return rules

    def add_rules(self, rules: BrandRules, brand_id: Optional[str] = None) -> str:
        """添加品牌规范"""
        if brand_id is None:
            brand_id = f"brand_{uuid.uuid4().hex[:8]}"

        rules.brand_id = brand_id
        rules.upload_time = datetime.now()

        self._cache[brand_id] = rules
        self._save_rules(brand_id, rules)

        logger.info(f"添加品牌规范: {brand_id} - {rules.brand_name}")
        return brand_id

    def _save_rules(self, brand_id: str, rules: BrandRules) -> None:
        """持久化保存规范"""
        brand_dir = self.rules_dir / brand_id
        brand_dir.mkdir(parents=True, exist_ok=True)

        rules_file = brand_dir / "current.json"
        with open(rules_file, "w", encoding="utf-8") as f:
            json.dump(rules.model_dump(), f, ensure_ascii=False, indent=2, default=str)

    def get_rules(self, brand_id: Optional[str] = None) -> Optional[BrandRules]:
        """获取品牌规范"""
        if brand_id is None:
            brand_id = self._current_brand_id

        if brand_id in self._cache:
            return self._cache[brand_id]

        rules_file = self.rules_dir / brand_id / "current.json"
        if rules_file.exists():
            try:
                with open(rules_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rules = BrandRules(**data)
                self._cache[brand_id] = rules
                return rules
            except Exception as e:
                logger.error(f"加载规范失败: {brand_id}, {e}")

        return None

    def set_current_brand(self, brand_id: str) -> bool:
        """设置当前品牌"""
        if brand_id in self._cache or (self.rules_dir / brand_id).exists():
            self._current_brand_id = brand_id
            logger.info(f"当前品牌已切换: {brand_id}")
            return True
        return False

    def get_rules_text(self, brand_id: Optional[str] = None) -> str:
        """获取规范的文本描述（精简格式，节省token）"""
        rules = self.get_rules(brand_id)
        if rules is None:
            return "未找到品牌规范，请先上传规范文档。"

        lines = []
        lines.append(f"品牌：{rules.brand_name}")

        # 色彩规范 - 只保留具体数据
        if rules.color:
            color_parts = []
            if rules.color.primary:
                color_parts.append(f"主色:{rules.color.primary.value}({rules.color.primary.name})")
            if rules.color.secondary:
                secondary = ",".join(f"{c.value}({c.name})" for c in rules.color.secondary)
                color_parts.append(f"辅助色:{secondary}")
            if rules.color.forbidden:
                forbidden = ",".join(f"{c.value}" for c in rules.color.forbidden)
                color_parts.append(f"禁用色:{forbidden}")
            if color_parts:
                lines.append("色彩：" + " | ".join(color_parts))

        # Logo规范 - 只保留具体参数
        if rules.logo:
            logo_parts = []
            if rules.logo.position_description:
                logo_parts.append(f"位置:{rules.logo.position_description}")
            if rules.logo.size_range:
                min_size = rules.logo.size_range.get("min", 5)
                max_size = rules.logo.size_range.get("max", 15)
                logo_parts.append(f"尺寸:{min_size}%-{max_size}%")
            if rules.logo.safe_margin_px:
                logo_parts.append(f"安全边距:{rules.logo.safe_margin_px}px")
            if logo_parts:
                lines.append("Logo：" + " | ".join(logo_parts))

        # 字体规范 - 只保留字体列表
        if rules.font:
            font_parts = []
            if rules.font.allowed:
                font_parts.append(f"推荐:{','.join(rules.font.allowed)}")
            if rules.font.forbidden:
                font_parts.append(f"禁用:{','.join(rules.font.forbidden)}")
            if font_parts:
                lines.append("字体：" + " | ".join(font_parts))

        # 文案规范 - 只保留禁用词
        if rules.copywriting and rules.copywriting.forbidden_words:
            words = ",".join(w.word for w in rules.copywriting.forbidden_words)
            lines.append(f"禁用词：{words}")

        # 布局规范
        if rules.layout:
            layout_parts = []
            if rules.layout.margin_min:
                layout_parts.append(f"最小边距:{rules.layout.margin_min}px")
            if rules.layout.description:
                layout_parts.append(rules.layout.description)
            if layout_parts:
                lines.append("布局：" + " | ".join(layout_parts))

        # 次要规范 - 按分类追加
        if rules.secondary_rules:
            # 按分类分组
            categories = {}
            for rule in rules.secondary_rules:
                if rule.category not in categories:
                    categories[rule.category] = []
                categories[rule.category].append(rule)

            for category, rules_list in categories.items():
                # 每个分类最多取前3条重要规则，节省token
                top_rules = sorted(rules_list, key=lambda x: x.priority)[:3]
                contents = "; ".join(f"{r.name}:{r.content}" for r in top_rules)
                lines.append(f"{category}：{contents}")

        return "\n".join(lines)

    def get_rules_checklist(self, brand_id: Optional[str] = None) -> list[dict]:
        """
        获取规则检查清单（用于 LLM Prompt）

        Returns:
            规则列表，每条规则包含:
            - rule_id: Rule_1, Rule_2...
            - content: 规则内容
            - category: 分类名
            - reference: 参考文档来源
        """
        rules = self.get_rules(brand_id)
        if rules is None:
            return []

        checklist = []
        rule_num = 1
        source_prefix = rules.source or rules.brand_name or "品牌规范"

        def add_rule(content: str, category: str):
            nonlocal rule_num
            if content and content.strip():
                checklist.append({
                    "rule_id": f"Rule_{rule_num}",
                    "content": content.strip(),
                    "category": category,
                    "reference": f"参考文档-{source_prefix}"
                })
                rule_num += 1

        # 1. Logo 规范
        if rules.logo:
            logo_category = "Logo规范"
            # additional_rules
            for rule in rules.logo.additional_rules:
                add_rule(rule, logo_category)
            # color_requirements
            for rule in rules.logo.color_requirements:
                add_rule(rule, f"{logo_category}-颜色要求")
            # background_requirements
            for rule in rules.logo.background_requirements:
                add_rule(rule, f"{logo_category}-背景要求")
            # 基本规则
            if rules.logo.position_description:
                add_rule(f"Logo位置应位于{rules.logo.position_description}", logo_category)
            if rules.logo.size_range:
                min_size = rules.logo.size_range.get("min", 5)
                max_size = rules.logo.size_range.get("max", 15)
                add_rule(f"Logo尺寸应占图片宽度的{min_size}%-{max_size}%", logo_category)
            if rules.logo.safe_margin_px:
                add_rule(f"Logo四周应保留至少{rules.logo.safe_margin_px}px安全边距", logo_category)
            if rules.logo.min_display_ratio:
                add_rule(rules.logo.min_display_ratio, logo_category)

        # 2. 色彩规范
        if rules.color:
            color_category = "色彩规范"
            # additional_rules
            for rule in rules.color.additional_rules:
                add_rule(rule, color_category)
            # 主色
            if rules.color.primary:
                add_rule(f"主色应为{rules.color.primary.value}({rules.color.primary.name})", color_category)
            # 辅助色
            if rules.color.secondary:
                for c in rules.color.secondary:
                    add_rule(f"辅助色可使用{c.value}({c.name})", color_category)
            # 禁用色
            if rules.color.forbidden:
                for c in rules.color.forbidden:
                    reason = f"，原因：{c.reason}" if c.reason else ""
                    add_rule(f"禁止使用颜色{c.value}{reason}", color_category)
            # 整体描述
            if rules.color.description:
                add_rule(rules.color.description, color_category)

        # 3. 字体规范
        if rules.font:
            font_category = "字体规范"
            # additional_rules
            for rule in rules.font.additional_rules:
                add_rule(rule, font_category)
            # 允许字体
            if rules.font.allowed:
                add_rule(f"推荐使用字体：{','.join(rules.font.allowed)}", font_category)
            # 禁用字体
            if rules.font.forbidden:
                add_rule(f"禁止使用字体：{','.join(rules.font.forbidden)}", font_category)
            # 备注
            if rules.font.note:
                add_rule(rules.font.note, font_category)

        # 4. 文案规范
        if rules.copywriting:
            cw_category = "文案规范"
            if rules.copywriting.forbidden_words:
                words = "、".join(w.word for w in rules.copywriting.forbidden_words)
                add_rule(f"禁止使用词语：{words}", cw_category)
            if rules.copywriting.required_content:
                for content in rules.copywriting.required_content:
                    add_rule(f"文案必须包含：{content}", cw_category)

        # 5. 布局规范
        if rules.layout:
            layout_category = "布局规范"
            if rules.layout.margin_min:
                add_rule(f"最小边距应为{rules.layout.margin_min}px", layout_category)
            if rules.layout.description:
                add_rule(rules.layout.description, layout_category)

        # 6. 次要规范（排版、风格、高风险标签等）
        for sr in rules.secondary_rules:
            add_rule(sr.content, sr.category)

        return checklist

    def list_rules(self) -> list[dict[str, Any]]:
        """列出所有品牌规范"""
        result = []

        for brand_id, rules in self._cache.items():
            result.append({
                "brand_id": brand_id,
                "brand_name": rules.brand_name,
                "version": rules.version,
                "source": rules.source,
                "upload_time": rules.upload_time.isoformat() if rules.upload_time else None,
            })

        if self.rules_dir.exists():
            for brand_dir in self.rules_dir.iterdir():
                if brand_dir.is_dir() and brand_dir.name not in self._cache:
                    rules_file = brand_dir / "current.json"
                    if rules_file.exists():
                        try:
                            with open(rules_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            result.append({
                                "brand_id": data.get("brand_id", brand_dir.name),
                                "brand_name": data.get("brand_name", ""),
                                "version": data.get("version", ""),
                                "source": data.get("source"),
                                "upload_time": data.get("upload_time"),
                            })
                        except Exception as e:
                            logger.warning(f"读取规范失败: {brand_dir.name}, {e}")

        return result

    def delete_rules(self, brand_id: str) -> bool:
        """删除品牌规范"""
        if brand_id in self._cache:
            del self._cache[brand_id]

        brand_dir = self.rules_dir / brand_id
        if brand_dir.exists():
            import shutil
            shutil.rmtree(brand_dir)
            logger.info(f"删除品牌规范: {brand_id}")
            return True

        return False

    def get_current_brand_id(self) -> str:
        """获取当前品牌ID"""
        return self._current_brand_id


# 全局规范上下文管理器实例
rules_context = RulesContextManager()