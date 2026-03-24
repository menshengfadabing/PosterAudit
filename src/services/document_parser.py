"""品牌合规审核平台 - 文档解析服务"""

import base64
import io
import json
import logging
import re
from pathlib import Path

import fitz  # PyMuPDF
from pptx import Presentation

from src.models.schemas import (
    BrandRules,
    ColorRule,
    ColorRules,
    CopywritingRules,
    ForbiddenWord,
    FontRules,
    LayoutRules,
    LogoRules,
)
from src.utils.config import settings

logger = logging.getLogger(__name__)


class DocumentParser:
    """文档解析服务"""

    def parse(self, file_data: bytes, filename: str) -> BrandRules:
        """解析文档"""
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return self._parse_pdf(file_data, filename)
        elif ext in (".ppt", ".pptx"):
            return self._parse_ppt(file_data, filename)
        else:
            raise ValueError(f"不支持的文档格式: {ext}")

    def parse_file(self, file_path: str, brand_name: str = None) -> BrandRules:
        """解析本地文件"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, "rb") as f:
            file_data = f.read()

        rules = self.parse(file_data, file_path.name)
        if brand_name:
            rules.brand_name = brand_name

        return rules

    def _parse_pdf(self, file_data: bytes, filename: str) -> BrandRules:
        """解析PDF文档"""
        logger.info(f"解析PDF文档: {filename}")

        doc = fitz.open(stream=file_data, filetype="pdf")
        text_content = []

        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                text_content.append(f"=== 第{page_num + 1}页 ===\n{text}")

        doc.close()

        full_text = "\n\n".join(text_content)
        logger.info(f"PDF解析完成，共{len(text_content)}页")

        rules = self._extract_rules_with_llm(full_text, filename)
        rules.raw_text = full_text[:50000]

        return rules

    def _parse_ppt(self, file_data: bytes, filename: str) -> BrandRules:
        """解析PPT/PPTX文档"""
        logger.info(f"解析PPT文档: {filename}")

        prs = Presentation(io.BytesIO(file_data))
        text_content = []

        for slide_num, slide in enumerate(prs.slides, 1):
            slide_texts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_texts.append(shape.text.strip())

            if slide_texts:
                text_content.append(f"=== 第{slide_num}页 ===\n" + "\n".join(slide_texts))

        full_text = "\n\n".join(text_content)
        logger.info(f"PPT解析完成，共{len(prs.slides)}页")

        rules = self._extract_rules_with_llm(full_text, filename)
        rules.raw_text = full_text[:50000]

        return rules

    def _extract_rules_with_llm(self, text: str, filename: str) -> BrandRules:
        """使用LLM提取品牌规范"""
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        logger.info(f"使用LLM提取品牌规范: {filename}")

        system_prompt = """你是一个品牌规范文档解析专家。请从品牌规范文档中提取结构化规则信息，输出为JSON格式。

严格按照以下JSON结构输出：
{
  "brand_name": "品牌名称",
  "color": {
    "primary": {"name": "颜色名称", "value": "#XXXXXX"},
    "secondary": [{"name": "颜色名称", "value": "#XXXXXX"}],
    "forbidden": [{"name": "颜色名称", "value": "#XXXXXX", "reason": "禁用原因"}]
  },
  "logo": {
    "position": "top_right",
    "position_description": "右上角",
    "size_range": {"min": 8, "max": 15},
    "safe_margin_px": 20
  },
  "font": {
    "allowed": ["字体1", "字体2"],
    "forbidden": ["字体1", "字体2"],
    "size_rules": {"大标题": "32-48px", "正文": "14-18px"}
  },
  "copywriting": {
    "forbidden_words": [{"word": "词语", "category": "分类"}],
    "required_content": ["必须内容1"]
  },
  "layout": {
    "margin_min": 20,
    "description": "布局要求描述"
  }
}

重要规则：
1. 如果某项信息未提及，设为null
2. 颜色值必须是十六进制格式如 #00A4FF
3. Logo位置用英文：top_right(右上角), top_left(左上角), center(居中)
4. 只输出JSON，不要其他文字"""

        user_prompt = f"""请从以下品牌规范文档中提取结构化规则：

