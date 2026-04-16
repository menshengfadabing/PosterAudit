"""品牌合规审核平台 - 审核服务"""

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image

from src.models.schemas import (
    AuditReport,
    DetectionResult,
    Issue,
    IssueSeverity,
    IssueType,
    LogoInfo,
    ColorInfo,
    FontInfo,
    LayoutInfo,
    StyleScore,
    AuditStatus,
    RuleCheckItem,
)
from src.services.llm_service import llm_service, COMPRESSED_AUDIT_PROMPT, REFERENCE_IMAGE_PROMPT
from src.services.rules_context import rules_context
from src.utils.config import settings

logger = logging.getLogger(__name__)


class AuditService:
    """品牌合规审核服务"""

    SUPPORTED_FORMATS = {"png", "jpeg", "jpg", "gif", "bmp", "webp"}

    # 默认压缩配置
    DEFAULT_COMPRESSION = {
        "max_dimension": 1920,      # 最大边长
        "max_file_size": 500_000,   # 最大文件大小 500KB
        "quality": 75,              # JPEG质量
        "enabled": True,            # 是否启用压缩
    }

    # 压缩预设（智能压缩：只在必要时处理，避免反向压缩）
    COMPRESSION_PRESETS = {
        "high_quality": {
            "max_dimension": 1920,      # 不放大，只缩小超限图片
            "max_file_size": 1_000_000,  # 1MB
            "quality": 85,              # 较高质量
            "enabled": True,
        },
        "balanced": {
            "max_dimension": 1920,      # 标准高清
            "max_file_size": 500_000,    # 500KB
            "quality": 75,              # 平衡质量
            "enabled": True,
        },
        "high_compression": {
            "max_dimension": 1280,      # 适中尺寸
            "max_file_size": 300_000,    # 300KB
            "quality": 60,              # 较低质量
            "enabled": True,
        },
        "no_compression": {
            "max_dimension": 99999,     # 几乎不限制（保持原图尺寸）
            "max_file_size": 99_000_000,  # 几乎不限制（保持原图大小）
            "quality": 100,             # 最高质量
            "enabled": False,           # 禁用处理
        },
    }

    def __init__(self):
        self._compression_config = self.DEFAULT_COMPRESSION.copy()

    @staticmethod
    def _safe_str(value: object, default: str = "") -> str:
        """将任意值安全转换为字符串，避免 None 导致 Pydantic 校验错误。"""
        if value is None:
            return default
        if isinstance(value, str):
            return value
        return str(value)

    def set_compression_config(self, config: dict):
        """设置压缩配置"""
        self._compression_config.update(config)
        logger.info(f"压缩配置已更新: {self._compression_config}")

    def set_compression_preset(self, preset_name: str):
        """使用预设压缩配置"""
        if preset_name in self.COMPRESSION_PRESETS:
            self._compression_config = self.COMPRESSION_PRESETS[preset_name].copy()
            logger.info(f"使用压缩预设: {preset_name}")
        else:
            logger.warning(f"未知的压缩预设: {preset_name}")

    def preprocess_image(self, image_data: bytes | str, image_format: str = "png") -> tuple[str, str]:
        """
        预处理图片 - 压缩以节省 Token 和传输时间

        简化策略：
        1. 控制尺寸：限制最大边长
        2. 控制大小：限制文件大小
        3. 格式转换：统一输出为 JPEG

        Args:
            image_data: 图片数据（bytes或base64字符串）
            image_format: 图片格式

        Returns:
            (base64编码的图片, 格式)
        """
        config = self._compression_config

        # 1. 解码输入
        if isinstance(image_data, str):
            if image_data.startswith("data:"):
                import re
                match = re.match(r"data:image/(\w+);base64,(.+)", image_data)
                if match:
                    image_format = match.group(1)
                    image_data = base64.b64decode(match.group(2))
                else:
                    image_data = base64.b64decode(image_data)
            else:
                image_data = base64.b64decode(image_data)

        original_bytes = len(image_data)
        original_kb = original_bytes / 1024

        # 打开图片
        img = Image.open(BytesIO(image_data))
        original_size = img.size

        # 标准化格式名
        image_format = image_format.lower()
        if image_format == "jpg":
            image_format = "jpeg"

        # 2. 如果禁用压缩，直接返回
        if not config.get("enabled", True):
            logger.debug(f"压缩已禁用: {original_size}, {original_kb:.1f}KB")
            return base64.b64encode(image_data).decode(), image_format

        max_dimension = config.get("max_dimension", 1920)
        max_file_size = config.get("max_file_size", 500_000)
        quality = config.get("quality", 75)

        # 3. 检查是否需要处理
        needs_resize = max(img.size) > max_dimension
        needs_compress = original_bytes > max_file_size

        if not needs_resize and not needs_compress:
            logger.debug(f"无需处理: {original_size}, {original_kb:.1f}KB")
            return base64.b64encode(image_data).decode(), image_format

        logger.info(f"预处理: {original_size}, {original_kb:.1f}KB -> "
                    f"max_dim={max_dimension}, max_size={max_file_size/1024:.0f}KB")

        # 4. 转换为 RGB 模式（去除 Alpha 通道）
        if img.mode in ("RGBA", "LA"):
            # 白色背景合成
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode == "P":
            if "transparency" in img.info:
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # 5. 缩放（仅在需要时）
        if needs_resize:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(f"缩放: {original_size} -> {img.size}")

        # 6. 压缩为 JPEG
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)

        # 如果仍然太大，降低质量再压缩
        if len(buffer.getvalue()) > max_file_size:
            lower_quality = max(40, int(quality * 0.7))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=lower_quality, optimize=True)
            logger.debug(f"二次压缩: quality={lower_quality}")

        compressed_kb = len(buffer.getvalue()) / 1024
        compression_ratio = (1 - len(buffer.getvalue()) / original_bytes) * 100 if original_bytes > 0 else 0

        logger.info(f"压缩完成: {original_kb:.1f}KB -> {compressed_kb:.1f}KB (节省{compression_ratio:.0f}%)")

        return base64.b64encode(buffer.getvalue()).decode(), "jpeg"

    def audit_file(self, file_path: str | Path, brand_id: str | None = None) -> AuditReport:
        """审核本地文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, "rb") as f:
            image_data = f.read()

        image_format = file_path.suffix.lstrip(".").lower()
        if image_format == "jpg":
            image_format = "jpeg"

        image_base64 = base64.b64encode(image_data).decode()

        return self.audit(image_base64, image_format, brand_id)

    def audit(
        self,
        image_base64: str,
        image_format: str = "png",
        brand_id: str | None = None,
        progress_callback=None,
    ) -> AuditReport:
        """执行审核"""
        try:
            logger.info("预处理图片...")
            image_base64, image_format = self.preprocess_image(image_base64, image_format)

            # 获取品牌规范规则清单
            rules_checklist = rules_context.get_rules_checklist(brand_id)

            # 获取参考图片
            reference_images = rules_context.get_reference_images_data(brand_id)
            if reference_images:
                logger.info(f"使用 {len(reference_images)} 张参考图片")

            logger.info("调用LLM审核...")
            result = llm_service.audit_image(
                image_base64=image_base64,
                image_format=image_format,
                rules_checklist=rules_checklist,
                reference_images=reference_images,
                progress_callback=progress_callback,
            )

            return self._build_report(result, rules_checklist)

        except Exception as e:
            logger.error(f"审核失败: {e}", exc_info=True)
            raise

    def batch_audit_merged(
        self,
        image_paths: list,
        brand_id: str | None = None,
        max_images_per_request: int = None,
        progress_callback=None,
        stream_callback=None,
        result_callback=None,
        preconditions: Optional[dict] = None,
    ) -> list:
        """
        合并请求批量审核（单次API调用处理多张图片，流式输出JSON）

        Args:
            image_paths: 图片路径列表
            brand_id: 品牌ID
            max_images_per_request: 单次请求最大图片数（None则自动计算）
            progress_callback: 进度回调函数 (completed, total, message)
            stream_callback: 流式文本回调函数 (text_chunk) - 实时显示JSON
            result_callback: 单条结果回调函数 (result, index, completed, total)

        Returns:
            审核结果列表
        """
        import time

        total = len(image_paths)
        start_time = time.time()

        logger.info(f"开始合并请求批量审核: {total}张图片")

        # 预处理所有图片，并流式更新进度
        images = []
        image_sizes = []
        preprocessed_count = 0

        for i, path in enumerate(image_paths):
            file_path = Path(path)
            with open(file_path, "rb") as f:
                image_data = f.read()

            # 预处理图片
            image_base64, image_format = self.preprocess_image(image_data, file_path.suffix.lstrip(".").lower())
            images.append({"base64": image_base64, "format": image_format})

            # 记录原始尺寸用于计算窗口容量
            try:
                img = Image.open(BytesIO(image_data))
                image_sizes.append(img.size)
            except:
                image_sizes.append((1920, 1080))  # 默认尺寸

            # 流式更新预处理进度
            preprocessed_count += 1
            if progress_callback:
                progress_callback(preprocessed_count, total, f"预处理图片 {preprocessed_count}/{total}")

        # 获取品牌规范（传入前置条件进行规则过滤）
        rules_checklist = rules_context.get_rules_checklist(brand_id, preconditions=preconditions)
        rules_text = rules_context.get_rules_text(brand_id)  # 用于计算token

        # 获取参考图片
        reference_images = rules_context.get_reference_images_data(brand_id)
        if reference_images:
            logger.info(f"使用 {len(reference_images)} 张参考图片")

        # 获取 API Keys 数量
        api_keys = settings.get_mllm_api_keys()
        if not api_keys:
            api_keys = [settings.mllm_api_key] if settings.mllm_api_key else []
        key_count = len(api_keys) if api_keys else 1

        # ── 同系列物料合并审核策略 ──────────────────────────────────────────
        # 当前置条件中 is_same_series_material=yes 时：
        #   1. 必须采用合并审核，不再采用默认的多 Key 轮询 + 动态批次大小
        #   2. 单批次最小 2 张，最大 5 张（避免上下文窗口溢出）
        #   3. 固定使用单个 API Key，禁用多 Key 轮询
        is_same_series = (preconditions or {}).get("is_same_series_material") == "yes"
        if is_same_series:
            # 单批次 2~5 张，超出则分多批但每批不超过 5 张
            max_images_per_request = min(max(2, total), 5)
            # 只使用第一个 API Key，禁用多 Key 轮询
            if api_keys and len(api_keys) > 1:
                api_keys = [api_keys[0]]
                key_count = 1
            logger.info(f"同系列物料合并审核: {total} 张，每批最多 5 张，共 {max(1, (total + max_images_per_request - 1) // max_images_per_request)} 批，使用单个 API Key")

        # 动态计算最优批次大小
        # 目标：最小化总审核时间
        # 关键因素：每轮的最大批次大小（各Key并行时的最长批次）
        # 假设每张图片处理时间约40秒
        TIME_PER_IMAGE = 40

        if max_images_per_request is None:
            # 先计算 token 限制下的最大批次大小
            token_limit = llm_service.calculate_max_images(image_sizes, rules_text)

            # 批次大小范围：最小3张，最大不超过token限制且不超过5张
            min_batch = 3
            max_batch = min(token_limit, 5)

            best_batch_size = min_batch
            best_time = float('inf')

            for batch_size in range(min_batch, max_batch + 1):
                # 计算各批次的大小
                batch_sizes = []
                remaining = total
                while remaining > 0:
                    batch_sizes.append(min(batch_size, remaining))
                    remaining -= batch_size

                batch_count = len(batch_sizes)

                # 计算每轮的时间（Key并行，每轮取最大批次）
                rounds = (batch_count + key_count - 1) // key_count  # ceil(batch_count/key_count)
                total_time = 0

                for r in range(rounds):
                    # 这一轮处理的批次索引范围
                    start_idx = r * key_count
                    end_idx = min(start_idx + key_count, batch_count)
                    # 这一轮各批次的大小
                    round_batch_sizes = batch_sizes[start_idx:end_idx]
                    # 这一轮的时间取决于最大的批次
                    max_batch_in_round = max(round_batch_sizes)
                    round_time = max_batch_in_round * TIME_PER_IMAGE
                    total_time += round_time

                logger.debug(f"批次大小 {batch_size}: 批次分布={batch_sizes}, 轮数={rounds}, 总时间={total_time}s")

                if total_time < best_time:
                    best_time = total_time
                    best_batch_size = batch_size

            max_images_per_request = best_batch_size
            logger.info(f"动态计算批次大小: {max_images_per_request}张/批 (Key数={key_count}, 总图片={total}, 预估时间={best_time}s)")

        # 分批处理
        results = []
        batches = [images[i:i + max_images_per_request] for i in range(0, len(images), max_images_per_request)]
        batch_paths = [image_paths[i:i + max_images_per_request] for i in range(0, len(image_paths), max_images_per_request)]

        logger.info(f"分为 {len(batches)} 批次处理（并行执行）")

        # 计算每张图片在总列表中的索引
        path_to_index = {path: i for i, path in enumerate(image_paths)}

        def process_batch(args: tuple) -> tuple:
            """处理单个批次"""
            batch_idx, batch_images, batch_path_list = args
            batch_num = batch_idx + 1
            total_batches = len(batches)
            batch_start = time.time()

            # 选择 API Key（轮询）
            api_key = None
            if api_keys:
                api_key = api_keys[batch_idx % len(api_keys)]
                logger.info(f"批次 {batch_num}: 使用 API Key #{batch_idx % len(api_keys) + 1}")

            logger.info(f"处理第 {batch_num}/{total_batches} 批，共 {len(batch_images)} 张图片")

            try:
                # 调用 LLM 批量审核
                batch_results = llm_service.audit_images_batch_stream(
                    images=batch_images,
                    rules_checklist=rules_checklist,
                    reference_images=reference_images,
                    stream_callback=None,  # 并行时不支持流式
                    api_key=api_key,  # 指定 API Key
                )

                batch_time = time.time() - batch_start
                logger.info(f"批次 {batch_num} 完成，耗时: {batch_time:.1f}秒")

                # 检查是否有有效结果（有规则检查结果即为有效，与状态无关）
                def has_valid_rules(result):
                    """检查结果是否包含规则检查结果"""
                    rule_checks = result.get("results", []) or result.get("rule_checks", [])
                    return len(rule_checks) > 0

                has_valid_result = any(has_valid_rules(r) for r in batch_results)

                if not has_valid_result and len(batch_images) > 1:
                    logger.warning(f"批次 {batch_num} 合并请求无有效结果，回退到并发审核")
                    # 回退处理
                    fallback_results = self._fallback_concurrent(
                        batch_images=batch_images,
                        batch_path_list=batch_path_list,
                        brand_id=brand_id,
                        rules_checklist=rules_checklist,
                        reference_images=reference_images,
                        max_concurrent=min(len(batch_images), 5)
                    )
                    return batch_idx, fallback_results

                # 转换结果格式，并检测不完整结果
                batch_result_items = []
                retry_items = []  # 需要重试的图片

                for i, (result, path) in enumerate(zip(batch_results, batch_path_list)):
                    try:
                        # 检查结果是否不完整
                        if self._is_result_incomplete(result, rules_checklist):
                            logger.warning(f"图片 {Path(path).name} 审核结果不完整，将尝试单独重审")
                            retry_items.append((i, path, batch_images[i]))
                            continue

                        report = self._build_report(result, rules_checklist)
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "success",
                            "report": report
                        }
                        batch_result_items.append(result_item)
                    except Exception as e:
                        logger.error(f"结果转换失败 [{path}]: {e}")
                        batch_result_items.append({
                            "file_name": Path(path).name,
                            "status": "error",
                            "error": str(e)
                        })

                # 对不完整结果进行单独重审
                if retry_items:
                    logger.info(f"对 {len(retry_items)} 张不完整结果的图片进行单独重审...")
                    for orig_idx, path, img_data in retry_items:
                        try:
                            # 选择不同的 API Key 重试
                            retry_key = api_keys[(batch_idx + 1) % len(api_keys)] if api_keys else None

                            single_result = llm_service.audit_image(
                                image_base64=img_data["base64"],
                                image_format=img_data.get("format", "jpeg"),
                                rules_checklist=rules_checklist,
                                reference_images=reference_images,
                                api_key=retry_key,
                            )
                            report = self._build_report(single_result, rules_checklist)
                            batch_result_items.append({
                                "file_name": Path(path).name,
                                "status": "success",
                                "report": report
                            })
                            logger.info(f"单独重审完成: {Path(path).name}")
                        except Exception as e:
                            logger.error(f"单独重审失败 [{path}]: {e}")
                            batch_result_items.append({
                                "file_name": Path(path).name,
                                "status": "error",
                                "error": f"重审失败: {str(e)}"
                            })

                return batch_idx, batch_result_items

            except Exception as e:
                logger.error(f"批次 {batch_num} 处理失败: {e}")
                # 返回错误结果
                error_results = []
                for path in batch_path_list:
                    error_results.append({
                        "file_name": Path(path).name,
                        "status": "error",
                        "error": str(e)
                    })
                return batch_idx, error_results

        # 并行处理所有批次
        from concurrent.futures import ThreadPoolExecutor, as_completed

        batch_results_map = {}  # batch_idx -> results

        # 计算并发数：批次数量和 Key 数量的较小值
        max_concurrent = min(len(batches), len(api_keys)) if api_keys else len(batches)
        logger.info(f"并发处理 {len(batches)} 个批次，最大并发数: {max_concurrent}")

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(process_batch, (i, batch, paths)): i
                for i, (batch, paths) in enumerate(zip(batches, batch_paths))
            }

            completed = 0
            for future in as_completed(futures):
                batch_idx, batch_results = future.result()
                batch_results_map[batch_idx] = batch_results
                completed += 1

                if progress_callback:
                    # 计算已完成图片数
                    completed_images = sum(
                        len(batch_results_map.get(i, []))
                        for i in range(completed)
                    )
                    progress_callback(completed_images, total, f"已完成 {completed}/{len(batches)} 批次")

        # 按批次顺序合并结果
        for batch_idx in range(len(batches)):
            batch_results = batch_results_map.get(batch_idx, [])
            batch_paths_list = batch_paths[batch_idx]

            for i, result_item in enumerate(batch_results):
                results.append(result_item)
                if result_callback and i < len(batch_paths_list):
                    # 使用原始路径获取索引
                    idx = path_to_index.get(batch_paths_list[i], len(results) - 1)
                    result_callback(result_item, idx, len(results), total)

        total_time = time.time() - start_time
        logger.info(f"合并请求批量审核完成: 总耗时: {total_time:.1f}秒, 平均每张: {total_time/total:.1f}秒")

        return results

    def _build_report(self, result: dict, rules_checklist: list[dict] = None) -> AuditReport:
        """从LLM结果构建审核报告"""
        detection_data = result.get("detection", {})

        # 构建颜色列表
        colors = []
        for c in detection_data.get("colors", []):
            colors.append(ColorInfo(
                hex=c.get("hex", ""),
                name=c.get("name", ""),
                percent=c.get("percent", 0),
            ))

        # 构建Logo信息
        logo_data = detection_data.get("logo", {})
        logo = LogoInfo(
            found=logo_data.get("found", False),
            position=self._safe_str(logo_data.get("position"), ""),
            position_correct=logo_data.get("position_correct"),
            size_percent=logo_data.get("size_percent"),
            size_correct=logo_data.get("size_correct"),
            color_type=self._safe_str(logo_data.get("color_type"), ""),
            color_correct=logo_data.get("color_correct"),
            safe_margin_ok=logo_data.get("safe_margin_ok"),
            deformed=logo_data.get("deformed"),
        )

        # 构建字体列表
        fonts = []
        for f in detection_data.get("fonts", []):
            fonts.append(FontInfo(
                text=f.get("text", ""),
                font_family=f.get("font_family", ""),
                font_size=f.get("font_size", ""),
                font_weight=f.get("font_weight", ""),
                font_style=f.get("font_style", ""),
                is_forbidden=f.get("is_forbidden") if f.get("is_forbidden") is not None else False,
            ))

        # 构建布局信息
        layout_data = detection_data.get("layout", {})
        layout = LayoutInfo(
            has_clear_focus=layout_data.get("has_clear_focus"),
            text_on_subject=layout_data.get("text_on_subject"),
            contrast_sufficient=layout_data.get("contrast_sufficient"),
            alignment_correct=layout_data.get("alignment_correct"),
        )

        # 构建风格评分
        style = {}
        for dim in ["sunshine", "health", "professional", "ecology"]:
            dim_data = detection_data.get("style", {}).get(dim, {})
            style[dim] = StyleScore(
                score=dim_data.get("score", 7),
                issues=dim_data.get("issues", []),
            )

        detection = DetectionResult(
            colors=colors,
            logo=logo,
            texts=detection_data.get("texts", []),
            fonts=fonts,
            layout=layout,
            style=style,
        )

        # 构建规则检查清单
        rule_checks = self._build_rule_checks(result, rules_checklist)
        if rules_checklist and not rule_checks:
            raise ValueError("LLM 未返回有效规则检查项")

        # 构建问题列表
        issues = []
        for issue in result.get("issues", []):
            try:
                issues.append(Issue(
                    type=IssueType(issue.get("type", "layout")),
                    severity=IssueSeverity(issue.get("severity", "minor")),
                    code=issue.get("code", ""),
                    description=issue.get("description", ""),
                    suggestion=issue.get("suggestion", ""),
                    action=issue.get("action", ""),
                ))
            except ValueError:
                pass

        # 根据规则检查结果确定最终评价
        # 优先级：FAIL > REVIEW > PASS
        # 全PASS → PASS，有FAIL → FAIL，否则 → REVIEW

        # 统计规则状态
        fail_count = sum(1 for c in rule_checks if c.status.lower() == "fail")
        review_count = sum(1 for c in rule_checks if c.status.lower() == "review")
        pass_count = sum(1 for c in rule_checks if c.status.lower() == "pass")
        total_count = len(rule_checks)

        # 根据规则状态判定最终状态
        if fail_count > 0:
            final_status = "fail"
        elif review_count == 0 and pass_count == total_count and total_count > 0:
            final_status = "pass"
        else:
            final_status = "review"

        logger.info(f"最终评价: {final_status}, PASS:{pass_count}, FAIL:{fail_count}, REVIEW:{review_count}")

        # 构建报告
        return AuditReport(
            status=AuditStatus(final_status),
            detection=detection,
            rule_checks=rule_checks,
            issues=issues,
            summary=result.get("summary", ""),
        )

    def _build_rule_checks(self, result: dict, rules_checklist: list[dict] = None) -> list[RuleCheckItem]:
        """构建规则检查清单（从精简格式转换）"""
        rule_checks = []

        # 从 LLM 结果获取 results（精简格式）
        llm_results = result.get("results", [])

        # 兼容旧格式 rule_checks
        if not llm_results:
            llm_results = result.get("rule_checks", [])

        # 如果有规则清单，按清单顺序构建结果
        if rules_checklist:
            # 创建 rule_id -> llm_result 的映射
            llm_results_map = {r.get("id") or r.get("rule_id"): r for r in llm_results}

            # 检测输出不完整的情况
            missing_rules = []
            for rule in rules_checklist:
                rule_id = rule.get("rule_id", "")
                if rule_id not in llm_results_map:
                    missing_rules.append(rule_id)

            if missing_rules:
                logger.warning(f"LLM 输出不完整，缺少 {len(missing_rules)} 条规则结果")

            for rule in rules_checklist:
                rule_id = rule.get("rule_id", "")
                llm_result = llm_results_map.get(rule_id, {})

                # 解析状态（支持精简格式 s 和旧格式 status）
                status_raw = llm_result.get("s") or llm_result.get("status", "")
                # 精简格式转换: p->pass, f->fail, r->review
                status_map = {"p": "pass", "f": "fail", "r": "review"}
                status = status_map.get(status_raw, status_raw) if status_raw else "review"

                # 解析置信度
                confidence = llm_result.get("c") or llm_result.get("confidence", 0.0) or 0.0

                # 置信度门控：低置信度的 pass/fail 结论降级为 review
                # 避免模型"猜测"的结论被当作确定结论影响最终评级
                CONFIDENCE_THRESHOLD = 0.5
                if confidence < CONFIDENCE_THRESHOLD and status in ("pass", "fail"):
                    logger.debug(
                        f"{rule_id} 置信度过低({confidence:.2f})，"
                        f"状态从 {status} 降级为 review"
                    )
                    status = "review"

                rule_checks.append(RuleCheckItem(
                    rule_id=rule_id,
                    rule_content=rule.get("content", ""),
                    status=status,
                    reference=rule.get("reference", ""),
                    confidence=confidence,
                    detail="",  # 精简格式不再输出 detail
                ))
        else:
            # 没有规则清单，直接使用 LLM 返回的结果
            for r in llm_results:
                status_raw = r.get("s") or r.get("status", "review")
                status_map = {"p": "pass", "f": "fail", "r": "review"}
                status = status_map.get(status_raw, status_raw) if status_raw else "review"

                rule_checks.append(RuleCheckItem(
                    rule_id=r.get("id") or r.get("rule_id", ""),
                    rule_content=r.get("rule_content", ""),
                    status=status,
                    reference=r.get("reference", ""),
                    confidence=r.get("c") or r.get("confidence", 0.0) or 0.0,
                    detail=r.get("d") or r.get("detail", ""),
                ))

        # 按状态排序：FAIL -> REVIEW -> PASS（红黄绿）
        status_order = {"fail": 0, "review": 1, "pass": 2}
        rule_checks.sort(key=lambda x: status_order.get(x.status, 1))

        return rule_checks

    def _is_result_incomplete(self, result: dict, rules_checklist: list[dict] = None) -> bool:
        """检查审核结果是否不完整"""
        if not rules_checklist:
            return False

        llm_results = result.get("results", []) or result.get("rule_checks", [])
        llm_results_map = {r.get("id") or r.get("rule_id"): r for r in llm_results}

        # 计算缺失比例
        missing_count = sum(1 for r in rules_checklist if r.get("rule_id") not in llm_results_map)
        total_count = len(rules_checklist)

        # 超过 50% 缺失视为不完整
        if total_count > 0 and missing_count / total_count > 0.5:
            logger.warning(f"审核结果不完整: {missing_count}/{total_count} 条规则缺失")
            return True

        return False

    def _fallback_concurrent(
        self,
        batch_images: list[dict],
        batch_path_list: list[str],
        brand_id: str | None = None,
        rules_checklist: list[dict] = None,
        reference_images: list[dict] = None,
        max_concurrent: int = 5,
    ) -> list[dict]:
        """
        合并审核失败时的并发回退方法

        使用已预处理的图片数据，直接并发调用 API

        Args:
            batch_images: 已预处理的图片数据 [{"base64": ..., "format": ...}, ...]
            batch_path_list: 图片路径列表
            brand_id: 品牌ID
            rules_checklist: 规则清单
            reference_images: 参考图片
            max_concurrent: 最大并发数

        Returns:
            审核结果列表
        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(batch_images)
        start_time = time.time()
        results = [None] * total

        logger.info(f"并发回退审核: {total}张图片, 最大并发数={max_concurrent}")

        def audit_single(args: tuple) -> tuple:
            """审核单张图片（使用已预处理数据）"""
            idx, image_data, path = args
            file_path = Path(path)

            try:
                # 直接使用已预处理的数据
                result = llm_service.audit_image(
                    image_base64=image_data["base64"],
                    image_format=image_data["format"],
                    rules_checklist=rules_checklist,
                    reference_images=reference_images,
                )

                report = self._build_report(result, rules_checklist)

                return idx, {
                    "file_name": file_path.name,
                    "status": "success",
                    "report": report,
                }

            except Exception as e:
                logger.error(f"并发回退审核失败 [{file_path.name}]: {e}")
                return idx, {
                    "file_name": file_path.name,
                    "status": "error",
                    "error": str(e),
                }

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {
                executor.submit(audit_single, (i, img, path)): i
                for i, (img, path) in enumerate(zip(batch_images, batch_path_list))
            }

            for future in as_completed(futures):
                idx, result = future.result()
                results[idx] = result

        total_time = time.time() - start_time
        logger.info(f"并发回退审核完成: 耗时 {total_time:.1f}秒")

        return results

    def batch_audit_concurrent(
        self,
        image_paths: list,
        brand_id: str | None = None,
        max_concurrent: int = 5,
        progress_callback=None,
        result_callback=None,
    ) -> list:
        """
        并发批量审核 - 多线程并行 API 调用

        与 batch_audit_merged() 的区别：
        - merged: 单次 API 调用处理多图，LLM 串行处理，节省 API 调用次数
        - concurrent: 多个并行 API 调用，真正的并行处理，速度更快

        Args:
            image_paths: 图片路径列表
            brand_id: 品牌ID
            max_concurrent: 最大并发数（默认5）
            progress_callback: 进度回调函数 (completed, total, message)
            result_callback: 单条结果回调函数 (result, index, completed, total)

        Returns:
            审核结果列表，每个元素包含:
            - file_name: 文件名
            - status: "success" 或 "error"
            - report: AuditReport 对象（成功时）
            - error: 错误信息（失败时）
        """
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        total = len(image_paths)
        start_time = time.time()
        results = [None] * total  # 预分配，保持顺序

        logger.info(f"开始并发批量审核: {total}张图片, 最大并发数={max_concurrent}")

        # 获取品牌规范（提前获取，避免每个线程重复获取）
        rules_checklist = rules_context.get_rules_checklist(brand_id)
        reference_images = rules_context.get_reference_images_data(brand_id)
        if reference_images:
            logger.info(f"使用 {len(reference_images)} 张参考图片")

        def audit_single(args: tuple) -> tuple:
            """审核单张图片（每个线程使用不同 Key）"""
            idx, path = args
            file_path = Path(path)

            try:
                # 读取图片
                with open(file_path, "rb") as f:
                    image_data = f.read()

                # 预处理图片
                image_base64, image_format = self.preprocess_image(
                    image_data, file_path.suffix.lstrip(".").lower()
                )

                # 获取 API Key（多 Key 轮询）
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import HumanMessage, SystemMessage

                keys = settings.get_mllm_api_keys()
                if keys:
                    # 轮询获取 Key
                    key_index = idx % len(keys)
                    api_key = keys[key_index]
                    logger.info(f"[{file_path.name}] 使用 Key #{key_index + 1}")
                else:
                    api_key = settings.mllm_api_key
                    logger.warning(f"[{file_path.name}] 无多 Key 配置，使用默认 Key")

                # 创建线程专属的 LLM 实例
                thread_llm = ChatOpenAI(
                    model=settings.mllm_model,
                    base_url=settings.mllm_api_base,
                    api_key=api_key,
                    temperature=0,
                    timeout=180,
                    max_tokens=16384,
                )

                # 构建审核请求
                checklist_text = llm_service._format_checklist(rules_checklist or [])
                reference_hint = REFERENCE_IMAGE_PROMPT if reference_images else ""
                system_content = COMPRESSED_AUDIT_PROMPT.format(
                    rules_checklist=checklist_text,
                    reference_hint=reference_hint
                )

                image_url = f"data:image/{image_format};base64,{image_base64}"
                user_content = [{"type": "text", "text": "审核这张设计稿，输出JSON格式报告。"}]
                user_content.append({"type": "image_url", "image_url": {"url": image_url}})

                messages = [
                    SystemMessage(content=system_content),
                    HumanMessage(content=user_content),
                ]

                # 调用 LLM
                response = thread_llm.invoke(messages)
                content = response.content

                # 解析结果
                result = llm_service._parse_json_response(content)

                # 构建报告
                report = self._build_report(result, rules_checklist)

                return idx, {
                    "file_name": file_path.name,
                    "status": "success",
                    "report": report,
                }

            except Exception as e:
                logger.error(f"审核失败 [{file_path.name}]: {e}")
                return idx, {
                    "file_name": file_path.name,
                    "status": "error",
                    "error": str(e),
                }

        # 使用线程池并发执行
        completed = 0

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # 提交所有任务
            futures = {
                executor.submit(audit_single, (i, p)): i
                for i, p in enumerate(image_paths)
            }

            # 按完成顺序收集结果
            for future in as_completed(futures):
                idx, result = future.result()
                results[idx] = result
                completed += 1

                # 回调通知
                if progress_callback:
                    progress_callback(completed, total, f"已完成 {completed}/{total}")

                if result_callback:
                    result_callback(result, idx, completed, total)

        total_time = time.time() - start_time
        avg_time = total_time / total if total > 0 else 0
        logger.info(f"并发批量审核完成: 总耗时 {total_time:.1f}秒, 平均每张 {avg_time:.1f}秒")

        return results


# 全局审核服务实例
audit_service = AuditService()
