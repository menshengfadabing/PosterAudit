"""品牌合规审核平台 - 配置管理"""

import json
from pathlib import Path
from typing import Any, Optional

from pydantic_settings import BaseSettings


def get_app_dir() -> Path:
    """获取应用目录（支持打包后的路径）"""
    import sys
    if getattr(sys, 'frozen', False):
        # 打包后的路径
        return Path(sys.executable).parent
    else:
        # 开发环境路径
        return Path(__file__).parent.parent.parent


def ensure_data_dirs():
    """确保所有必要的数据目录存在"""
    app_dir = get_app_dir()

    # 创建必要的目录
    dirs = [
        app_dir / "data",
        app_dir / "data" / "rules",
        app_dir / "data" / "audit_history",
        app_dir / "data" / "exports",
        app_dir / "data" / "uploads",
        app_dir / "config",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    return app_dir


class Settings(BaseSettings):
    """应用配置"""

    # 规则解析模型（纯文本）
    deepseek_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v3-2-251201"

    # 海报分析模型（多模态）
    openai_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    openai_api_key: str = ""
    doubao_model: str = "doubao-seed-2-0-pro-260215"

    # 应用配置
    brand_rules_path: str = ""
    data_dir: str = ""
    log_level: str = "INFO"

    # 缓存配置
    cache_enabled: bool = True
    cache_ttl: int = 3600
    cache_max_size: int = 1000

    # Prompt配置
    use_compressed_prompt: bool = True
    use_few_shot: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 设置默认路径
        app_dir = get_app_dir()
        if not self.brand_rules_path:
            self.brand_rules_path = str(app_dir / "config" / "brand_rules.json")
        if not self.data_dir:
            self.data_dir = str(app_dir / "data")


class BrandRulesLoader:
    """品牌规范加载器"""

    _instance: Optional["BrandRulesLoader"] = None
    _rules: Optional[dict[str, Any]] = None

    def __new__(cls) -> "BrandRulesLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, path: Optional[str] = None) -> dict[str, Any]:
        """加载品牌规范配置"""
        if self._rules is not None:
            return self._rules

        config_path = Path(path or Settings().brand_rules_path)
        if not config_path.exists():
            raise FileNotFoundError(f"品牌规范配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            self._rules = json.load(f)

        return self._rules

    def get_rules_text(self, brand_id: Optional[str] = None) -> str:
        """获取品牌规范的文本描述"""
        rules = self.load()
        return self._build_rules_text(rules)

    def _build_rules_text(self, rules: dict) -> str:
        """构建规范文本"""
        text_parts = []

        rules_data = rules.get("rules", {})
        color_rules = rules_data.get("color", {})
        logo_rules = rules_data.get("logo", {})
        font_rules = rules_data.get("font", {})
        copywriting_rules = rules_data.get("copywriting", {})
        layout_rules = rules_data.get("layout", {})

        # 色彩规范
        text_parts.append("## 色彩规范")
        if primary := color_rules.get("primary"):
            text_parts.append(f"- 主色：{primary.get('value')}（{primary.get('name')}）")
        if secondary := color_rules.get("secondary"):
            secondary_colors = "、".join(f"{c.get('value')}（{c.get('name')}）" for c in secondary)
            text_parts.append(f"- 辅助色：{secondary_colors}")
        if forbidden := color_rules.get("forbidden"):
            forbidden_colors = "、".join(f"{c.get('value')}（{c.get('name')}）" for c in forbidden)
            text_parts.append(f"- 禁用色：{forbidden_colors}")

        # Logo规范
        text_parts.append("\n## Logo规范")
        text_parts.append(f"- 位置：必须位于{logo_rules.get('position_description', '左上角')}")
        if size_range := logo_rules.get("size_range"):
            text_parts.append(f"- 尺寸：占图片宽度的{size_range.get('min')}%-{size_range.get('max')}%")
        text_parts.append(f"- 安全间距：Logo四周至少保留{logo_rules.get('safe_margin_px', 20)}px空白区域")

        # 字体规范
        text_parts.append("\n## 字体规范")
        if allowed := font_rules.get("allowed"):
            text_parts.append(f"- 允许使用：{'、'.join(allowed)}")
        if forbidden := font_rules.get("forbidden"):
            text_parts.append(f"- 禁止使用：{'、'.join(forbidden)}")

        # 文案规范
        text_parts.append("\n## 文案规范")
        if forbidden_words := copywriting_rules.get("forbidden_words"):
            words = "、".join(w.get("word", "") for w in forbidden_words)
            text_parts.append(f"- 禁用词：{words}")

        # 布局规范
        text_parts.append("\n## 布局规范")
        text_parts.append(f"- {layout_rules.get('description', '元素布局应整洁')}")

        return "\n".join(text_parts)

    def reload(self) -> None:
        """重新加载配置"""
        self._rules = None


# 全局配置实例
settings = Settings()
brand_rules = BrandRulesLoader()