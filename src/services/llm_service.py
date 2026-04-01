"""品牌合规审核平台 - LLM服务"""

import json
import logging
import math
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.config import settings
from src.utils.json_parser import parse_json_response, parse_json_array

logger = logging.getLogger(__name__)


# 审核Prompt - 单图审核（精简输出）
COMPRESSED_AUDIT_PROMPT = '''你是品牌视觉合规审计官。根据规则清单审核设计稿。

【规则清单 - 共{rule_count}条】
{rules_checklist}
{reference_hint}
【输出要求】只输出JSON:
{{
  "results": [
    {{"id": "Rule_N", "s": "p|f|r", "c": 0.0-1.0}}
  ],
  "detection": {{
    "colors": [{{"hex": "#XXX", "name": "名称", "percent": 比例}}],
    "logo": {{"found": bool, "position": "位置", "size_percent": 数值, "position_correct": bool, "deformed": bool}},
    "texts": ["识别的文字"],
    "fonts": [{{"text": "文字", "font_family": "字体", "is_forbidden": bool}}]
  }},
  "issues": [{{"type": "类型", "severity": "严重程度", "description": "问题", "suggestion": "建议"}}],
  "summary": "总体评价"
}}

字段说明:
- results: 规则结果数组，id=规则ID，s=状态(p=pass/f=fail/r=review)，c=置信度
- 必须为每条规则输出结果'''

# 参考图片提示模板
REFERENCE_IMAGE_PROMPT = '''
【标准参考图片】
以下提供了品牌的标准Logo/图标等参考图片。请仔细对比：
1. 将待审核图片中的Logo与参考图片进行视觉对比
2. 检查Logo的形状、比例、颜色是否与标准一致
3. 判断Logo是否存在变形、拉伸或颜色错误
'''

