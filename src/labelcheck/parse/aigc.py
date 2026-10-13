# -*- coding: utf-8 -*-
"""AIGC 元数据载荷解析（GB 45438-2025 §6.1 b) + 规范性附录 E）。

标准规定：文件元数据隐式标识**以 JSON 串形式**存于含 AIGC 关键词的字段中，JSON 为
``{外层包裹键: {要素键: 字符串值, …}}`` 的**两层结构**（附录 E b)）。

**键名一律来自数据文件**：外层包裹键读映射表的解析画像（``parse_profile.payload_wrapper``），
要素键由 ``labelcheck.mapping`` 的别名表识别——本模块**不硬编码任何政策键名**，
只做"找 JSON → 摊平外层 → 交出键值字典"的结构工作。

**找不到就返回空载荷**——上层据此判定"隐式标识确实缺失"还是"根本没检查到"；绝不臆测。
"""

import json

#: JSON 候选切片的扫描上限（超出即放弃；元数据块本身已受 MAX_BLOB 约束）
MAX_SCAN = 256 * 1024


def _candidate_objects(text):
    """在文本里按 ``{`` 起点做**括号配平**扫描，产出所有可解析的 JSON 对象。

    不依赖整块就是 JSON（元数据里常有前后缀）：逐个 ``{`` 尝试配平闭合，
    能 ``json.loads`` 成功的即候选。确定性：按出现顺序、只取成功项。
    """
    results = []
    scan = text[:MAX_SCAN]
    length = len(scan)
    index = 0
    while index < length:
        start = scan.find("{", index)
        if start < 0:
            break
        depth = 0
        in_string = False
        escaped = False
        end = -1
        for cursor in range(start, length):
            ch = scan[cursor]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = cursor + 1
                    break
        if end < 0:
            break
        snippet = scan[start:end]
        try:
            obj = json.loads(snippet)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            results.append(obj)
        index = end
    return results


def extract_aigc_payload(blobs, wrapper):
    """从元数据文本块中抽出 AIGC 载荷。

    :param blobs: :func:`labelcheck.parse.containers.iter_metadata_blobs` 产出的文本块
    :param wrapper: 载荷外层包裹键（来自映射表 ``parse_profile.payload_wrapper``，
        即附录 E b) 的两层结构；**不在此处硬编码**）
    :returns: ``(fields, payload_count)``——

        - ``fields``：容器键 → 值（发现顺序，确定性；同键保留首个值）；
        - ``payload_count``：**发现的外层包裹块个数**——>1 即该文件保留了多份隐式
          标识（GB 45438-2025 §6.1 c)「应仅保留一份」），供 ``unique`` 规则判定。
    """
    if not wrapper:
        return {}, 0
    fields = {}
    payload_count = 0
    for blob in blobs:
        for obj in _candidate_objects(blob):
            block = obj.get(wrapper)
            if not isinstance(block, dict):
                continue
            payload_count += 1
            for key, value in block.items():
                if key in fields:
                    continue  # 保留首个发现值（确定性；重复由 unique 规则据 payload_count 判）
                fields[key] = value
    return fields, payload_count


__all__ = ["extract_aigc_payload"]
