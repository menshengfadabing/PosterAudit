"""品牌合规审核平台 - 文档解析服务"""

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

# 支持的文档格式
SUPPORTED_FORMATS = {
    # 格式扩展名 -> (解析方法名, 描述)
    ".pdf": ("_parse_pdf", "PDF文档"),
    ".ppt": ("_parse_ppt", "PowerPoint演示文稿"),
    ".pptx": ("_parse_ppt", "PowerPoint演示文稿"),
    ".doc": ("_parse_word", "Word文档"),
    ".docx": ("_parse_word", "Word文档"),
    ".xls": ("_parse_excel", "Excel表格"),
    ".xlsx": ("_parse_excel", "Excel表格"),
    ".md": ("_parse_text", "Markdown文档"),
    ".txt": ("_parse_text", "文本文件"),
}


class DocumentParser:
    """文档解析服务"""

    def parse(self, file_data: bytes, filename: str) -> BrandRules:
        """解析文档"""
        ext = Path(filename).suffix.lower()

        if ext not in SUPPORTED_FORMATS:
            raise ValueError(f"不支持的文档格式: {ext}，支持的格式: {', '.join(SUPPORTED_FORMATS.keys())}")

        method_name, _ = SUPPORTED_FORMATS[ext]
        parse_method = getattr(self, method_name)
        return parse_method(file_data, filename)

    def parse_file(self, file_path: str, brand_name: str = None, progress_callback=None) -> BrandRules:
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
        logger.info(f"PDF解析完成，共{len(text_content)}页，{len(full_text)}字符")

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
        logger.info(f"PPT解析完成，共{len(prs.slides)}页，{len(full_text)}字符")

        rules = self._extract_rules_with_llm(full_text, filename)
        rules.raw_text = full_text[:50000]

        return rules

    def _parse_word(self, file_data: bytes, filename: str) -> BrandRules:
        """解析Word文档 (.doc, .docx)"""
        logger.info(f"解析Word文档: {filename}")

        ext = Path(filename).suffix.lower()
        text_content = []

        try:
            if ext == ".docx":
                # 使用python-docx解析.docx
                from docx import Document
                doc = Document(io.BytesIO(file_data))

                # 提取段落文本
                for i, para in enumerate(doc.paragraphs):
                    if para.text.strip():
                        text_content.append(para.text.strip())

                # 提取表格文本
                for table_idx, table in enumerate(doc.tables):
                    table_texts = []
                    for row in table.rows:
                        row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                        if row_text:
                            table_texts.append(row_text)
                    if table_texts:
                        text_content.append(f"\n=== 表格{table_idx + 1} ===\n" + "\n".join(table_texts))

            else:
                # .doc格式，尝试使用antiword或直接用python-docx（可能失败）
                try:
                    from docx import Document
                    doc = Document(io.BytesIO(file_data))
                    for para in doc.paragraphs:
                        if para.text.strip():
                            text_content.append(para.text.strip())
                except Exception as e:
                    logger.warning(f"解析.doc格式失败，尝试其他方式: {e}")
                    # 尝试作为纯文本解析
                    try:
                        text_content.append(file_data.decode('utf-8', errors='ignore'))
                    except:
                        text_content.append(file_data.decode('gbk', errors='ignore'))

        except ImportError:
            logger.error("未安装python-docx库，无法解析Word文档")
            raise ImportError("请安装python-docx库: pip install python-docx")
        except Exception as e:
            logger.error(f"Word文档解析失败: {e}")
            raise

        full_text = "\n\n".join(text_content)
        logger.info(f"Word解析完成，{len(full_text)}字符")

        rules = self._extract_rules_with_llm(full_text, filename)
        rules.raw_text = full_text[:50000]

        return rules

    def _parse_excel(self, file_data: bytes, filename: str) -> BrandRules:
        """解析Excel表格 (.xls, .xlsx)"""
        logger.info(f"解析Excel文档: {filename}")

        ext = Path(filename).suffix.lower()
        text_content = []

        try:
            if ext == ".xlsx":
                # 使用openpyxl解析.xlsx
                from openpyxl import load_workbook
                wb = load_workbook(io.BytesIO(file_data), data_only=True)

                for sheet_name in wb.sheetnames:
                    sheet = wb[sheet_name]
                    sheet_texts = [f"=== 工作表: {sheet_name} ==="]

                    for row in sheet.iter_rows(values_only=True):
                        # 过滤空值，转字符串
                        row_values = [str(cell) if cell is not None else "" for cell in row]
                        row_text = " | ".join(row_values)
                        if row_text.strip(" |"):
                            sheet_texts.append(row_text)

                    if len(sheet_texts) > 1:  # 有内容才添加
                        text_content.append("\n".join(sheet_texts))

            else:
                # .xls格式，使用xlrd
                try:
                    import xlrd
                    workbook = xlrd.open_workbook(file_contents=file_data)

                    for sheet in workbook.sheets():
                        sheet_texts = [f"=== 工作表: {sheet.name} ==="]

                        for row_idx in range(sheet.nrows):
                            row_values = [str(sheet.cell_value(row_idx, col_idx)) for col_idx in range(sheet.ncols)]
                            row_text = " | ".join(row_values)
                            if row_text.strip(" |"):
                                sheet_texts.append(row_text)

                        if len(sheet_texts) > 1:
                            text_content.append("\n".join(sheet_texts))

                except ImportError:
                    logger.warning("未安装xlrd库，尝试用openpyxl解析.xls")
                    from openpyxl import load_workbook
                    wb = load_workbook(io.BytesIO(file_data), data_only=True)

                    for sheet_name in wb.sheetnames:
                        sheet = wb[sheet_name]
                        sheet_texts = [f"=== 工作表: {sheet_name} ==="]

                        for row in sheet.iter_rows(values_only=True):
                            row_values = [str(cell) if cell is not None else "" for cell in row]
                            row_text = " | ".join(row_values)
                            if row_text.strip(" |"):
                                sheet_texts.append(row_text)

                        if len(sheet_texts) > 1:
                            text_content.append("\n".join(sheet_texts))

        except ImportError as e:
            logger.error(f"缺少必要的库: {e}")
            raise ImportError("请安装openpyxl库: pip install openpyxl (或 xlrd for .xls)")
        except Exception as e:
            logger.error(f"Excel解析失败: {e}")
            raise

        full_text = "\n\n".join(text_content)
        logger.info(f"Excel解析完成，{len(full_text)}字符")

        rules = self._extract_rules_with_llm(full_text, filename)
        rules.raw_text = full_text[:50000]

        return rules

    def _parse_text(self, file_data: bytes, filename: str) -> BrandRules:
        """解析文本文件 (.txt, .md)"""
        ext = Path(filename).suffix.lower()
        logger.info(f"解析文本文档: {filename}")

        # 尝试多种编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
        text_content = None

        for encoding in encodings:
            try:
                text_content = file_data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if text_content is None:
            # 最后尝试忽略错误
            text_content = file_data.decode('utf-8', errors='ignore')

        full_text = text_content.strip()
        logger.info(f"文本解析完成，{len(full_text)}字符")

        # 对于Markdown文件，可以做一些简单的格式处理说明
        if ext == ".md":
            # 统计标题数量
            heading_count = len(re.findall(r'^#{1,6}\s', full_text, re.MULTILINE))
            if heading_count > 0:
                logger.info(f"检测到{heading_count}个Markdown标题")

        rules = self._extract_rules_with_llm(full_text, filename)
        rules.raw_text = full_text[:50000]

        return rules

    def _extract_rules_with_llm(self, text: str, filename: str) -> BrandRules:
        """使用LLM提取品牌规范"""
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        logger.info(f"使用LLM提取品牌规范: {filename}")

        # 检查API配置
        if not settings.deepseek_api_key:
            logger.warning("未配置DeepSeek API Key，无法进行LLM提取")
            return BrandRules(
                brand_id="",
                brand_name="",
                version="1.0",
                source=filename,
            )

        system_prompt = """你是品牌规范文档解析专家。请从品牌规范文档中提取结构化规则信息。

你需要提取以下信息：
1. 品牌名称 (brand_name)
2. 色彩规范 (color)：主色、辅助色、禁用色
3. Logo规范 (logo)：位置、尺寸范围、安全间距
4. 字体规范 (font)：允许字体、禁用字体
5. 文案规范 (copywriting)：禁用词
6. 布局规范 (layout)：最小边距

输出JSON格式：
```json
{
  "brand_name": "品牌名称",
  "color": {
    "primary": {"name": "颜色名称", "value": "#XXXXXX"},
    "secondary": [{"name": "名称", "value": "#XXXXXX"}],
    "forbidden": [{"name": "名称", "value": "#XXXXXX", "reason": "原因"}]
  },
  "logo": {
    "position": "top_left 或 top_right 或 center",
    "position_description": "位置描述",
    "size_range": {"min": 5, "max": 15},
    "safe_margin_px": 20
  },
  "font": {
    "allowed": ["字体1", "字体2"],
    "forbidden": ["字体3"],
    "size_rules": {"标题": "32px", "正文": "14px"}
  },
  "copywriting": {
    "forbidden_words": [{"word": "词语", "category": "分类"}]
  },
  "layout": {
    "margin_min": 20,
    "description": "布局说明"
  }
}
```

规则：
- 颜色值必须是十六进制格式如 #00A4FF
- 如果文档中未提及某项，该字段设为 null
- 只输出JSON，不要其他文字"""

        # 截取文本，保留关键内容
        max_chars = 12000
        if len(text) > max_chars:
            # 尝试保留前面部分和包含关键词的部分
            text_for_llm = text[:max_chars]
            logger.info(f"文本过长({len(text)}字符)，截取前{max_chars}字符")
        else:
            text_for_llm = text

        user_prompt = f"""请从以下品牌规范文档中提取结构化规则。

文档内容：
{text_for_llm}

请输出JSON格式的规则："""

        try:
            # 使用 DeepSeek 纯文本模型进行规则解析
            logger.info(f"DeepSeek API配置: base={settings.deepseek_api_base}, model={settings.deepseek_model}")

            llm = ChatOpenAI(
                model=settings.deepseek_model,
                base_url=settings.deepseek_api_base,
                api_key=settings.deepseek_api_key,
                temperature=0.1,
                timeout=120,  # 增加超时时间
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            logger.info("正在调用LLM...")
            response = llm.invoke(messages)
            content = response.content
            logger.info(f"LLM响应长度: {len(content)} 字符")
            logger.debug(f"LLM响应内容: {content[:1000]}...")

            # 提取JSON - 多种方式尝试
            data = self._parse_json_response(content)

            if data is None:
                logger.error("无法从LLM响应中解析JSON")
                logger.error(f"原始响应: {content}")
                return BrandRules(
                    brand_id="",
                    brand_name="",
                    version="1.0",
                    source=filename,
                )

            # 构建BrandRules
            rules = BrandRules(
                brand_id="",
                brand_name=data.get("brand_name") or "",
                version="1.0",
                source=filename,
            )

            # 解析色彩
            if data.get("color"):
                self._parse_color_rules(rules, data["color"])

            # 解析Logo
            if data.get("logo"):
                self._parse_logo_rules(rules, data["logo"])

            # 解析字体
            if data.get("font"):
                self._parse_font_rules(rules, data["font"])

            # 解析文案
            if data.get("copywriting"):
                self._parse_copywriting_rules(rules, data["copywriting"])

            # 解析布局
            if data.get("layout"):
                self._parse_layout_rules(rules, data["layout"])

            logger.info(f"LLM规则提取完成: brand_name={rules.brand_name}, "
                       f"color={rules.color is not None}, "
                       f"logo={rules.logo is not None}, "
                       f"font={rules.font is not None}")

            return rules

        except Exception as e:
            logger.error(f"LLM规则提取失败: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return BrandRules(
                brand_id="",
                brand_name="",
                version="1.0",
                source=filename,
            )

    def _parse_json_response(self, content: str) -> dict | None:
        """从LLM响应中解析JSON"""
        # 方法1: 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 方法2: 提取```json ... ```块
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 方法3: 找到第一个 { 和最后一个 }
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(content[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _parse_color_rules(self, rules: BrandRules, color_data: dict):
        """解析色彩规则"""
        rules.color = ColorRules()

        if color_data.get("primary"):
            primary = color_data["primary"]
            value = primary.get("value") or primary.get("hex") or ""
            if value:
                rules.color.primary = ColorRule(
                    name=primary.get("name", "主色"),
                    value=value,
                )

        if color_data.get("secondary"):
            secondary_list = [
                ColorRule(name=c.get("name", ""), value=c.get("value") or c.get("hex") or "")
                for c in color_data["secondary"]
                if c.get("value") or c.get("hex")
            ]
            if secondary_list:
                rules.color.secondary = secondary_list

        if color_data.get("forbidden"):
            forbidden_list = [
                ColorRule(
                    name=c.get("name", ""),
                    value=c.get("value") or c.get("hex") or "",
                    reason=c.get("reason", ""),
                )
                for c in color_data["forbidden"]
                if c.get("value") or c.get("hex")
            ]
            if forbidden_list:
                rules.color.forbidden = forbidden_list

    def _parse_logo_rules(self, rules: BrandRules, logo_data: dict):
        """解析Logo规则"""
        size_range = logo_data.get("size_range")

        if size_range is None:
            size_range = {"min": 5, "max": 15}
        elif isinstance(size_range, str):
            numbers = re.findall(r'(\d+\.?\d*)', size_range)
            size_range = {
                "min": int(float(numbers[0])) if numbers else 5,
                "max": int(float(numbers[1])) if len(numbers) > 1 else 15
            }
        elif isinstance(size_range, dict):
            size_range = {
                "min": int(float(size_range.get("min", 5) or 5)),
                "max": int(float(size_range.get("max", 15) or 15))
            }

        rules.logo = LogoRules(
            position=logo_data.get("position", "") or "",
            position_description=logo_data.get("position_description", "") or "",
            size_range=size_range,
            safe_margin_px=int(logo_data.get("safe_margin_px", 20) or 20),
        )

    def _parse_font_rules(self, rules: BrandRules, font_data: dict):
        """解析字体规则"""
        allowed = font_data.get("allowed") or []
        forbidden = font_data.get("forbidden") or []
        size_rules = font_data.get("size_rules") or {}

        # 过滤空值
        allowed = [f for f in allowed if f]
        forbidden = [f for f in forbidden if f]

        if allowed or forbidden or size_rules:
            rules.font = FontRules(
                allowed=allowed,
                forbidden=forbidden,
                size_rules=size_rules,
            )

    def _parse_copywriting_rules(self, rules: BrandRules, cw_data: dict):
        """解析文案规则"""
        forbidden_words = cw_data.get("forbidden_words") or []

        if forbidden_words:
            rules.copywriting = CopywritingRules()
            rules.copywriting.forbidden_words = [
                ForbiddenWord(word=w.get("word", ""), category=w.get("category") or "禁用词")
                for w in forbidden_words
                if w.get("word")
            ]

        required_content = cw_data.get("required_content") or []
        if required_content and rules.copywriting:
            rules.copywriting.required_content = required_content

    def _parse_layout_rules(self, rules: BrandRules, layout_data: dict):
        """解析布局规则"""
        margin_min = layout_data.get("margin_min")
        description = layout_data.get("description") or ""

        if margin_min is not None or description:
            rules.layout = LayoutRules(
                margin_min=int(margin_min) if margin_min else 20,
                description=description,
            )


# 全局文档解析器实例
document_parser = DocumentParser()