文档内容：
{text[:15000]}

请输出JSON："""

        try:
            llm = ChatOpenAI(
                model=settings.doubao_model,
                openai_api_base=settings.openai_api_base,
                openai_api_key=settings.openai_api_key,
                temperature=0.1,
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            response = llm.invoke(messages)
            content = response.content
            logger.info(f"LLM响应: {content[:500]}...")

            # 提取JSON
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r"\{[\s\S]*\}", content)
                json_str = json_match.group() if json_match else content

            data = json.loads(json_str)

            # 构建BrandRules
            rules = BrandRules(
                brand_id="",
                brand_name=data.get("brand_name") or "",
                version="1.0",
                source=filename,
            )

            # 解析色彩
            if data.get("color"):
                color_data = data["color"]
                rules.color = ColorRules()

                if color_data.get("primary"):
                    primary = color_data["primary"]
                    value = primary.get("value") or primary.get("hex") or ""
                    rules.color.primary = ColorRule(
                        name=primary.get("name", "主色"),
                        value=value,
                    )

                if color_data.get("secondary"):
                    rules.color.secondary = [
                        ColorRule(name=c.get("name", ""), value=c.get("value") or c.get("hex") or "")
                        for c in color_data["secondary"]
                        if c.get("value") or c.get("hex") or c.get("name")
                    ]

                if color_data.get("forbidden"):
                    rules.color.forbidden = [
                        ColorRule(
                            name=c.get("name", ""),
                            value=c.get("value") or c.get("hex") or "",
                            reason=c.get("reason", ""),
                        )
                        for c in color_data["forbidden"]
                        if c.get("value") or c.get("hex") or c.get("name")
                    ]

            # 解析Logo
            if data.get("logo"):
                logo_data = data["logo"]
                size_range = logo_data.get("size_range") or {"min": 5, "max": 15}

                if isinstance(size_range, str):
                    numbers = re.findall(r'(\d+\.?\d*)', size_range)
                    size_range = {
                        "min": int(float(numbers[0])) if numbers else 5,
                        "max": int(float(numbers[1])) if len(numbers) > 1 else 15
                    }
                elif isinstance(size_range, dict):
                    # 确保是整数
                    size_range = {
                        "min": int(float(size_range.get("min", 5))),
                        "max": int(float(size_range.get("max", 15)))
                    }

                rules.logo = LogoRules(
                    position=logo_data.get("position", ""),
                    position_description=logo_data.get("position_description", ""),
                    size_range=size_range,
                    safe_margin_px=logo_data.get("safe_margin_px", 20) or 20,
                )

            # 解析字体
            if data.get("font"):
                font_data = data["font"]
                rules.font = FontRules(
                    allowed=font_data.get("allowed", []) or [],
                    forbidden=font_data.get("forbidden", []) or [],
                    size_rules=font_data.get("size_rules", {}) or {},
                )

            # 解析文案
            if data.get("copywriting"):
                cw_data = data["copywriting"]
                rules.copywriting = CopywritingRules()

                if cw_data.get("forbidden_words"):
                    rules.copywriting.forbidden_words = [
                        ForbiddenWord(word=w.get("word", ""), category=w.get("category") or "禁用词")
                        for w in cw_data["forbidden_words"]
                        if w.get("word")
                    ]

                rules.copywriting.required_content = cw_data.get("required_content", []) or []

            # 解析布局
            if data.get("layout"):
                layout_data = data["layout"]
                rules.layout = LayoutRules(
                    margin_min=layout_data.get("margin_min", 20) or 20,
                    description=layout_data.get("description", "") or "",
                )

            logger.info(f"LLM规则提取完成: brand_name={rules.brand_name}")
            return rules

        except Exception as e:
            logger.error(f"LLM规则提取失败: {e}")
            return BrandRules(brand_id="", brand_name="", version="1.0", source=filename)


# 全局文档解析器实例
document_parser = DocumentParser()