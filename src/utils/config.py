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

    # 文本模型（规则解析）
    llm_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v3-2-251201"

    # 多模态模型（海报审核）
    mllm_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    mllm_api_key: str = ""  # 单个 Key
    mllm_api_keys: str = ""  # 多个 Key，逗号分隔（优先）
    mllm_model: str = "doubao-seed-2-0-pro-260215"

    # 应用配置
    brand_rules_path: str = ""
    data_dir: str = ""
    log_level: str = "INFO"

    # Web API 配置
    database_url: str = "postgresql+psycopg2://postgres:postgres123456@localhost:5432/app"
    allowed_api_keys: str = ""   # 逗号分隔；为空时跳过鉴权（开发模式）
    require_api_key: bool = False  # 生产建议开启：未配置 ALLOWED_API_KEYS 则拒绝请求
    upload_dir: str = ""

    # 对象存储（MinIO）配置
    enable_minio_storage: bool = False
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "audit-images"
    minio_secure: bool = False
    minio_task_prefix: str = "tasks"
    minio_reference_prefix: str = "references"
    cors_allow_origins: str = "*"  # 生产建议配置为逗号分隔域名白名单

    # 角色鉴权配置（回源 Java userInfo）
    enable_java_auth: bool = False
    java_userinfo_url: str = ""
    java_token_header: str = "Token"
    java_auth_timeout_seconds: float = 5.0
    allow_header_auth_fallback: bool = True  # 非 Java 鉴权时是否允许通过 Header 透传身份

    # 用户数据隔离（历史/任务仅展示本人数据）
    enable_user_isolation: bool = True

    use_celery: bool = False
    redis_url: str = "redis://localhost:6379/0"
    redis_result_url: str = "redis://localhost:6379/1"
    redis_cache_url: str = "redis://localhost:6379/2"
    celery_worker_concurrency: int = 70
    task_status_ttl_seconds: int = 3600

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

    def get_mllm_api_keys(self) -> list[str]:
        """获取多模态 API Key 列表（支持多 Key）"""
        import os

        # 优先级 1: MLLM_API_KEYS 环境变量（逗号分隔）
        if self.mllm_api_keys:
            keys = [k.strip() for k in self.mllm_api_keys.split(",") if k.strip()]
            if keys:
                return keys

        # 优先级 2: MLLM_API_KEY_0, MLLM_API_KEY_1, ... 格式
        indexed_keys = []
        for i in range(10):  # 支持最多 10 个 Key
            key = os.getenv(f"MLLM_API_KEY_{i}", "")
            if key and key.strip():
                indexed_keys.append(key.strip())
        if indexed_keys:
            return indexed_keys

        # 优先级 3: 从项目 .env 文件中读取索引 Key（兼容 Celery 直接启动场景）
        env_path = get_app_dir() / ".env"
        if env_path.exists():
            file_keys: list[str] = []
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    row = line.strip()
                    if not row or row.startswith("#") or "=" not in row:
                        continue
                    k, _, v = row.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k.startswith("MLLM_API_KEY_") and v:
                        file_keys.append(v)
                if file_keys:
                    return file_keys
            except Exception:
                pass

        # 优先级 4: 单 Key 配置
        if self.mllm_api_key:
            return [self.mllm_api_key]

        return []

    def get_cors_allow_origins(self) -> list[str]:
        raw = (self.cors_allow_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


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
