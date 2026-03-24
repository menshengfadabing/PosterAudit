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
        self._current_brand_id: str = "default"

        self._ensure_directories()
        self._load_default_rules()

    def _ensure_directories(self) -> None:
        """确保目录存在"""
        self.rules_dir.mkdir(parents=True, exist_ok=True)

    def _load_default_rules(self) -> None:
        """加载默认规范配置"""
        default_path = Path(settings.brand_rules_path)
        if default_path.exists():
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                rules = self._parse_rules_data(data, str(default_path))
                self._cache["default"] = rules
                logger.info(f"已加载默认规范: {rules.brand_name}")
            except Exception as e:
                logger.error(f"加载默认规范失败: {e}")

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

        if brand_id != "default" and "default" in self._cache:
            return self._cache["default"]

        return None

    def set_current_brand(self, brand_id: str) -> bool:
        """设置当前品牌"""
        if brand_id in self._cache or (self.rules_dir / brand_id).exists():
            self._current_brand_id = brand_id
            logger.info(f"当前品牌已切换: {brand_id}")
            return True
        return False

    def get_rules_text(self, brand_id: Optional[str] = None) -> str:
        """获取规范的文本描述"""
        rules = self.get_rules(brand_id)
        if rules is None:
            return "未找到品牌规范，请先上传规范文档。"

        text_parts = []

        text_parts.append(f"# 品牌名称：{rules.brand_name}")
        if rules.source:
            text_parts.append(f"规范来源：{rules.source}")
        text_parts.append("")

        # 色彩规范
        if rules.color:
            text_parts.append("## 一、色彩规范")
            text_parts.append("")

            if rules.color.primary:
                text_parts.append("### 1. 主色（品牌标准色）")
                text_parts.append(f"- 颜色名称：{rules.color.primary.name}")
                text_parts.append(f"- 色值：{rules.color.primary.value}")
                text_parts.append("")

            if rules.color.secondary:
                text_parts.append("### 2. 辅助色/允许色")
                for c in rules.color.secondary:
                    text_parts.append(f"- {c.name}：{c.value}")
                text_parts.append("")

            if rules.color.forbidden:
                text_parts.append("### 3. 禁用色")
                for c in rules.color.forbidden:
                    text_parts.append(f"- {c.name or '非规范色'}：{c.reason or '禁止使用'}")
                text_parts.append("")

        # Logo规范
        if rules.logo:
            text_parts.append("## 二、Logo标志规范")
            text_parts.append("")

            text_parts.append("### L01 Logo结构完整性")
            text_parts.append("- Logo不得被拉伸、压缩、变形、拆改或改变组合关系")
            text_parts.append("")

            text_parts.append("### L04 Logo位置规范")
            if rules.logo.position_description:
                text_parts.append(f"- 品牌标识应位于{rules.logo.position_description}")
            else:
                text_parts.append("- 品牌标识应位于画面左上角")
            text_parts.append("")

            text_parts.append("### L05 Logo最小显示比例")
            if rules.logo.size_range:
                min_size = rules.logo.size_range.get("min", 5)
                text_parts.append(f"- Logo高度不得低于画面高度的{min_size}%")
            text_parts.append("")

            text_parts.append("### L06 Logo安全区规范")
            text_parts.append(f"- Logo周围应保留安全区")
            if rules.logo.safe_margin_px:
                text_parts.append(f"- 安全间距至少{rules.logo.safe_margin_px}px")
            text_parts.append("")

        # 字体规范
        if rules.font:
            text_parts.append("## 三、字体规范")
            text_parts.append("")

            text_parts.append("### F01 字体数量控制")
            text_parts.append("- 单个版面的字体数量应控制在3种以内")
            text_parts.append("")

            text_parts.append("### F02 字体风格合规性")
            if rules.font.allowed:
                text_parts.append(f"- 推荐字体：{'、'.join(rules.font.allowed)}")
            if rules.font.forbidden:
                text_parts.append(f"- 禁用字体：{'、'.join(rules.font.forbidden)}")
            text_parts.append("")

        # 文案规范
        if rules.copywriting and (rules.copywriting.forbidden_words or rules.copywriting.required_content):
            text_parts.append("## 四、文案规范")
            text_parts.append("")

            if rules.copywriting.forbidden_words:
                text_parts.append("### 禁用词")
                words_by_category: dict[str, list[str]] = {}
                for item in rules.copywriting.forbidden_words:
                    cat = item.category or "其他"
                    words_by_category.setdefault(cat, []).append(item.word)
                for cat, words in words_by_category.items():
                    text_parts.append(f"- {cat}：{'、'.join(words)}")
                text_parts.append("")

        # 布局规范
        if rules.layout:
            text_parts.append("## 五、排版布局规范")
            text_parts.append("")

            text_parts.append("### T01 文本与主体关系")
            text_parts.append("- 文字应优先放置于图片空白区域")
            text_parts.append("- 文字不得压在主体焦点区域")
            text_parts.append("")

            text_parts.append("### T02 版面聚焦与信息层级")
            text_parts.append("- 版面应具备明确的视觉中心")
            text_parts.append("- 应具备清晰的主标题、次级信息、正文层级关系")
            text_parts.append("")

            if rules.layout.description:
                text_parts.append("### 其他布局要求")
                text_parts.append(rules.layout.description)
                text_parts.append("")

        # 风格倾向
        text_parts.append("## 六、风格倾向校准")
        text_parts.append("")
        text_parts.append("所有审核均服从统一审美价值导向：阳光、健康、专业、生态")
        text_parts.append("")

        return "\n".join(text_parts)

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