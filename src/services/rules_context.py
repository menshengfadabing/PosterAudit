"""品牌合规审核平台 - 规范上下文管理器"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.models.schemas import (
    BrandRules,
    ColorRule,
    ColorRules,
    CopywritingRules,
    ForbiddenWord,
    FontRules,
    LayoutRules,
    LogoRules,
    ReferenceImage,
    SecondaryRule,
)
from src.utils.config import settings, get_app_dir

logger = logging.getLogger(__name__)


class RulesContextManager:
    """规范上下文管理器"""

    def __init__(self, data_dir: str = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = get_app_dir() / "data"

        self.rules_dir = self.data_dir / "rules"
        self._cache: dict[str, BrandRules] = {}
        self._current_brand_id: str = ""

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保目录存在"""
        self.rules_dir.mkdir(parents=True, exist_ok=True)

    def _parse_rules_data(self, data: dict, source: str) -> BrandRules:
        """解析规范数据"""
        rules = BrandRules(
            brand_id=data.get("brand_id", "default"),
            brand_name=data.get("brand_name", "默认品牌"),
            version=data.get("version", "1.0"),
            source=source,
        )

        rules_dict = data.get("rules", {})

        # 色彩规范
        if "color" in rules_dict:
            color_data = rules_dict["color"]
            rules.color = ColorRules()
            if "primary" in color_data:
                rules.color.primary = ColorRule(**color_data["primary"])
            if "secondary" in color_data:
                rules.color.secondary = [ColorRule(**c) for c in color_data["secondary"]]
            if "forbidden" in color_data:
                rules.color.forbidden = [ColorRule(**c) for c in color_data["forbidden"]]

        # Logo规范
        if "logo" in rules_dict:
            rules.logo = LogoRules(**rules_dict["logo"])

        # 字体规范
        if "font" in rules_dict:
            rules.font = FontRules(**rules_dict["font"])

        # 文案规范
        if "copywriting" in rules_dict:
            cw_data = rules_dict["copywriting"]
            rules.copywriting = CopywritingRules()
            if "forbidden_words" in cw_data:
                rules.copywriting.forbidden_words = [
                    ForbiddenWord(**w) for w in cw_data["forbidden_words"]
                ]
            if "required_content" in cw_data:
                rules.copywriting.required_content = cw_data["required_content"]

        # 布局规范
        if "layout" in rules_dict:
            rules.layout = LayoutRules(**rules_dict["layout"])

        return rules

    def add_rules(self, rules: BrandRules, brand_id: Optional[str] = None) -> str:
        """添加品牌规范"""
        if brand_id is None:
            brand_id = f"brand_{uuid.uuid4().hex[:8]}"

        rules.brand_id = brand_id
        rules.upload_time = datetime.now()

        self._cache[brand_id] = rules
        self._save_rules(brand_id, rules)

        logger.info(f"添加品牌规范: {brand_id} - {rules.brand_name}")
        return brand_id

    def _save_rules(self, brand_id: str, rules: BrandRules) -> None:
        """持久化保存规范"""
        brand_dir = self.rules_dir / brand_id
        brand_dir.mkdir(parents=True, exist_ok=True)

        rules_file = brand_dir / "current.json"
        with open(rules_file, "w", encoding="utf-8") as f:
            json.dump(rules.model_dump(), f, ensure_ascii=False, indent=2, default=str)

    def get_rules(self, brand_id: Optional[str] = None) -> Optional[BrandRules]:
        """获取品牌规范"""
        if brand_id is None:
            brand_id = self._current_brand_id

        if brand_id in self._cache:
            return self._cache[brand_id]

        rules_file = self.rules_dir / brand_id / "current.json"
        if rules_file.exists():
            try:
                with open(rules_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rules = BrandRules(**data)
                self._cache[brand_id] = rules
                return rules
            except Exception as e:
                logger.error(f"加载规范失败: {brand_id}, {e}")

        return None

    def set_current_brand(self, brand_id: str) -> bool:
        """设置当前品牌"""
        if brand_id in self._cache or (self.rules_dir / brand_id).exists():
            self._current_brand_id = brand_id
            logger.info(f"当前品牌已切换: {brand_id}")
            return True
        return False

    def get_rules_text(self, brand_id: Optional[str] = None) -> str:
        """获取规范的文本描述（精简格式，节省token）"""
        rules = self.get_rules(brand_id)
        if rules is None:
            return "未找到品牌规范，请先上传规范文档。"

        lines = []
        lines.append(f"品牌：{rules.brand_name}")

        # 色彩规范 - 只保留具体数据
        if rules.color:
            color_parts = []
            if rules.color.primary:
                color_parts.append(f"主色:{rules.color.primary.value}({rules.color.primary.name})")
            if rules.color.secondary:
                secondary = ",".join(f"{c.value}({c.name})" for c in rules.color.secondary)
                color_parts.append(f"辅助色:{secondary}")
            if rules.color.forbidden:
                forbidden = ",".join(f"{c.value}" for c in rules.color.forbidden)
                color_parts.append(f"禁用色:{forbidden}")
            if color_parts:
                lines.append("色彩：" + " | ".join(color_parts))

        # Logo规范 - 只保留具体参数
        if rules.logo:
            logo_parts = []
            if rules.logo.position_description:
                logo_parts.append(f"位置:{rules.logo.position_description}")
            if rules.logo.size_range:
                min_size = rules.logo.size_range.get("min", 5)
                max_size = rules.logo.size_range.get("max", 15)
                logo_parts.append(f"尺寸:{min_size}%-{max_size}%")
            if rules.logo.safe_margin_px:
                logo_parts.append(f"安全边距:{rules.logo.safe_margin_px}px")
            if logo_parts:
                lines.append("Logo：" + " | ".join(logo_parts))

        # 字体规范 - 只保留字体列表
        if rules.font:
            font_parts = []
            if rules.font.allowed:
                font_parts.append(f"推荐:{','.join(rules.font.allowed)}")
            if rules.font.forbidden:
                font_parts.append(f"禁用:{','.join(rules.font.forbidden)}")
            if font_parts:
                lines.append("字体：" + " | ".join(font_parts))

        # 文案规范 - 只保留禁用词
        if rules.copywriting and rules.copywriting.forbidden_words:
            words = ",".join(w.word for w in rules.copywriting.forbidden_words)
            lines.append(f"禁用词：{words}")

        # 布局规范
        if rules.layout:
            layout_parts = []
            if rules.layout.margin_min:
                layout_parts.append(f"最小边距:{rules.layout.margin_min}px")
            if rules.layout.description:
                layout_parts.append(rules.layout.description)
            if layout_parts:
                lines.append("布局：" + " | ".join(layout_parts))

        # 次要规范 - 按分类追加
        if rules.secondary_rules:
            # 按分类分组
            categories = {}
            for rule in rules.secondary_rules:
                if rule.category not in categories:
                    categories[rule.category] = []
                categories[rule.category].append(rule)

            for category, rules_list in categories.items():
                # 每个分类最多取前3条重要规则，节省token
                top_rules = sorted(rules_list, key=lambda x: x.priority)[:3]
                contents = "; ".join(f"{r.name}:{r.content}" for r in top_rules)
                lines.append(f"{category}：{contents}")

        return "\n".join(lines)

    def get_rules_checklist(self, brand_id: Optional[str] = None, preconditions: Optional[dict] = None) -> list[dict]:
        """
        获取规则检查清单（用于 LLM Prompt）

        规则来源：仅使用 secondary_rules，按 Logo→色彩→字体→其他 分类排序。
        主规范结构化字段（color/logo/font）不再单独生成规则条目，避免与 secondary_rules 重复。

        Args:
            brand_id: 品牌ID
            preconditions: 前置条件字典

        Returns:
            规则列表，每条规则包含 rule_id、content、category、reference 等字段
        """
        rules = self.get_rules(brand_id)
        if rules is None:
            return []

        source_prefix = rules.source or rules.brand_name or "品牌规范"

        # 分类排序权重：Logo → 色彩 → 字体 → 其他
        def category_order(category: str) -> int:
            c = category.lower()
            if "logo" in c or "标识" in c:
                return 0
            if "色彩" in c or "颜色" in c or "color" in c:
                return 1
            if "字体" in c or "排版" in c or "font" in c or "type" in c:
                return 2
            return 3

        sorted_rules = sorted(rules.secondary_rules, key=lambda r: category_order(r.category))

        checklist = []
        for i, sr in enumerate(sorted_rules, start=1):
            if not sr.content or not sr.content.strip():
                continue
            entry = {
                "rule_id": f"Rule_{i}",
                "content": sr.content.strip(),
                "category": sr.category,
                "reference": f"参考文档-{source_prefix}",
            }
            if sr.rule_source_id:
                entry["rule_source_id"] = sr.rule_source_id
            if sr.fail_condition:
                entry["fail_condition"] = sr.fail_condition
            if sr.review_condition:
                entry["review_condition"] = sr.review_condition
            if sr.pass_condition:
                entry["pass_condition"] = sr.pass_condition
            if sr.output_level and not sr.fail_condition:
                entry["output_level"] = sr.output_level
            if sr.threshold and not sr.fail_condition:
                entry["threshold"] = sr.threshold
            checklist.append(entry)

        # 根据前置条件过滤 + 注入上下文
        if preconditions:
            checklist = self._apply_preconditions(checklist, preconditions)

        return checklist

    # ─────────────────────────────────────────────────────────────────────────
    # 前置条件豁免逻辑
    # ─────────────────────────────────────────────────────────────────────────

    # 各业务规则的 rule_source_id 映射（以讯飞新规则为准）
    _LOGO_POSITION_IDS = {"H-LOGO-05"}        # Logo 位于规范位置（左上角）
    _LOGO_SIZE_IDS     = {"H-LOGO-06"}        # Logo 相对尺寸合规
    _LOGO_JOINT_IDS    = {"H-LOGO-08", "H-LOGO-10"}  # 联合标识分割线 + 主次顺序

    def _apply_preconditions(self, checklist: list[dict], preconditions: dict) -> list[dict]:
        """
        根据前置条件对规则清单进行豁免过滤和上下文注入。

        豁免策略：
          brand_status=main_subject → 豁免 Logo 位置、尺寸规则（只保留颜色/形变）
          brand_status=none         → 豁免全部 Logo 规则
          joint_brand=none          → 豁免联合标识相关规则（H-LOGO-08、H-LOGO-10）
          collab_lead=partner       → 豁免 Logo 位置（左上角）、尺寸下限

        上下文注入：
          将关键前置条件以 [前置条件] 标签追加到相关规则的 content，
          供 LLM 参考（不修改 fail/review/pass_condition）。
        """
        brand_status = preconditions.get("brand_status", "normal")
        joint_brand  = preconditions.get("joint_brand", "none")
        collab_lead  = preconditions.get("collab_lead")
        department   = preconditions.get("department")
        comm_type    = preconditions.get("comm_type", "")
        material_type = preconditions.get("material_type", "")
        channels     = preconditions.get("channels", [])
        notes        = preconditions.get("notes", "")

        # ── 计算豁免的 rule_source_id 集合 ──────────────────────────────────
        exempt_ids: set[str] = set()

        if brand_status == "none":
            # 跳过所有 Logo 规则（分类含 Logo 的）
            exempt_ids.update(self._LOGO_POSITION_IDS | self._LOGO_SIZE_IDS | self._LOGO_JOINT_IDS)

        elif brand_status == "main_subject":
            # Logo 是核心主体，豁免位置和尺寸约束
            exempt_ids.update(self._LOGO_POSITION_IDS | self._LOGO_SIZE_IDS)

        if joint_brand == "none":
            # 没有联合品牌，联合标识规则无意义
            exempt_ids.update(self._LOGO_JOINT_IDS)

        if collab_lead == "partner":
            # 对方主导，讯飞 Logo 不必在左上角，也没有尺寸下限
            exempt_ids.update(self._LOGO_POSITION_IDS | self._LOGO_SIZE_IDS)

        # ── 构建上下文标注字符串（注入到受影响规则的 content）──────────────
        ctx_parts = []
        if comm_type:
            ctx_parts.append(f"传播类型={comm_type}")
        if material_type:
            ctx_parts.append(f"物料类型={material_type}")
        if channels:
            ctx_parts.append(f"使用渠道={'、'.join(channels)}")
        if joint_brand == "internal" and department:
            ctx_parts.append(f"归属部门={department}")
        if joint_brand != "none" and collab_lead:
            ctx_parts.append(f"合作主导关系={'讯飞主导' if collab_lead == 'xunfei' else '对方主导'}")
        if notes:
            ctx_parts.append(f"补充说明={notes}")
        context_tag = f"[前置条件] {'; '.join(ctx_parts)}" if ctx_parts else ""

        # ── 过滤 + 注入 ───────────────────────────────────────────────────
        filtered = []
        for rule in checklist:
            src_id = rule.get("rule_source_id", "")

            # 1. 豁免：直接跳过
            if src_id in exempt_ids:
                logger.debug(f"豁免规则 {src_id}（前置条件: brand_status={brand_status}, "
                             f"joint_brand={joint_brand}, collab_lead={collab_lead}）")
                continue

            # 2. brand_status=none 时，跳过分类含"Logo"的规则（无 rule_source_id 的通用 Logo 规则）
            if brand_status == "none" and "Logo" in rule.get("category", ""):
                logger.debug(f"豁免Logo规则（无src_id）: {rule.get('rule_id')}")
                continue

            # 3. 注入上下文到受上下文影响的规则
            if context_tag:
                # 对联合标识主次规则（H-LOGO-10）注入合作主导关系，对调性规则注入传播类型
                if src_id in ("H-LOGO-10",) or "调性" in rule.get("category", "") or "场景" in rule.get("category", ""):
                    rule = dict(rule)  # 浅拷贝，避免污染原始 checklist
                    rule["content"] = rule["content"] + f"\n{context_tag}"

            filtered.append(rule)

        # 重新编号 rule_id（保持连续）
        for i, rule in enumerate(filtered, start=1):
            rule["rule_id"] = f"Rule_{i}"

        logger.info(f"前置条件过滤：原始规则 {len(checklist)} 条 → 过滤后 {len(filtered)} 条"
                    f"（豁免 {len(checklist) - len(filtered)} 条）")
        return filtered

    def list_rules(self) -> list[dict[str, Any]]:
        """列出所有品牌规范"""
        result = []

        for brand_id, rules in self._cache.items():
            result.append({
                "brand_id": brand_id,
                "brand_name": rules.brand_name,
                "version": rules.version,
                "source": rules.source,
                "upload_time": rules.upload_time.isoformat() if rules.upload_time else None,
            })

        if self.rules_dir.exists():
            for brand_dir in self.rules_dir.iterdir():
                if brand_dir.is_dir() and brand_dir.name not in self._cache:
                    rules_file = brand_dir / "current.json"
                    if rules_file.exists():
                        try:
                            with open(rules_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            result.append({
                                "brand_id": data.get("brand_id", brand_dir.name),
                                "brand_name": data.get("brand_name", ""),
                                "version": data.get("version", ""),
                                "source": data.get("source"),
                                "upload_time": data.get("upload_time"),
                            })
                        except Exception as e:
                            logger.warning(f"读取规范失败: {brand_dir.name}, {e}")

        return result

    def delete_rules(self, brand_id: str) -> bool:
        """删除品牌规范"""
        if brand_id in self._cache:
            del self._cache[brand_id]

        brand_dir = self.rules_dir / brand_id
        if brand_dir.exists():
            import shutil
            shutil.rmtree(brand_dir)
            logger.info(f"删除品牌规范: {brand_id}")
            return True

        return False

    def get_current_brand_id(self) -> str:
        """获取当前品牌ID"""
        return self._current_brand_id

    # ============== 参考图片管理 ==============

    MAX_REFERENCE_IMAGES = 5  # 每个规范组最多5张参考图片

    def add_reference_image(
        self,
        brand_id: str,
        image_data: bytes,
        filename: str,
        description: str = "",
        image_type: str = "logo",
    ) -> ReferenceImage | None:
        """
        添加参考图片

        Args:
            brand_id: 品牌ID
            image_data: 图片二进制数据
            filename: 文件名
            description: 图片描述
            image_type: 图片类型 (logo/logo_variant/icon等)

        Returns:
            ReferenceImage 对象，失败返回 None
        """
        rules = self.get_rules(brand_id)
        if rules is None:
            logger.warning(f"品牌规范不存在: {brand_id}")
            return None

        # 检查数量限制
        if len(rules.reference_images) >= self.MAX_REFERENCE_IMAGES:
            logger.warning(f"参考图片数量已达上限: {self.MAX_REFERENCE_IMAGES}")
            return None

        # 确保图片目录存在
        images_dir = self.rules_dir / brand_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一文件名（避免冲突）
        safe_filename = filename
        if (images_dir / safe_filename).exists():
            import time
            name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
            safe_filename = f"{name}_{int(time.time())}.{ext}" if ext else f"{name}_{int(time.time())}"

        # 保存图片文件
        image_path = images_dir / safe_filename
        with open(image_path, "wb") as f:
            f.write(image_data)

        # 创建 ReferenceImage 对象
        ref_image = ReferenceImage(
            filename=safe_filename,
            description=description,
            image_type=image_type,
            file_size=len(image_data),
            upload_time=datetime.now(),
        )

        # 添加到规则中
        rules.reference_images.append(ref_image)
        self._cache[brand_id] = rules
        self._save_rules(brand_id, rules)

        logger.info(f"添加参考图片: {brand_id}/{safe_filename}")
        return ref_image

    def get_reference_images(self, brand_id: str) -> list[ReferenceImage]:
        """获取参考图片列表"""
        rules = self.get_rules(brand_id)
        if rules is None:
            return []
        return rules.reference_images

    def get_reference_images_data(self, brand_id: str) -> list[dict]:
        """
        获取参考图片数据（用于 LLM 调用）

        Returns:
            list[dict]: 每个元素包含 {"url": data_url, "format": str, "description": str}
        """
        import base64

        rules = self.get_rules(brand_id)
        if rules is None:
            return []

        images_data = []
        images_dir = self.rules_dir / brand_id / "images"

        for ref_image in rules.reference_images:
            image_path = images_dir / ref_image.filename
            if not image_path.exists():
                logger.warning(f"参考图片文件不存在: {image_path}")
                continue

            # 读取图片
            with open(image_path, "rb") as f:
                image_data = f.read()

            # 确定格式
            ext = image_path.suffix.lower().lstrip(".")
            if ext == "jpg":
                ext = "jpeg"
            image_format = ext if ext in ["png", "jpeg", "gif", "bmp", "webp"] else "png"

            # 转为 base64 data URL
            image_base64 = base64.b64encode(image_data).decode()
            data_url = f"data:image/{image_format};base64,{image_base64}"

            images_data.append({
                "url": data_url,
                "format": image_format,
                "description": ref_image.description,
                "image_type": ref_image.image_type,
            })

        return images_data

    def delete_reference_image(self, brand_id: str, filename: str) -> bool:
        """删除参考图片"""
        rules = self.get_rules(brand_id)
        if rules is None:
            return False

        # 从列表中移除
        original_count = len(rules.reference_images)
        rules.reference_images = [
            img for img in rules.reference_images if img.filename != filename
        ]

        if len(rules.reference_images) == original_count:
            logger.warning(f"参考图片不存在: {brand_id}/{filename}")
            return False

        # 删除文件
        image_path = self.rules_dir / brand_id / "images" / filename
        if image_path.exists():
            image_path.unlink()

        # 更新缓存和持久化
        self._cache[brand_id] = rules
        self._save_rules(brand_id, rules)

        logger.info(f"删除参考图片: {brand_id}/{filename}")
        return True

    def update_reference_image_description(self, brand_id: str, filename: str, description: str) -> bool:
        """更新参考图片描述"""
        rules = self.get_rules(brand_id)
        if rules is None:
            return False

        for img in rules.reference_images:
            if img.filename == filename:
                img.description = description
                self._cache[brand_id] = rules
                self._save_rules(brand_id, rules)
                logger.info(f"更新参考图片描述: {brand_id}/{filename}")
                return True

        return False

    def reparse_rules_from_raw_text(self, brand_id: str) -> Optional[BrandRules]:
        """从 raw_text 重新解析规则（用于升级现有规则以提取结构化字段）"""
        rules = self.get_rules(brand_id)
        if rules is None:
            logger.error(f"品牌规则不存在: {brand_id}")
            return None

        if not rules.raw_text:
            logger.error(f"品牌规则缺少 raw_text 字段: {brand_id}")
            return None

        logger.info(f"开始重新解析品牌规则: {brand_id}")

        # 导入 document_parser（延迟导入避免循环依赖）
        from src.services.document_parser import document_parser

        try:
            # 使用 raw_text 重新解析
            reparsed_rules = document_parser._extract_rules_with_llm(rules.raw_text)

            # 保留原有的 brand_id、reference_images、upload_time
            reparsed_rules.brand_id = rules.brand_id
            reparsed_rules.reference_images = rules.reference_images
            reparsed_rules.upload_time = rules.upload_time

            # 更新缓存和持久化
            self._cache[brand_id] = reparsed_rules
            self._save_rules(brand_id, reparsed_rules)

            logger.info(f"重新解析完成: {brand_id}, secondary_rules数量: {len(reparsed_rules.secondary_rules)}")
            return reparsed_rules

        except Exception as e:
            logger.error(f"重新解析失败: {brand_id}, 错误: {e}")
            return None

    async def async_reparse_rules_from_raw_text(self, brand_id: str) -> Optional[BrandRules]:
        """reparse_rules_from_raw_text 的异步版本，避免阻塞事件循环"""
        import asyncio
        return await asyncio.to_thread(self.reparse_rules_from_raw_text, brand_id)


# 全局规范上下文管理器实例
rules_context = RulesContextManager()