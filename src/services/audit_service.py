"""品牌合规审核平台 - 审核服务"""

import base64
import logging
from io import BytesIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    # 压缩预设
    COMPRESSION_PRESETS = {
        "high_quality": {
            "max_dimension": 2560,
            "max_file_size": 1_000_000,  # 1MB
            "quality": 90,
            "enabled": True,
        },
        "balanced": {
            "max_dimension": 1920,
            "max_file_size": 500_000,    # 500KB
            "quality": 75,
            "enabled": True,
        },
        "high_compression": {
            "max_dimension": 1280,
            "max_file_size": 300_000,    # 300KB
            "quality": 60,
            "enabled": True,
        },
        "no_compression": {
            "max_dimension": 4096,
            "max_file_size": 10_000_000,  # 10MB
            "quality": 95,
            "enabled": False,
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

        img = Image.open(BytesIO(image_data))
        original_size = img.size
        original_kb = len(image_data) / 1024

        # 如果禁用压缩，直接返回
        if not config.get("enabled", True):
            logger.info(f"压缩已禁用，原图大小: {original_kb:.1f}KB")
            return base64.b64encode(image_data).decode(), image_format

        # 转换为RGB模式（统一处理）
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

        # 智能缩放
        max_dimension = config.get("max_dimension", 1920)
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"图片缩放: {original_size} -> {img.size}")

        # 压缩为JPEG格式
        quality = config.get("quality", 75)
        max_file_size = config.get("max_file_size", 500_000)

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)

        # 检查文件大小，如果过大则进一步压缩
        file_size = len(buffer.getvalue())
        if file_size > max_file_size:
            # 计算需要的质量
            new_quality = max(50, int(quality * max_file_size / file_size))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=new_quality, optimize=True)
            logger.info(f"图片进一步压缩: quality={new_quality}, size={len(buffer.getvalue())}")

        image_base64 = base64.b64encode(buffer.getvalue()).decode()

        # 记录压缩效果
        compressed_kb = len(buffer.getvalue()) / 1024
        compression_ratio = (1 - compressed_kb / original_kb) * 100 if original_kb > 0 else 0
        logger.info(f"图片压缩完成: {original_kb:.1f}KB -> {compressed_kb:.1f}KB (节省{compression_ratio:.1f}%)")

        return image_base64, "jpeg"

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

            logger.info("调用LLM审核...")
            result = llm_service.audit_image(
                image_base64=image_base64,
                image_format=image_format,
                rules_checklist=rules_checklist,
                progress_callback=progress_callback,
            )

            return self._build_report(result, rules_checklist)

        except Exception as e:
            logger.error(f"审核失败: {e}", exc_info=True)
            raise

    def batch_audit_concurrent(
        self,
        image_paths: list,
        brand_id: str | None = None,
        max_concurrent: int = 5,
        progress_callback=None,
        result_callback=None,
    ) -> list:
        """
        并发批量审核（方案A：多个独立API请求）

        Args:
            image_paths: 图片路径列表
            brand_id: 品牌ID
            max_concurrent: 最大并发数
            progress_callback: 进度回调函数 (completed, total, message)
            result_callback: 单条结果回调函数 (result) - 用于流式返回

        Returns:
            审核结果列表
        """
        import time

        results = [None] * len(image_paths)
        total = len(image_paths)
        start_time = time.time()

        logger.info(f"开始并发批量审核: {total}张图片, 最大并发数: {max_concurrent}")

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            submit_time = time.time()
            future_to_index = {
                executor.submit(self.audit_file, path, brand_id): i
                for i, path in enumerate(image_paths)
            }
            logger.info(f"所有任务已提交，耗时: {time.time() - submit_time:.2f}秒")

            completed = 0
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    report = future.result()
                    results[index] = {
                        "file_name": Path(image_paths[index]).name,
                        "status": "success",
                        "report": report
                    }
                except Exception as e:
                    logger.error(f"审核失败 [{image_paths[index]}]: {e}")
                    results[index] = {
                        "file_name": Path(image_paths[index]).name,
                        "status": "error",
                        "error": str(e)
                    }

                completed += 1
                elapsed = time.time() - start_time
                logger.info(f"进度: {completed}/{total}, 已耗时: {elapsed:.1f}秒")

                # 流式返回单条结果
                if result_callback:
                    result_callback(results[index], index, completed, total)

                if progress_callback:
                    progress_callback(completed, total, f"已完成 {completed}/{total}")

        total_time = time.time() - start_time
        avg_time = total_time / total if total > 0 else 0
        logger.info(f"并发批量审核完成: {completed}/{total}, 总耗时: {total_time:.1f}秒, 平均每张: {avg_time:.1f}秒")

        return results

    def batch_audit_merged(
        self,
        image_paths: list,
        brand_id: str | None = None,
        max_images_per_request: int = None,
        progress_callback=None,
        result_callback=None,
    ) -> list:
        """
        合并请求批量审核（方案B：单次API调用处理多张图片）

        Args:
            image_paths: 图片路径列表
            brand_id: 品牌ID
            max_images_per_request: 单次请求最大图片数（None则自动计算）
            progress_callback: 进度回调函数 (completed, total, message)
            result_callback: 单条结果回调函数 (result) - 用于流式返回

        Returns:
            审核结果列表
        """
        import time

        total = len(image_paths)
        start_time = time.time()

        logger.info(f"开始合并请求批量审核: {total}张图片")

        # 预处理所有图片
        images = []
        image_sizes = []

        for path in image_paths:
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

        # 获取品牌规范
        rules_checklist = rules_context.get_rules_checklist(brand_id)
        rules_text = rules_context.get_rules_text(brand_id)  # 用于计算token

        # 计算单次请求可容纳的最大图片数
        if max_images_per_request is None:
            max_images_per_request = llm_service.calculate_max_images(image_sizes, rules_text)

        # 分批处理
        results = []
        batches = [images[i:i + max_images_per_request] for i in range(0, len(images), max_images_per_request)]
        batch_paths = [image_paths[i:i + max_images_per_request] for i in range(0, len(image_paths), max_images_per_request)]

        logger.info(f"分为 {len(batches)} 批次处理")

        for batch_idx, (batch_images, batch_path_list) in enumerate(zip(batches, batch_paths)):
            batch_start = time.time()
            logger.info(f"处理第 {batch_idx + 1}/{len(batches)} 批，共 {len(batch_images)} 张图片")

            # 调用LLM批量审核
            batch_results = llm_service.audit_images_batch(
                images=batch_images,
                rules_checklist=rules_checklist,
                progress_callback=None,
            )

            batch_time = time.time() - batch_start
            logger.info(f"批次 {batch_idx + 1} 完成，耗时: {batch_time:.1f}秒")

            # 检查是否有有效结果（如果全部失败则回退到单图审核）
            has_valid_result = any(
                r.get("score", 0) > 0 or r.get("status") != "fail"
                for r in batch_results
            )

            if not has_valid_result and len(batch_images) > 1:
                logger.warning(f"批次 {batch_idx + 1} 合并请求全部失败，回退到并发单图审核")
                # 回退到并发单图审核
                for i, (result, path) in enumerate(zip(batch_results, batch_path_list)):
                    try:
                        # 单独审核每张图片
                        single_result = llm_service.audit_image(
                            image_base64=batch_images[i]["base64"],
                            image_format=batch_images[i]["format"],
                            rules_checklist=rules_checklist,
                        )
                        report = self._build_report(single_result, rules_checklist)
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "success",
                            "report": report
                        }
                        results.append(result_item)
                        # 流式返回
                        if result_callback:
                            result_callback(result_item, len(results), len(results), total)
                    except Exception as e:
                        logger.error(f"单图审核失败 [{path}]: {e}")
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "error",
                            "error": str(e)
                        }
                        results.append(result_item)
                        if result_callback:
                            result_callback(result_item, len(results), len(results), total)
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
                        # 流式返回
                        if result_callback:
                            result_callback(result_item, len(results), len(results), total)
                    except Exception as e:
                        logger.error(f"结果转换失败 [{path}]: {e}")
                        result_item = {
                            "file_name": Path(path).name,
                            "status": "error",
                            "error": str(e)
                        }
                        results.append(result_item)
                        if result_callback:
                            result_callback(result_item, len(results), len(results), total)

            if progress_callback:
                completed = len(results)
                progress_callback(completed, total, f"已完成 {completed}/{total}")

        total_time = time.time() - start_time
        logger.info(f"合并请求批量审核完成: 总耗时: {total_time:.1f}秒, 平均每张: {total_time/total:.1f}秒")

        return results

    def batch_audit(
        self,
        image_paths: list,
        brand_id: str | None = None,
        max_concurrent: int = 5,
        progress_callback=None,
    ) -> list:
        """
        批量审核（默认使用并发方案，保持向后兼容）
        """
        return self.batch_audit_concurrent(image_paths, brand_id, max_concurrent, progress_callback)

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
                is_forbidden=f.get("is_forbidden", False),
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

        # 构建报告
        return AuditReport(
            score=result.get("score", 0),
            status=AuditStatus(result.get("status", "fail")),
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