# 批量审核Prompt - 多图合并（精简输出）
BATCH_AUDIT_PROMPT = '''你是品牌视觉合规审计官。根据规则清单审核多张设计稿。
{reference_hint}
【规则清单 - 共{rule_count}条】
{rules_checklist}

【输出格式】JSON数组:
[
  {{
    "idx": 0,
    "results": [
      {{"id": "Rule_N", "s": "p|f|r", "c": 0.0-1.0}}
    ],
    "detection": {{
      "colors": [{{"hex": "#XXX", "name": "名称", "percent": 比例}}],
      "logo": {{"found": bool, "position": "位置", "size_percent": 数值}},
      "texts": ["识别的文字"],
      "fonts": [{{"text": "文字", "font_family": "字体", "is_forbidden": bool}}]
    }},
    "issues": [{{"type": "类型", "severity": "严重程度", "description": "问题", "suggestion": "建议"}}],
    "summary": "评价"
  }}
]

重要:
1. idx: 图片序号(从0开始)
2. results: 每条规则结果，id=规则ID，s=状态(p/f/r)，c=置信度
3. 必须为每张图片的每条规则输出结果'''


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
    OUTPUT_TOKENS_PER_IMAGE = 500  # 每张图片输出约500 tokens（简化格式后）
    OUTPUT_OVERHEAD = 200  # 输出固定开销

    def __init__(self) -> None:
        self._llm = None
        self._context_limit = None
        self._output_limit = None
        self._key_index = 0  # Key 轮询索引
        self._api_keys = []  # 缓存的 Key 列表

    def _get_next_api_key(self) -> str:
        """轮询获取下一个 API Key"""
        # 获取 Key 列表（首次或配置变更时刷新）
        keys = settings.get_openai_api_keys()
        if keys != self._api_keys:
            self._api_keys = keys
            self._key_index = 0
            logger.info(f"API Key 列表已更新，共 {len(keys)} 个")

        if not self._api_keys:
            logger.warning("未配置 API Key")
            return ""

        # 轮询选择
        key = self._api_keys[self._key_index % len(self._api_keys)]
        self._key_index += 1
        logger.debug(f"使用 API Key #{(self._key_index - 1) % len(self._api_keys) + 1}")
        return key

    @property
    def llm(self):
        """获取LLM实例（懒加载，使用轮询 Key）"""
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            # 火山引擎模型支持更大的输出
            # 默认 max_tokens=4096，需要显式设置更大值
            api_key = self._get_next_api_key()
            self._llm = ChatOpenAI(
                model=settings.doubao_model,
                base_url=settings.openai_api_base,
                api_key=api_key,
                temperature=0.1,
                timeout=180,
                max_tokens=16384,  # 16k 输出限制
            )
        return self._llm

    def reset_llm(self):
        """重置 LLM 实例（强制使用下一个 Key）"""
        self._llm = None
        self._key_index += 1  # 切换到下一个 Key

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

        # 安全上限（避免单次请求处理过多图片导致超时）
        # 之前硬编码为2，现在提高到10，让动态计算真正发挥作用
        MAX_IMAGES_PER_REQUEST = 10
        max_images = min(max_images, MAX_IMAGES_PER_REQUEST)

        logger.info(
            f"动态计算: 输入限制={max_by_input}张, 输出限制={max_by_output}张, "
            f"最终={max_images}张 (上下文{self.context_limit}, 输出限制{self.output_limit})"
        )

        return max(max_images, 1)

    def set_api_config(self, api_key: str = None, api_keys: list[str] = None, api_base: str = None, model: str = None) -> None:
        """
        设置API配置

        Args:
            api_key: 单个 API Key（兼容旧接口）
            api_keys: 多个 API Key 列表（新接口）
            api_base: API 基础 URL
            model: 模型名称
        """
        # 支持多 Key 设置
        if api_keys:
            settings.openai_api_keys = ",".join(api_keys)
        elif api_key:
            settings.openai_api_key = api_key
            settings.openai_api_keys = ""  # 清空多 Key 配置

        if api_base:
            settings.openai_api_base = api_base
        if model:
            settings.doubao_model = model

        # 重置所有缓存
        self._llm = None
        self._context_limit = None
        self._output_limit = None
        self._api_keys = []
        self._key_index = 0
        logger.info(f"API配置已更新，Key数量: {len(settings.get_openai_api_keys())}")

    def audit_image(
        self,
        image_base64: str,
        image_format: str = "png",
        rules_checklist: list[dict] = None,
        reference_images: list[dict] = None,
        progress_callback=None,
        api_key: str = None,
    ) -> dict[str, Any]:
        """
        审核单张图片

        Args:
            image_base64: Base64编码的图片数据
            image_format: 图片格式 (png/jpeg)
            rules_checklist: 规则检查清单
            reference_images: 参考图片列表 [{"url": data_url, "format": str, "description": str}]
            progress_callback: 进度回调（未使用）
            api_key: 指定的 API Key（用于重试）

        Returns:
            审核结果字典
        """
        try:
            # 如果指定了 api_key，创建临时 LLM 实例
            llm_instance = None
            if api_key:
                from langchain_openai import ChatOpenAI
                llm_instance = ChatOpenAI(
                    model=settings.doubao_model,
                    base_url=settings.openai_api_base,
                    api_key=api_key,
                    temperature=0.1,
                    timeout=180,
                    max_tokens=16384,
                )
            else:
                # 多 Key 轮询：每次调用都获取新 Key
                keys = settings.get_openai_api_keys()
                if len(keys) > 1:
                    # 多 Key 模式，强制切换 Key
                    self._llm = None  # 清除缓存
                    logger.info(f"多 Key 模式: 切换到下一个 Key")
                llm_instance = self.llm

            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 参考图片提示
            reference_hint = REFERENCE_IMAGE_PROMPT if reference_images else ""

            # 构建Prompt
            system_content = COMPRESSED_AUDIT_PROMPT.format(
                rules_checklist=checklist_text,
                reference_hint=reference_hint,
                rule_count=len(rules_checklist or [])
            )
            image_url = f"data:image/{image_format};base64,{image_base64}"

            user_content = []

            # 先添加参考图片
            if reference_images:
                user_content.append({"type": "text", "text": "【标准参考图片】以下是品牌标准Logo，请仔细对比："})
                for i, ref_img in enumerate(reference_images, 1):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": ref_img["url"]}
                    })
                    desc = ref_img.get("description", "标准Logo")
                    user_content.append({
                        "type": "text",
                        "text": f"参考图片{i}：{desc}"
                    })
                user_content.append({"type": "text", "text": "---以上为参考图片，以下为待审核设计稿---"})

            # 添加待审核图片
            user_content.append({"type": "text", "text": "审核这张设计稿，输出JSON格式报告。"})
            user_content.append({"type": "image_url", "image_url": {"url": image_url}})

            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]

            # 调用LLM
            logger.info(f"正在调用API进行审核... (参考图片: {len(reference_images or [])}张)")
            response = llm_instance.invoke(messages)
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
        reference_images: list[dict] = None,
        stream_callback=None,
    ):
        """
        流式审核单张图片

        Args:
            image_base64: Base64编码的图片数据
            image_format: 图片格式 (png/jpeg)
            rules_checklist: 规则检查清单
            reference_images: 参考图片列表 [{"url": data_url, "format": str, "description": str}]
            stream_callback: 流式回调函数，接收每个文本块

        Yields:
            每个文本块
        """
        full_content = ""

        try:
            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 参考图片提示
            reference_hint = REFERENCE_IMAGE_PROMPT if reference_images else ""

            # 构建Prompt
            system_content = COMPRESSED_AUDIT_PROMPT.format(
                rules_checklist=checklist_text,
                reference_hint=reference_hint,
                rule_count=len(rules_checklist or [])
            )
            image_url = f"data:image/{image_format};base64,{image_base64}"

            user_content = []

            # 先添加参考图片
            if reference_images:
                user_content.append({"type": "text", "text": "【标准参考图片】以下是品牌标准Logo，请仔细对比："})
                for i, ref_img in enumerate(reference_images, 1):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": ref_img["url"]}
                    })
                    desc = ref_img.get("description", "标准Logo")
                    user_content.append({
                        "type": "text",
                        "text": f"参考图片{i}：{desc}"
                    })
                user_content.append({"type": "text", "text": "---以上为参考图片，以下为待审核设计稿---"})

            # 添加待审核图片
            user_content.append({"type": "text", "text": "审核这张设计稿，输出JSON格式报告。"})
            user_content.append({"type": "image_url", "image_url": {"url": image_url}})

            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]

            # 调用LLM流式API
            logger.info(f"正在调用API进行流式审核... (参考图片: {len(reference_images or [])}张)")

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
        reference_images: list[dict] = None,
        progress_callback=None,
    ) -> list[dict[str, Any]]:
        """
        单次API调用审核多张图片（合并请求方案）

        Args:
            images: 图片列表，每个元素包含 {"base64": str, "format": str}
            rules_checklist: 规则检查清单
            reference_images: 参考图片列表 [{"url": data_url, "format": str, "description": str}]
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
                    rules_checklist,
                    reference_images
                )
                return [result]

            logger.info(f"批量审核: 单次API调用处理 {len(images)} 张图片")

            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 参考图片提示
            reference_hint = REFERENCE_IMAGE_PROMPT if reference_images else ""

            # 构建Prompt
            system_content = BATCH_AUDIT_PROMPT.format(
                rules_checklist=checklist_text,
                reference_hint=reference_hint,
                rule_count=len(rules_checklist or [])
            )

            # 构建用户消息
            user_content = []

            # 先添加参考图片
            if reference_images:
                user_content.append({"type": "text", "text": "【标准参考图片】以下是品牌标准Logo，请仔细对比："})
                for i, ref_img in enumerate(reference_images, 1):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": ref_img["url"]}
                    })
                    desc = ref_img.get("description", "标准Logo")
                    user_content.append({
                        "type": "text",
                        "text": f"参考图片{i}：{desc}"
                    })
                user_content.append({"type": "text", "text": "---以上为参考图片，以下为待审核设计稿---"})

            # 添加待审核图片
            user_content.append({"type": "text", "text": f"审核以下{len(images)}张设计稿，输出JSON数组格式的报告。每张图片对应一个对象。"})

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
            logger.info(f"正在调用API进行批量审核... (参考图片: {len(reference_images or [])}张)")
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
        reference_images: list[dict] = None,
        stream_callback=None,
        api_key: str = None,
    ) -> list[dict[str, Any]]:
        """
        流式批量审核多张图片（单次API调用，流式输出JSON）

        Args:
            images: 图片列表，每个元素包含 {"base64": str, "format": str}
            rules_checklist: 规则检查清单
            reference_images: 参考图片列表 [{"url": data_url, "format": str, "description": str}]
            stream_callback: 流式回调函数，接收每个文本块
            api_key: 指定的 API Key（用于多批次并行）

        Returns:
            审核结果列表
        """
        try:
            if not images:
                return []

            # 如果指定了 api_key，创建临时 LLM 实例
            llm_instance = None
            if api_key:
                from langchain_openai import ChatOpenAI
                llm_instance = ChatOpenAI(
                    model=settings.doubao_model,
                    base_url=settings.openai_api_base,
                    api_key=api_key,
                    temperature=0.1,
                    timeout=300,
                    max_tokens=16384,
                )
            else:
                llm_instance = self.llm

            if len(images) == 1:
                # 单张图片，使用单图流式接口
                full_content = ""
                for chunk in self.audit_image_stream(
                    images[0]["base64"],
                    images[0].get("format", "jpeg"),
                    rules_checklist,
                    reference_images,
                    stream_callback,
                ):
                    full_content += chunk
                result = self.parse_stream_result(full_content)
                return [result]

            logger.info(f"流式批量审核: 单次API调用处理 {len(images)} 张图片")

            # 格式化规则清单为文本
            checklist_text = self._format_checklist(rules_checklist or [])

            # 参考图片提示
            reference_hint = REFERENCE_IMAGE_PROMPT if reference_images else ""

            # 构建Prompt
            system_content = BATCH_AUDIT_PROMPT.format(
                rules_checklist=checklist_text,
                reference_hint=reference_hint,
                rule_count=len(rules_checklist or [])
            )

            # 构建用户消息
            user_content = []

            # 先添加参考图片
            if reference_images:
                user_content.append({"type": "text", "text": "【标准参考图片】以下是品牌标准Logo，请仔细对比："})
                for i, ref_img in enumerate(reference_images, 1):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": ref_img["url"]}
                    })
                    desc = ref_img.get("description", "标准Logo")
                    user_content.append({
                        "type": "text",
                        "text": f"参考图片{i}：{desc}"
                    })
                user_content.append({"type": "text", "text": "---以上为参考图片，以下为待审核设计稿---"})

            # 添加待审核图片
            user_content.append({"type": "text", "text": f"审核以下{len(images)}张设计稿，输出JSON数组格式的报告。每张图片对应一个对象。"})

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
            logger.info(f"正在调用API进行流式批量审核... (参考图片: {len(reference_images or [])}张)")
            full_content = ""

            for chunk in llm_instance.stream(messages):
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
        """解析LLM响应中的JSON（委托给公共方法）"""
        result = parse_json_response(content)
        return result if isinstance(result, dict) else None

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
        """标准化结果（支持精简格式）"""
        result.setdefault("detection", {})
        result.setdefault("issues", [])

        # 支持精简格式 results 和旧格式 rule_checks
        if "results" not in result and "rule_checks" not in result:
            result["results"] = []
        if "results" in result:
            result.setdefault("rule_checks", result["results"])

        detection = result["detection"]
        detection.setdefault("colors", [])
        detection.setdefault("logo", {"found": False})
        detection.setdefault("texts", [])
        detection.setdefault("fonts", [])
        detection.setdefault("layout", {})
        detection.setdefault("style", {})

        # 根据规则结果计算 status
        # 优先级：FAIL > REVIEW > PASS
        # 全PASS → PASS，有FAIL → FAIL，否则 → REVIEW
        rule_results = result.get("results", []) or result.get("rule_checks", [])

        # 统计各状态数量
        status_map = {"p": "pass", "f": "fail", "r": "review"}
        statuses = []
        for r in rule_results:
            if isinstance(r, dict):
                s = r.get("s") or r.get("status", "")
                s = status_map.get(s, s) if s else "review"
                statuses.append(s)

        fail_count = sum(1 for s in statuses if s == "fail")
        review_count = sum(1 for s in statuses if s == "review")
        pass_count = sum(1 for s in statuses if s == "pass")
        total_count = len(statuses)

        # 根据规则状态判定最终状态
        if fail_count > 0:
            final_status = "fail"
        elif review_count == 0 and pass_count == total_count and total_count > 0:
            final_status = "pass"
        else:
            final_status = "review"

        result["status"] = final_status
        result["summary"] = f"审核完成: PASS:{pass_count}, FAIL:{fail_count}, REVIEW:{review_count}"

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