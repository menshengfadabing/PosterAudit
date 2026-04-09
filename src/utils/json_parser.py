"""品牌合规审核平台 - JSON 解析工具"""

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _fix_unescaped_control_chars(s: str) -> str:
    """
    修复 JSON 字符串值中未转义的换行符/制表符等控制字符。

    LLM 输出的 JSON 有时在字符串值内含有字面换行符，
    导致标准 json.loads 解析失败。本函数逐字符扫描，
    仅对字符串内部的控制字符进行转义，不影响其他结构。
    """
    result: list[str] = []
    in_string = False
    escape_next = False

    for ch in s:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == '\\':
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            result.append('\\r')
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)

    return ''.join(result)


def _try_loads(text: str) -> Optional[Any]:
    """尝试解析 JSON，先直接解析，失败则修复控制字符后重试。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        fixed = _fix_unescaped_control_chars(text)
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        logger.debug(f"_try_loads 修复后仍失败: {e} | 内容前100字符: {text[:100]!r}")
        pass
    return None


def parse_json_response(content: str) -> Optional[dict | list]:
    """
    从文本中解析 JSON（支持多种格式）

    尝试以下方式：
    1. 直接解析
    2. 提取 ```json ... ``` 代码块
    3. 查找第一个 { 和最后一个 } / [ 和 ]

    Args:
        content: 可能包含 JSON 的文本

    Returns:
        解析后的 dict 或 list，解析失败返回 None
    """
    if not content:
        return None

    # 预处理：将中文弯引号替换为转义直引号，避免 JSON 解析失败
    content = content.replace('\u201c', '\\"').replace('\u201d', '\\"')

    # 方法1: 尝试直接解析（含控制字符修复重试）
    result = _try_loads(content)
    if result is not None:
        return result

    # 方法2: 提取 ```json ... ``` 或 ``` ... ``` 代码块
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if json_match:
        result = _try_loads(json_match.group(1).strip())
        if result is not None:
            return result
        logger.debug(f"方法2(代码块)失败，代码块长度={len(json_match.group(1))}")
    else:
        logger.debug("方法2: 未找到 ```json 代码块")

    # 方法3: 查找第一个 { 和最后一个 }（对象）
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        result = _try_loads(content[first_brace:last_brace + 1])
        if result is not None:
            return result
        logger.debug(f"方法3(花括号)失败，截取长度={last_brace - first_brace + 1}")
    else:
        logger.debug(f"方法3: 未找到有效花括号范围 first={first_brace} last={last_brace}")

    # 方法4: 查找第一个 [ 和最后一个 ]（数组）
    first_bracket = content.find("[")
    last_bracket = content.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        result = _try_loads(content[first_bracket:last_bracket + 1])
        if result is not None:
            return result
        logger.debug(f"方法4(方括号)失败，截取长度={last_bracket - first_bracket + 1}")

    logger.warning(f"parse_json_response: 所有方法均失败，内容长度={len(content)}, 前200字符={content[:200]!r}")
    return None


def parse_json_array(content: str, expected_count: int = None) -> list[dict]:
    """
    从文本中解析 JSON 数组

    Args:
        content: 可能包含 JSON 数组的文本
        expected_count: 期望的元素数量（用于补全缺失元素）

    Returns:
        解析后的列表
    """
    data = parse_json_response(content)

    if isinstance(data, list):
        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(item)

        if expected_count and len(result) < expected_count:
            # 补充缺失的结果
            for i in range(len(result), expected_count):
                result.append({"error": f"第{i+1}个结果解析失败", "score": 0, "status": "fail"})

        return result

    # 如果解析结果是单个对象，包装成数组
    if isinstance(data, dict):
        return [data]

    return []

    """
    从文本中解析 JSON 数组

    Args:
        content: 可能包含 JSON 数组的文本
        expected_count: 期望的元素数量（用于补全缺失元素）

    Returns:
        解析后的列表
    """
    data = parse_json_response(content)

    if isinstance(data, list):
        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(item)

        if expected_count and len(result) < expected_count:
            # 补充缺失的结果
            for i in range(len(result), expected_count):
                result.append({"error": f"第{i+1}个结果解析失败", "score": 0, "status": "fail"})

        return result

    # 如果解析结果是单个对象，包装成数组
    if isinstance(data, dict):
        return [data]

    return []