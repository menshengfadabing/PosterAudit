"""品牌合规审核平台 - LLM服务"""

import json
import logging
import math
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.config import settings

logger = logging.getLogger(__name__)


# 审核Prompt - 单图审核
COMPRESSED_AUDIT_PROMPT = '''你是品牌视觉合规审计官。根据以下品牌规范规则清单，逐条审核设计稿的合规性。

【品牌规范规则清单】
{rules_checklist}

【输出格式】JSON:
{{
  "score": 0-100,
  "status": "pass|warning|fail",
  "rule_checks": [
    {{"rule_id": "Rule_N", "status": "pass|fail|review", "confidence": 0.0-1.0, "detail": "判断依据和说明"}}
  ],
  "detection": {{
    "colors": [{{"hex": "#XXX", "name": "名称", "percent": 比例}}],
    "logo": {{"found": bool, "position": "位置", "size_percent": 数值, "position_correct": bool, "deformed": bool}},
    "texts": ["识别的文字"],
    "fonts": [{{"text": "文字", "font_family": "字体", "is_forbidden": bool}}]
  }},
  "issues": [{{"type": "color|logo|font|layout|style", "severity": "critical|major|minor", "description": "问题描述", "suggestion": "修改建议"}}],
  "summary": "总体评价"
}}

重要提示：
1. rule_checks 数组必须包含每条规则的检查结果，rule_id 必须与清单中的一致
2. status: pass=合规, fail=不合规, review=需人工复核
3. confidence: 对判断的置信度，0-1之间
4. detail: 简要说明判断依据'''

# 批量审核Prompt - 多图合并
BATCH_AUDIT_PROMPT = '''你是品牌视觉合规审计官。根据以下品牌规范规则清单，逐条审核多张设计稿的合规性。

【品牌规范规则清单】
{rules_checklist}

【输出格式】JSON数组，每张图片一个对象:
[
  {{
    "image_index": 0,
    "score": 0-100,
    "status": "pass|warning|fail",
    "rule_checks": [
      {{"rule_id": "Rule_N", "status": "pass|fail|review", "confidence": 0.0-1.0, "detail": "判断依据"}}
    ],
    "detection": {{
      "colors": [{{"hex": "#XXX", "name": "名称", "percent": 比例}}],
      "logo": {{"found": bool, "position": "位置", "size_percent": 数值, "position_correct": bool, "deformed": bool}},
      "texts": ["识别的文字"],
      "fonts": [{{"text": "文字", "font_family": "字体", "is_forbidden": bool}}]
    }},
    "issues": [{{"type": "color|logo|font|layout|style", "severity": "critical|major|minor", "description": "问题描述", "suggestion": "修改建议"}}],
    "summary": "总体评价"
  }},
  ... (每张图片一个对象)
]

重要：
1. 输出必须是JSON数组，数组长度与图片数量一致，image_index从0开始
2. rule_checks 数组必须包含每条规则的检查结果
3. status: pass=合规, fail=不合规, review=需人工复核'''


