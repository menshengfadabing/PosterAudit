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
    CheckItem,
    AuditStatus,
    RuleCheckItem,
)
from src.services.llm_service import llm_service
from src.services.rules_context import rules_context

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
        预处理图片 - 智能压缩以节省Token和传输时间

        智能压缩策略：
        1. 分析原图属性（格式、尺寸、大小、质量）
        2. 根据原图情况动态决定压缩策略
        3. 只在确实能减小体积时才压缩
        4. 避免反向压缩（压缩后比原图大）

        Args:
            image_data: 图片数据（bytes或base64字符串）
            image_format: 图片格式

        Returns:
            (base64编码的图片, 格式)
        """
        config = self._compression_config

        # 解码输入
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

        img = Image.open(BytesIO(image_data))
        original_size = img.size
        original_format = image_format.lower()
        if original_format == "jpg":
            original_format = "jpeg"

        # 如果禁用压缩，直接返回
        if not config.get("enabled", True):
            logger.info(f"压缩已禁用，原图: {original_size}, {original_kb:.1f}KB, 格式: {original_format}")
            return base64.b64encode(image_data).decode(), original_format

        # ===== 分析原图属性 =====

        # 检测原图是否为JPEG及其质量估算
        is_original_jpeg = original_format == "jpeg"
        estimated_quality = self._estimate_jpeg_quality(image_data) if is_original_jpeg else None

        # 分析PNG是否适合转换为JPEG
        is_png_with_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        png_to_jpeg_potential = original_format == "png" and not is_png_with_alpha

        logger.info(f"原图分析: {original_size}, {original_kb:.1f}KB, 格式={original_format}, "
                    f"mode={img.mode}, JPEG质量≈{estimated_quality}, 有Alpha={is_png_with_alpha}")

        # ===== 智能决策：是否需要处理 =====

        max_dimension = config.get("max_dimension", 1920)
        max_file_size = config.get("max_file_size", 500_000)
        target_quality = config.get("quality", 75)

        # 决策因子
        needs_resize = max(img.size) > max_dimension
        needs_quality_reduction = False
        needs_format_conversion = False

        # 1. 尺寸决策：只有原图大于max_dimension才需要缩放
        if needs_resize:
            logger.info(f"需要缩放: {max(img.size)} > {max_dimension}")
        else:
            logger.info(f"尺寸合适: {max(img.size)} <= {max_dimension}, 无需缩放")

        # 2. 质量决策：对比原图质量和目标质量
        if is_original_jpeg and estimated_quality:
            if estimated_quality <= target_quality:
                # 原图质量已经低于或等于目标，不需要降低质量
                logger.info(f"质量合适: 原图≈{estimated_quality} <= 目标{target_quality}, 无需降低质量")
            else:
                # 原图质量高于目标，需要降低
                needs_quality_reduction = True
                logger.info(f"需要降质: 原图≈{estimated_quality} > 目标{target_quality}")

        # 3. 格式转换决策：PNG转JPEG可能节省空间
        if png_to_jpeg_potential:
            # PNG无损转JPEG有损，通常能节省空间（除非PNG本身很小）
            needs_format_conversion = True
            logger.info(f"建议转换: PNG无Alpha -> JPEG (可能节省空间)")

        # 4. 文件大小决策：原图是否已满足大小要求
        if original_bytes <= max_file_size and not needs_resize:
            # 原图大小已满足要求且尺寸合适，检查是否还需要处理
            if is_original_jpeg and estimated_quality and estimated_quality <= target_quality:
                # JPEG质量也合适 -> 无需处理，直接返回原图
                logger.info(f"原图已满足所有要求: {original_kb:.1f}KB <= {max_file_size/1024:.1f}KB, "
                            f"尺寸合适, 质量≈{estimated_quality}, 直接返回原图")
                return base64.b64encode(image_data).decode(), original_format
            elif png_to_jpeg_potential and original_kb > 50:
                # PNG较大，转JPEG可能更小，继续处理
                needs_format_conversion = True
            else:
                # 其他情况，原图满足要求
                logger.info(f"原图大小合适: {original_kb:.1f}KB <= {max_file_size/1024:.1f}KB, 尺寸合适, 返回原图")
                return base64.b64encode(image_data).decode(), original_format

        # ===== 执行压缩 =====

        # 如果没有任何处理需求，直接返回原图
        if not needs_resize and not needs_quality_reduction and not needs_format_conversion:
            # 但可能需要检查是否超过大小限制
            if original_bytes <= max_file_size:
                logger.info(f"无需任何处理，直接返回原图")
                return base64.b64encode(image_data).decode(), original_format

        # 转换为RGB模式
        if img.mode in ("RGBA", "P", "LA", "L"):
            if img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
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
            else:
                img = img.convert("RGB")

        # 缩放（仅在需要时）
        if needs_resize:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"图片缩放: {original_size} -> {img.size}")

        # 动态调整压缩质量
        # 如果原图是高质量JPEG，用目标质量压缩；如果原图质量已经较低，保持相近质量
        actual_quality = target_quality
        if is_original_jpeg and estimated_quality and not needs_quality_reduction:
            # 原图质量合适，保持相近质量（略微降低以补偿重编码开销）
            actual_quality = min(estimated_quality, target_quality)
            logger.info(f"保持相近质量: actual_quality={actual_quality}")

        # 压缩为JPEG
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=actual_quality, optimize=True)

        compressed_bytes = len(buffer.getvalue())
        compressed_kb = compressed_bytes / 1024

        # ===== 压缩效果检查 =====

        # 如果压缩后比原图大，且原图满足大小和尺寸要求，返回原图
        if compressed_bytes > original_bytes:
            if original_bytes <= max_file_size and not needs_resize:
                logger.warning(f"压缩效果不佳: {compressed_kb:.1f}KB > {original_kb:.1f}KB, 返回原图")
                return base64.b64encode(image_data).decode(), original_format
            else:
                # 原图超限，即使压缩后更大也得用（通常是尺寸缩放导致）
                logger.warning(f"压缩后变大但原图超限: {compressed_kb:.1f}KB > {original_kb:.1f}KB, "
                               f"原图{original_kb:.1f}KB > {max_file_size/1024:.1f}KB 或尺寸超限")

        # 如果仍然超过大小限制，进一步降低质量
        if compressed_bytes > max_file_size:
            # 计算需要的质量（保守估计）
            new_quality = max(40, int(actual_quality * 0.8 * max_file_size / compressed_bytes))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=new_quality, optimize=True)
            compressed_bytes = len(buffer.getvalue())
            compressed_kb = compressed_bytes / 1024
            logger.info(f"二次压缩: quality={new_quality}, size={compressed_kb:.1f}KB")

            # 再次检查是否比原图大
            if compressed_bytes > original_bytes and original_bytes <= max_file_size:
                logger.warning(f"二次压缩仍比原图大: {compressed_kb:.1f}KB > {original_kb:.1f}KB, 返回原图")
                return base64.b64encode(image_data).decode(), original_format

        # 记录压缩效果
        compression_ratio = (1 - compressed_kb / original_kb) * 100 if original_kb > 0 else 0
        logger.info(f"压缩完成: {original_kb:.1f}KB -> {compressed_kb:.1f}KB "
                    f"(节省{compression_ratio:.1f}%, 质量={actual_quality})")

        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        return image_base64, "jpeg"

    def _estimate_jpeg_quality(self, image_data: bytes) -> int | None:
        """
        估算JPEG图片的质量值

        通过分析JPEG文件的量化表来估算编码时使用的质量参数

        Args:
            image_data: JPEG图片的二进制数据

        Returns:
            估算的质量值（1-100），如果无法估算返回None
        """
        try:
            # PIL没有直接提供质量信息，通过文件大小和尺寸估算
            img = Image.open(BytesIO(image_data))
            width, height = img.size
            file_size = len(image_data)

            # 计算每像素字节数
            pixels = width * height
            bytes_per_pixel = file_size / pixels if pixels > 0 else 0

            # 根据每像素字节数估算质量（经验公式）
            # JPEG质量与压缩率大致对应：
            # quality 90-100: ~2-4 bytes/pixel (高质量)
            # quality 75-85:  ~0.8-2 bytes/pixel (中等)
            # quality 50-70:  ~0.3-0.8 bytes/pixel (低质量)
            # quality <50:    ~0.1-0.3 bytes/pixel (极低)

            if bytes_per_pixel >= 2.5:
                estimated = 95
            elif bytes_per_pixel >= 1.5:
                estimated = 85
            elif bytes_per_pixel >= 0.8:
                estimated = 75
            elif bytes_per_pixel >= 0.5:
                estimated = 60
            elif bytes_per_pixel >= 0.3:
                estimated = 50
            else:
                estimated = 40

            logger.debug(f"JPEG质量估算: {file_size}字节, {width}x{height}, "
                        f"{bytes_per_pixel:.2f}bytes/pixel -> quality≈{estimated}")

            return estimated

        except Exception as e:
            logger.warning(f"JPEG质量估算失败: {e}")
            return None

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

        # 获取品牌规范
        rules_checklist = rules_context.get_rules_checklist(brand_id)
        rules_text = rules_context.get_rules_text(brand_id)  # 用于计算token

        # 获取参考图片
        reference_images = rules_context.get_reference_images_data(brand_id)
        if reference_images:
            logger.info(f"使用 {len(reference_images)} 张参考图片")

        # 计算单次请求可容纳的最大图片数
        if max_images_per_request is None:
            max_images_per_request = llm_service.calculate_max_images(image_sizes, rules_text)

        # 分批处理
        results = []
        batches = [images[i:i + max_images_per_request] for i in range(0, len(images), max_images_per_request)]
        batch_paths = [image_paths[i:i + max_images_per_request] for i in range(0, len(image_paths), max_images_per_request)]

        logger.info(f"分为 {len(batches)} 批次处理")

        # 计算每张图片在总列表中的索引
        path_to_index = {path: i for i, path in enumerate(image_paths)}

        for batch_idx, (batch_images, batch_path_list) in enumerate(zip(batches, batch_paths)):
            batch_start = time.time()
            batch_num = batch_idx + 1
            total_batches = len(batches)

            if progress_callback:
                progress_callback(len(results), total, f"正在审核批次 {batch_num}/{total_batches}...")

            logger.info(f"处理第 {batch_num}/{total_batches} 批，共 {len(batch_images)} 张图片")

            # 调用LLM流式批量审核
            batch_results = llm_service.audit_images_batch_stream(
                images=batch_images,
                rules_checklist=rules_checklist,
                reference_images=reference_images,
                stream_callback=stream_callback,
            )

            batch_time = time.time() - batch_start
            logger.info(f"批次 {batch_num} 完成，耗时: {batch_time:.1f}秒")

            # 检查是否有有效结果（如果全部失败则回退到单图审核）
            has_valid_result = any(
                r.get("score", 0) > 0 or r.get("status") != "fail"
                for r in batch_results
            )

            if not has_valid_result and len(batch_images) > 1:
                logger.warning(f"批次 {batch_num} 合并请求全部失败，回退到单图审核")
                # 回退到单图审核
                for i, (result, path) in enumerate(zip(batch_results, batch_path_list)):
                    try:
                        # 单独审核每张图片
                        single_result = llm_service.audit_image(
                            image_base64=batch_images[i]["base64"],
                            image_format=batch_images[i]["format"],
                            rules_checklist=rules_checklist,
                            reference_images=reference_images,
                        )
                        report = self._build_report(single_result, rules_checklist)
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "success",
                            "report": report
                        }
                        results.append(result_item)
                        # 流式返回，使用正确的索引
                        if result_callback:
                            idx = path_to_index.get(path, len(results) - 1)
                            result_callback(result_item, idx, len(results), total)
                    except Exception as e:
                        logger.error(f"单图审核失败 [{path}]: {e}")
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "error",
                            "error": str(e)
                        }
                        results.append(result_item)
                        if result_callback:
                            idx = path_to_index.get(path, len(results) - 1)
                            result_callback(result_item, idx, len(results), total)
            else:
                # 转换结果格式
                for i, (result, path) in enumerate(zip(batch_results, batch_path_list)):
                    try:
                        report = self._build_report(result, rules_checklist)
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "success",
                            "report": report
                        }
                        results.append(result_item)
                        # 流式返回，使用正确的索引
                        if result_callback:
                            idx = path_to_index.get(path, len(results) - 1)
                            result_callback(result_item, idx, len(results), total)
                    except Exception as e:
                        logger.error(f"结果转换失败 [{path}]: {e}")
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "error",
                            "error": str(e)
                        }
                        results.append(result_item)
                        if result_callback:
                            idx = path_to_index.get(path, len(results) - 1)
                            result_callback(result_item, idx, len(results), total)

            if progress_callback:
                progress_callback(len(results), total, f"已完成 {len(results)}/{total}")

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
            position=logo_data.get("position", ""),
            position_correct=logo_data.get("position_correct"),
            size_percent=logo_data.get("size_percent"),
            size_correct=logo_data.get("size_correct"),
            color_type=logo_data.get("color_type", ""),
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

        # 构建检查项
        checks = {}
        for check_type, items in result.get("checks", {}).items():
            checks[check_type] = [
                CheckItem(
                    code=item.get("code", ""),
                    name=item.get("name", ""),
                    status=item.get("status", "pass"),
                    detail=item.get("detail", ""),
                )
                for item in items
            ]

        # 构建规则检查清单
        rule_checks = self._build_rule_checks(result, rules_checklist)

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

        # 根据规则检查结果修正最终评价
        # 规则：最终评价不能高于规则列表中的最差状态
        original_score = result.get("score", 0)
        original_status = result.get("status", "fail")

        # 找出规则检查中的最差状态
        worst_status = "pass"  # 默认为通过
        status_priority = {"fail": 0, "review": 1, "pass": 2}

        for check in rule_checks:
            check_status = check.status.lower() if check.status else "review"
            if status_priority.get(check_status, 2) < status_priority.get(worst_status, 2):
                worst_status = check_status

        # 根据最差状态限制最终评价
        final_status = original_status
        final_score = original_score

        if worst_status == "fail":
            # 有FAIL规则，最终状态必须为FAIL，分数不超过55
            final_status = "fail"
            final_score = min(original_score, 55)
        elif worst_status == "review":
            # 有REVIEW规则（无FAIL），最终状态必须为REVIEW，分数不超过70
            final_status = "review"
            final_score = min(original_score, 70)

        logger.info(f"评价修正: 原始({original_status}, {original_score}) -> 最终({final_status}, {final_score}), 规则最差状态={worst_status}")

        # 构建报告
        return AuditReport(
            score=final_score,
            status=AuditStatus(final_status),
            detection=detection,
            checks=checks,
            rule_checks=rule_checks,
            issues=issues,
            summary=result.get("summary", ""),
        )

    def _build_rule_checks(self, result: dict, rules_checklist: list[dict] = None) -> list[RuleCheckItem]:
        """构建规则检查清单"""
        rule_checks = []

        # 从 LLM 结果获取 rule_checks
        llm_rule_checks = result.get("rule_checks", [])

        # 如果有规则清单，按清单顺序构建结果
        if rules_checklist:
            # 创建 rule_id -> llm_result 的映射
            llm_results_map = {r.get("rule_id"): r for r in llm_rule_checks}

            for rule in rules_checklist:
                rule_id = rule.get("rule_id", "")
                llm_result = llm_results_map.get(rule_id, {})

                rule_checks.append(RuleCheckItem(
                    rule_id=rule_id,
                    rule_content=rule.get("content", ""),
                    status=llm_result.get("status", "review") if llm_result else "review",
                    reference=rule.get("reference", ""),
                    confidence=llm_result.get("confidence", 0.0) if llm_result else 0.0,
                    detail=llm_result.get("detail", "") if llm_result else "未能获取审核结果",
                ))
        else:
            # 没有规则清单，直接使用 LLM 返回的结果
            for r in llm_rule_checks:
                rule_checks.append(RuleCheckItem(
                    rule_id=r.get("rule_id", ""),
                    rule_content=r.get("rule_content", ""),
                    status=r.get("status", "review"),
                    reference=r.get("reference", ""),
                    confidence=r.get("confidence", 0.0),
                    detail=r.get("detail", ""),
                ))

        return rule_checks


# 全局审核服务实例
audit_service = AuditService()