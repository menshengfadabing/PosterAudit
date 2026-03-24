"""品牌合规审核平台 - LLM服务"""

import json
import logging
import hashlib
from typing import Any, Optional
from functools import lru_cache

from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.config import settings

logger = logging.getLogger(__name__)


# 压缩版Prompt - 保留核心审核标准
COMPRESSED_AUDIT_PROMPT = '''你是品牌视觉合规审计官，审核设计稿是否符合品牌规范。

【品牌规范】
{rules_text}

═══════════════════════════════════════════════════════════════════
                        审核标准（共20项）
═══════════════════════════════════════════════════════════════════

【Logo规范 - L01至L07】
L01 结构完整性: Logo不得拉伸、变形、拆改
L02 标准色规范: 仅允许品牌色、反白版(#FFFFFF)、墨稿黑，禁止其他颜色
L03 背景适配: 深色背景用反白版，浅色背景用原色版
L04 位置规范: 必须位于画面左上角
L05 最小比例: 高度不低于画面高度的4.2%
L06 安全区: Logo周围不得被文字或图形侵入
L07 联合标识: 需具有清晰分隔关系

【色彩规范 - C01至C03】
C01 色系数量: 主色系不超过3种
C02 配色比例: 符合主色、辅助色、点缀色层次逻辑
C03 主色调方向: 应符合"阳光、健康、专业、生态"导向

【字体规范 - F01至F02】
F01 字体数量: 单个版面不超过3种
F02 字体风格: 推荐黑体、宋体，禁止书法字、花体字、装饰性字体

【排版规范 - T01至T04】
T01 文本位置: 优先放置于空白区，不得压主体焦点
T02 信息层级: 版面应有明确视觉中心和清晰层级
T03 对齐方式: 与主体结构和版式逻辑一致
T04 图文反差: 文字与背景有足够反差保证可读性

【风格维度 - S01至S04】
S01 阳光: 明亮、积极、向上（负向：阴暗、压抑、下降感）
S02 健康: 舒适、自然、真实（负向：过度艰苦、信息拥堵）
S03 专业: 有序、清晰、可信（负向：主体单薄、逻辑混乱）
S04 生态: 温暖、生机、协调（负向：生命力不足、风格不搭）

═══════════════════════════════════════════════════════════════════
                        输出格式
═══════════════════════════════════════════════════════════════════

输出JSON格式：
{{
  "score": <0-100>,
  "status": "<pass|warning|fail>",
  "detection": {{
    "colors": [{{"hex": "#XXX", "name": "名称", "percent": 占比}}],
    "logo": {{"found": bool, "position": "位置", "size_percent": 数值, "color_correct": bool, "position_correct": bool}},
    "texts": ["识别到的文字"],
    "fonts": [{{"text": "文字", "font_family": "字体", "is_forbidden": bool}}]
  }},
  "checks": {{
    "logo_checks": [{{"code": "L01", "name": "名称", "status": "pass|warn|fail", "detail": "说明"}}],
    "color_checks": [...],
    "font_checks": [...],
    "layout_checks": [...],
    "style_checks": [...]
  }},
  "issues": [{{"type": "类型", "severity": "critical|major|minor", "code": "编号", "description": "描述", "suggestion": "建议"}}],
  "summary": "总体评价"
}}

要求：checks必须包含全部20项检查结果，每项都有code/name/status/detail。
'''


class AuditCache:
    """审核结果缓存"""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self._cache: dict[str, tuple[float, Any]] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, image_base64: str, brand_id: Optional[str] = None) -> str:
        """生成缓存键"""
        image_hash = hashlib.md5(image_base64.encode()).hexdigest()[:16]
        brand = brand_id or "default"
        return f"{brand}:{image_hash}"

    def get(self, image_base64: str, brand_id: Optional[str] = None) -> Optional[dict]:
        """获取缓存"""
        import time
        key = self._make_key(image_base64, brand_id)

        if key in self._cache:
            timestamp, value = self._cache[key]
            if time.time() - timestamp < self.ttl:
                self._hits += 1
                return value
            else:
                del self._cache[key]

        self._misses += 1
        return None

    def set(self, image_base64: str, value: dict, brand_id: Optional[str] = None) -> None:
        """设置缓存"""
        import time
        key = self._make_key(image_base64, brand_id)

        # LRU清理
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]

        self._cache[key] = (time.time(), value)

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> dict:
        """获取统计信息"""
        total = self._hits + self._misses
        hit_rate = self._hits / total * 100 if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%"
        }