class LLMService:
    """LLM服务 - 调用豆包多模态API"""

    # 模型上下文窗口配置（可根据实际模型调整）
    MODEL_CONTEXT_LIMITS = {
        # 模型名称: (上下文窗口大小, 输出token限制)
        "default": (128000, 8192),
        "gpt-4o": (128000, 16384),
        "gpt-4-turbo": (128000, 4096),
        "claude-3-opus": (200000, 4096),
        "claude-3-sonnet": (200000, 4096),
        "doubao-vision": (128000, 8192),  # 豆包视觉模型
    }

    # Token估算参数
    TEXT_TOKEN_RATIO = 1.5  # 中文约1.5字符/token
    IMAGE_BASE_TOKENS = 85  # 图片基础token
    IMAGE_TOKEN_PER_TILE = 170  # 每个512x512 tile的token

    # 批量审核输出估算
    OUTPUT_TOKENS_PER_IMAGE = 2000  # 每张图片输出约2000 tokens（非常保守的估计）
    OUTPUT_OVERHEAD = 200  # 输出固定开销

    def __init__(self) -> None:
        self._llm = None
        self._context_limit = None
        self._output_limit = None

    @property
    def llm(self):
        """获取LLM实例（懒加载）"""
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            # 火山引擎模型支持更大的输出
            # 默认 max_tokens=4096，需要显式设置更大值
            self._llm = ChatOpenAI(
                model=settings.doubao_model,
                base_url=settings.openai_api_base,
                api_key=settings.openai_api_key,
                temperature=0.1,
                timeout=180,
                max_tokens=16384,  # 16k 输出限制
            )
        return self._llm

    @property
    def context_limit(self) -> int:
        """获取当前模型的上下文窗口限制"""
        if self._context_limit is None:
            model_name = settings.doubao_model.lower()
            for key, (ctx, out) in self.MODEL_CONTEXT_LIMITS.items():
                if key in model_name:
                    self._context_limit = ctx
                    self._output_limit = out
                    break
            else:
                self._context_limit, self._output_limit = self.MODEL_CONTEXT_LIMITS["default"]
        return self._context_limit

    @property
    def output_limit(self) -> int:
        """获取当前模型的输出token限制"""
        if self._output_limit is None:
            _ = self.context_limit  # 触发初始化
        return self._output_limit

    def estimate_image_tokens(self, width: int, height: int) -> int:
        """估算图片的token消耗"""
        # OpenAI的多模态token计算方式
        # 512x512以下: 85 tokens
        # 更大的图片: 85 + 170 * tiles数量
        if width <= 512 and height <= 512:
            return self.IMAGE_BASE_TOKENS

        tiles_x = math.ceil(width / 512)
        tiles_y = math.ceil(height / 512)
        tiles = tiles_x * tiles_y
        return self.IMAGE_BASE_TOKENS + self.IMAGE_TOKEN_PER_TILE * tiles

    def estimate_text_tokens(self, text: str) -> int:
        """估算文本的token消耗"""
        return int(len(text) / self.TEXT_TOKEN_RATIO)

    def calculate_max_images(self, image_sizes: list[tuple[int, int]], rules_text: str = "") -> int:
        """
        动态计算单次API调用可容纳的最大图片数量

        综合考虑两个限制：
        1. 输入上下文窗口限制（图片 + prompt）
        2. 输出token限制（每张图片的审核结果）

        Args:
            image_sizes: 图片尺寸列表 [(width, height), ...]
            rules_text: 品牌规范文本

        Returns:
            可容纳的最大图片数量
        """
        # === 1. 基于输入上下文窗口计算 ===
        system_tokens = self.estimate_text_tokens(BATCH_AUDIT_PROMPT)
        rules_tokens = self.estimate_text_tokens(rules_text)
        input_overhead = system_tokens + rules_tokens + 500

        available_input = self.context_limit - input_overhead

        max_by_input = 0
        total_input_tokens = 0

        for w, h in image_sizes:
            img_tokens = self.estimate_image_tokens(w, h)
            if total_input_tokens + img_tokens <= available_input:
                total_input_tokens += img_tokens
                max_by_input += 1
            else:
                break

        # === 2. 基于输出token限制计算 ===
        # 输出限制是真正的瓶颈！
        # 每张图片的审核结果约需 OUTPUT_TOKENS_PER_IMAGE tokens
        available_output = self.output_limit - self.OUTPUT_OVERHEAD
        max_by_output = max(1, available_output // self.OUTPUT_TOKENS_PER_IMAGE)

        # === 3. 取较小值 ===
        max_images = min(max_by_input, max_by_output)

        # 安全上限（保守设置，避免输出token超限）
        max_images = min(max_images, 2)

        logger.info(
            f"动态计算: 输入限制={max_by_input}张, 输出限制={max_by_output}张, "
            f"最终={max_images}张 (上下文{self.context_limit}, 输出限制{self.output_limit})"
        )

        return max(max_images, 1)

    def set_api_config(self, api_key: str, api_base: str = None, model: str = None) -> None:
        """设置API配置"""
        settings.openai_api_key = api_key
        if api_base:
            settings.openai_api_base = api_base
        if model:
            settings.doubao_model = model
        self._llm = None  # 重置LLM实例
        self._context_limit = None  # 重置上下文限制
        self._output_limit = None  # 重置输出限制
        logger.info("API配置已更新")

    def audit_image(
        self,
        image_base64: str,
        image_format: str = "png",
        rules_checklist: list[dict] = None,
        progress_callback=None,
    ) -> dict[str, Any]:
        """
        审核单张图片

        Args:
            image_base64: Base64编码的图片数据
            image_format: 图片格式 (png/jpeg)
            rules_checklist: 规则检查清单
            progress_callback: 进度回调（未使用）

        Returns:
            审核结果字典
        """
        try:
            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 构建Prompt
            system_content = COMPRESSED_AUDIT_PROMPT.format(rules_checklist=checklist_text)
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

    def audit_image_stream(
        self,
        image_base64: str,
        image_format: str = "png",
        rules_checklist: list[dict] = None,
        stream_callback=None,
    ):
        """
        流式审核单张图片

        Args:
            image_base64: Base64编码的图片数据
            image_format: 图片格式 (png/jpeg)
            rules_checklist: 规则检查清单
            stream_callback: 流式回调函数，接收每个文本块

        Yields:
            每个文本块
        """
        full_content = ""

        try:
            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 构建Prompt
            system_content = COMPRESSED_AUDIT_PROMPT.format(rules_checklist=checklist_text)
            image_url = f"data:image/{image_format};base64,{image_base64}"

            user_content = [
                {"type": "text", "text": "审核这张设计稿，输出JSON格式报告。"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]

            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]

            # 调用LLM流式API
            logger.info("正在调用API进行流式审核...")

            for chunk in self.llm.stream(messages):
                if chunk.content:
                    text_chunk = chunk.content
                    full_content += text_chunk

                    # 回调
                    if stream_callback:
                        stream_callback(text_chunk)

                    yield text_chunk

        except Exception as e:
            logger.error(f"流式审核失败: {e}")
            error_msg = f"审核过程出错: {str(e)}"
            if stream_callback:
                stream_callback(f"\n\n[错误] {error_msg}")
            yield error_msg

    def parse_stream_result(self, full_content: str) -> dict[str, Any]:
        """
        解析流式输出的完整结果

        Args:
            full_content: 流式输出的完整文本

        Returns:
            解析后的结果字典
        """
        result = self._parse_json_response(full_content)
        if result is None:
            return self._build_error_result("审核结果解析失败")
        return self._normalize_result(result)

    def _format_checklist(self, checklist: list[dict]) -> str:
        """格式化规则清单为Prompt文本"""
        if not checklist:
            return "无具体规则"

        lines = []
        for rule in checklist:
            rule_id = rule.get("rule_id", "Rule_?")
            content = rule.get("content", "")
            category = rule.get("category", "")
            lines.append(f"{rule_id}: {content} [{category}]")

        return "\n".join(lines)

    def audit_images_batch(
        self,
        images: list[dict],
        rules_checklist: list[dict] = None,
        progress_callback=None,
    ) -> list[dict[str, Any]]:
        """
        单次API调用审核多张图片（合并请求方案）

        Args:
            images: 图片列表，每个元素包含 {"base64": str, "format": str}
            rules_checklist: 规则检查清单
            progress_callback: 进度回调

        Returns:
            审核结果列表
        """
        try:
            if not images:
                return []

            if len(images) == 1:
                # 单张图片，使用单图接口
                result = self.audit_image(
                    images[0]["base64"],
                    images[0].get("format", "jpeg"),
                    rules_checklist
                )
                return [result]

            logger.info(f"批量审核: 单次API调用处理 {len(images)} 张图片")

            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 构建Prompt
            system_content = BATCH_AUDIT_PROMPT.format(rules_checklist=checklist_text)

            # 构建用户消息，包含多张图片
            user_content = [{"type": "text", "text": f"审核以下{len(images)}张设计稿，输出JSON数组格式的报告。每张图片对应一个对象。"}]

            for i, img in enumerate(images):
                image_url = f"data:image/{img.get('format', 'jpeg')};base64,{img['base64']}"
                user_content.append({
                    "type": "text",
                    "text": f"\n--- 图片 {i + 1} ---"
                })
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })

            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]

            # 调用LLM
            logger.info("正在调用API进行批量审核...")
            response = self.llm.invoke(messages)
            content = response.content

            # 解析结果
            results = self._parse_batch_response(content, len(images))

            if progress_callback:
                progress_callback(len(images), len(images), "批量审核完成")

            return results

        except Exception as e:
            logger.error(f"批量审核失败: {e}")
            return [self._build_error_result(f"批量审核出错: {str(e)}") for _ in images]

    def audit_images_batch_stream(
        self,
        images: list[dict],
        rules_checklist: list[dict] = None,
        stream_callback=None,
    ) -> list[dict[str, Any]]:
        """
        流式批量审核多张图片（单次API调用，流式输出JSON）

        Args:
            images: 图片列表，每个元素包含 {"base64": str, "format": str}
            rules_checklist: 规则检查清单
            stream_callback: 流式回调函数，接收每个文本块

        Returns:
            审核结果列表
        """
        try:
            if not images:
                return []

            if len(images) == 1:
                # 单张图片，使用单图流式接口
                full_content = ""
                for chunk in self.audit_image_stream(
                    images[0]["base64"],
                    images[0].get("format", "jpeg"),
                    rules_checklist,
                    stream_callback,
                ):
                    full_content += chunk
                result = self.parse_stream_result(full_content)
                return [result]

            logger.info(f"流式批量审核: 单次API调用处理 {len(images)} 张图片")

            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 构建Prompt
            system_content = BATCH_AUDIT_PROMPT.format(rules_checklist=checklist_text)

            # 构建用户消息，包含多张图片
            user_content = [{"type": "text", "text": f"审核以下{len(images)}张设计稿，输出JSON数组格式的报告。每张图片对应一个对象。"}]

            for i, img in enumerate(images):
                image_url = f"data:image/{img.get('format', 'jpeg')};base64,{img['base64']}"
                user_content.append({
                    "type": "text",
                    "text": f"\n--- 图片 {i + 1} ---"
                })
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })

            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]

            # 调用LLM流式API
            logger.info("正在调用API进行流式批量审核...")
            full_content = ""

            for chunk in self.llm.stream(messages):
                if chunk.content:
                    text_chunk = chunk.content
                    full_content += text_chunk
                    if stream_callback:
                        stream_callback(text_chunk)

            # 解析结果
            results = self._parse_batch_response(full_content, len(images))
            return results

        except Exception as e:
            logger.error(f"流式批量审核失败: {e}")
            return [self._build_error_result(f"批量审核出错: {str(e)}") for _ in images]

    def _parse_batch_response(self, content: str, expected_count: int) -> list[dict]:
        """解析批量审核响应"""
        import re

        results = []

        # 记录原始响应用于调试
        logger.debug(f"批量审核原始响应 (前2000字符): {content[:2000]}")

        # 尝试解析JSON数组
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        results.append(self._normalize_result(item))
                if len(results) == expected_count:
                    logger.info(f"批量解析成功: {expected_count}个结果")
                    return results
                elif len(results) > 0:
                    logger.warning(f"批量解析部分成功: 预期{expected_count}个，实际{len(results)}个")
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}")

        # 尝试提取JSON数组块
        array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', content)
        if array_match:
            try:
                data = json.loads(array_match.group())
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            results.append(self._normalize_result(item))
                    if len(results) == expected_count:
                        logger.info(f"通过正则提取解析成功: {expected_count}个结果")
                        return results
                    elif len(results) > 0:
                        logger.warning(f"正则提取部分成功: 预期{expected_count}个，实际{len(results)}个")
            except json.JSONDecodeError as e:
                logger.warning(f"正则提取后JSON解析失败: {e}")

        # 记录解析失败的详细信息
        logger.error(f"批量响应解析完全失败，预期{expected_count}个结果")
        logger.error(f"响应内容长度: {len(content)}, 前500字符: {content[:500]}")

        # 补充缺失的结果
        while len(results) < expected_count:
            results.append(self._build_error_result(f"第{len(results)+1}张图片结果解析失败"))

        return results[:expected_count]

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
            "rule_checks": [],
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
        result.setdefault("rule_checks", [])
        result.setdefault("issues", [])

        detection = result["detection"]
        detection.setdefault("colors", [])
        detection.setdefault("logo", {"found": False})
        detection.setdefault("texts", [])
        detection.setdefault("fonts", [])
        detection.setdefault("layout", {})
        detection.setdefault("style", {})

        return result

    def test_deepseek_connection(self) -> tuple[bool, str]:
        """
        测试DeepSeek API连通性

        Returns:
            (success, message) 元组
        """
        try:
            from langchain_openai import ChatOpenAI

            if not settings.deepseek_api_key:
                return False, "未配置DeepSeek API Key"

            llm = ChatOpenAI(
                model=settings.deepseek_model,
                base_url=settings.deepseek_api_base,
                api_key=settings.deepseek_api_key,
                temperature=0.1,
                timeout=30,
            )

            response = llm.invoke("你好，请回复'连接成功'")
            if response and response.content:
                return True, "连接成功"
            return False, "响应异常"

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, "API Key无效"
            elif "timeout" in error_msg.lower():
                return False, "连接超时"
            elif "connection" in error_msg.lower():
                return False, "无法连接到服务器"
            return False, f"连接失败: {error_msg[:50]}"

    def test_doubao_connection(self) -> tuple[bool, str]:
        """
        测试Doubao API连通性

        Returns:
            (success, message) 元组
        """
        try:
            from langchain_openai import ChatOpenAI

            if not settings.openai_api_key:
                return False, "未配置Doubao API Key"

            # 使用一个简单的测试请求
            llm = ChatOpenAI(
                model=settings.doubao_model,
                base_url=settings.openai_api_base,
                api_key=settings.openai_api_key,
                temperature=0.1,
                timeout=30,
            )

            # 发送一个简单的文本请求测试连通性
            response = llm.invoke("测试连接")
            if response:
                return True, "连接成功"
            return False, "响应异常"

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                return False, "API Key无效"
            elif "timeout" in error_msg.lower():
                return False, "连接超时"
            elif "connection" in error_msg.lower():
                return False, "无法连接到服务器"
            return False, f"连接失败: {error_msg[:50]}"


# 全局LLM服务实例
llm_service = LLMService()