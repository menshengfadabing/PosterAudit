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
)
from src.services.llm_service import llm_service
from src.services.rules_context import rules_context

logger = logging.getLogger(__name__)


class AuditService:
    """品牌合规审核服务"""

    SUPPORTED_FORMATS = {"png", "jpeg", "jpg", "gif", "bmp", "webp"}

    # 压缩配置
    MAX_DIMENSION = 1920  # 最大边长
    MAX_FILE_SIZE = 500_000  # 最大文件大小 500KB
    JPEG_QUALITY = 75  # JPEG质量

    def preprocess_image(self, image_data: bytes | str, image_format: str = "png") -> tuple[str, str]:
        """
        预处理图片 - 智能压缩以节省Token和传输时间

        Args:
            image_data: 图片数据（bytes或base64字符串）
            image_format: 图片格式

        Returns:
            (base64编码的图片, 格式)
        """
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
        original_mode = img.mode

        # 转换为RGB模式（统一处理）
        if img.mode in ("RGBA", "P", "LA", "L"):
            if img.mode == "RGBA":
                # 保留透明度信息，使用白色背景
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
        max_dimension = self.MAX_DIMENSION
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.info(f"图片缩放: {original_size} -> {img.size}")

        # 压缩为JPEG格式
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=self.JPEG_QUALITY, optimize=True)

        # 检查文件大小，如果过大则进一步压缩
        file_size = len(buffer.getvalue())
        if file_size > self.MAX_FILE_SIZE:
            # 计算需要的质量
            quality = max(50, int(self.JPEG_QUALITY * self.MAX_FILE_SIZE / file_size))
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            logger.info(f"图片进一步压缩: quality={quality}, size={len(buffer.getvalue())}")

        image_base64 = base64.b64encode(buffer.getvalue()).decode()

        # 记录压缩效果
        original_kb = len(image_data) / 1024
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

            # 获取品牌规范文本
            rules_text = rules_context.get_rules_text(brand_id)

            logger.info("调用LLM审核...")
            result = llm_service.audit_image(
                image_base64=image_base64,
                image_format=image_format,
                rules_text=rules_text,
                progress_callback=progress_callback,
            )

            return self._build_report(result)

        except Exception as e:
            logger.error(f"审核失败: {e}", exc_info=True)
            raise

    def batch_audit(
        self,
        image_paths: list,
        brand_id: str | None = None,
        max_concurrent: int = 5,
        progress_callback=None,
    ) -> list:
        """
        并发批量审核

        Args:
            image_paths: 图片路径列表
            brand_id: 品牌ID
            max_concurrent: 最大并发数
            progress_callback: 进度回调函数 (current, total, message)

        Returns:
            审核结果列表
        """
        results = [None] * len(image_paths)
        total = len(image_paths)

        logger.info(f"开始批量审核: {total}张图片, 最大并发数: {max_concurrent}")

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(self.audit_file, path, brand_id): i
                for i, path in enumerate(image_paths)
            }

            # 收集结果
            completed = 0
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = {
                        "file_name": Path(image_paths[index]).name,
                        "status": "success",
                        "report": future.result()
                    }
                except Exception as e:
                    logger.error(f"审核失败 [{image_paths[index]}]: {e}")
                    results[index] = {
                        "file_name": Path(image_paths[index]).name,
                        "status": "error",
                        "error": str(e)
                    }

                completed += 1
                if progress_callback:
                    progress_callback(completed, total, f"已完成 {completed}/{total}")

        logger.info(f"批量审核完成: {completed}/{total}")
        return results

    def _build_report(self, result: dict) -> AuditReport:
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
            issues=issues,
            summary=result.get("summary", ""),
        )


# 全局审核服务实例
audit_service = AuditService()