# 全局缓存实例
audit_cache = AuditCache()


class LLMService:
    """LLM服务 - 调用豆包多模态API"""

    def __init__(self) -> None:
        self._llm = None
        self._use_cache = settings.cache_enabled

    @property
    def llm(self):
        """获取LLM实例（懒加载）"""
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(
                model=settings.doubao_model,
                openai_api_base=settings.openai_api_base,
                openai_api_key=settings.openai_api_key,
                temperature=0.1,
            )
        return self._llm

    def set_api_config(self, api_key: str, api_base: str = None, model: str = None) -> None:
        """设置API配置"""
        settings.openai_api_key = api_key
        if api_base:
            settings.openai_api_base = api_base
        if model:
            settings.doubao_model = model
        self._llm = None  # 重置LLM实例
        logger.info("API配置已更新")

    def audit_image(
        self,
        image_base64: str,
        image_format: str = "png",
        rules_text: str = "",
        use_cache: Optional[bool] = None,
    ) -> dict[str, Any]:
        """
        审核图片

        Args:
            image_base64: Base64编码的图片数据
            image_format: 图片格式 (png/jpeg)
            rules_text: 品牌规范文本
            use_cache: 是否使用缓存

        Returns:
            审核结果字典
        """
        should_use_cache = use_cache if use_cache is not None else self._use_cache

        # 尝试从缓存获取
        if should_use_cache:
            cached = audit_cache.get(image_base64)
            if cached is not None:
                logger.info("使用缓存结果")
                return cached

        try:
            # 构建Prompt
            system_content = COMPRESSED_AUDIT_PROMPT.format(rules_text=rules_text)
            image_url = f"data:image/{image_format};base64,{image_base64}"

            user_content = [
                {"type": "text", "text": "请对这张设计稿图片进行品牌合规审核，按照Logo标志规范、色彩规范、字体规范、排版规范、风格倾向五个维度逐一检查，输出完整的审核报告。"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]

            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]

            # 调用LLM
            logger.info("正在调用API进行审核...")
            response = self.llm.invoke(messages)
            content = response.content

            # 解析结果
            result = self._parse_json_response(content)
            if result is None:
                return self._build_error_result(f"审核结果解析失败")

            # 标准化结果
            result = self._normalize_result(result)

            # 存入缓存
            if should_use_cache:
                audit_cache.set(image_base64, result)

            return result

        except Exception as e:
            logger.error(f"审核失败: {e}")
            return self._build_error_result(f"审核过程出错: {str(e)}")

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """解析LLM响应中的JSON"""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        import re
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        brace_match = re.search(r"\{[\s\S]*\}", content)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _build_error_result(self, error_msg: str) -> dict:
        """构建错误结果"""
        return {
            "score": 0,
            "status": "fail",
            "detection": {
                "colors": [],
                "logo": {"found": False},
                "texts": [],
                "fonts": [],
                "layout": {},
                "style": {}
            },
            "checks": {},
            "issues": [{
                "type": "layout",
                "severity": "critical",
                "code": "ERR",
                "description": error_msg,
                "suggestion": "请重试或检查图片格式"
            }],
            "summary": f"审核失败：{error_msg}",
        }

    def _normalize_result(self, result: dict) -> dict:
        """标准化结果"""
        result.setdefault("score", 50)
        result.setdefault("status", "warning")
        result.setdefault("summary", "审核完成")
        result.setdefault("detection", {})
        result.setdefault("checks", {})
        result.setdefault("issues", [])

        detection = result["detection"]
        detection.setdefault("colors", [])
        detection.setdefault("logo", {"found": False})
        detection.setdefault("texts", [])
        detection.setdefault("fonts", [])
        detection.setdefault("layout", {})
        detection.setdefault("style", {})

        return result


# 全局LLM服务实例
llm_service = LLMService()