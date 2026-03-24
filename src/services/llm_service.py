"""品牌合规审核平台 - LLM服务"""

import json
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.config import settings

logger = logging.getLogger(__name__)


# 精简版Prompt - 减少Token消耗
COMPRESSED_AUDIT_PROMPT = '''你是品牌视觉合规审计官。根据以下品牌规范审核设计稿。

【品牌规范】
{rules_text}

【审核要点】
Logo: 位置左上角，高度≥画面4.2%，不得变形/改色
色彩: 主色系≤3种，符合"阳光、健康、专业、生态"导向
字体: 推荐:黑体/宋体，禁止:书法字/花体字
排版: 文字不压主体，层级清晰，图文反差足

【输出格式】JSON:
{{
  "score": 0-100,
  "status": "pass|warning|fail",
  "detection": {{
    "colors": [{{"hex": "#XXX", "name": "名称", "percent": 比例}}],
    "logo": {{"found": bool, "position": "位置", "size_percent": 数值, "position_correct": bool}},
    "texts": ["识别的文字"],
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
}}'''


class LLMService:
    """LLM服务 - 调用豆包多模态API"""

    def __init__(self) -> None:
        self._llm = None

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
                timeout=120,  # 增加超时时间
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
        progress_callback=None,
    ) -> dict[str, Any]:
        """
        审核图片

        Args:
            image_base64: Base64编码的图片数据
            image_format: 图片格式 (png/jpeg)
            rules_text: 品牌规范文本
            progress_callback: 进度回调（未使用）

        Returns:
            审核结果字典
        """
        try:
            # 构建Prompt
            system_content = COMPRESSED_AUDIT_PROMPT.format(rules_text=rules_text)
            image_url = f"data:image/{image_format};base64,{image_base64}"

            user_content = [
                {"type": "text", "text": "审核这张设计稿，输出JSON格式报告。"},
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

            return result

        except Exception as e:
            logger.error(f"审核失败: {e}")
            return self._build_error_result(f"审核过程出错: {str(e)}")

    def _parse_json_response(self, content: str) -> Optional[dict]:
        """解析LLM响应中的JSON"""
        import re

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

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