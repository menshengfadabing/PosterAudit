"""品牌合规审核平台 - JSON 解析工具"""

import json
import re
from typing import Any, Optional


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

    # 方法1: 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 方法2: 提取 ```json ... ``` 或 ``` ... ``` 代码块
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 方法3: 查找第一个 { 和最后一个 }（对象）
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(content[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    # 方法4: 查找第一个 [ 和最后一个 ]（数组）
    first_bracket = content.find("[")
    last_bracket = content.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        try:
            return json.loads(content[first_bracket:last_bracket + 1])
        except json.JSONDecodeError:
            pass

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