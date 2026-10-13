"""确定性 JSON 读写与指纹工具。

纪律（plan/03 §七 / plan/05 §三.1）：

- 落盘一律 LF（``newline="\\n"``）——Python 3.8 无 ``Path.write_text(newline=)``，
  故用 ``open()`` 显式传参（``create_system`` 类漂移的文本对应物）；
- 产物**不含时间戳**——时间字段由调用方显式传入，保证"相同输入两次导出逐字节一致"；
- 读入支持 ``parse_float=Decimal``（金额/阈值边界比较不受二进制浮点尾差影响）。
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .errors import UsageError


def sha256_bytes(data):
    """返回字节串的 sha256（小写 hex）。"""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    """返回文本（UTF-8）的 sha256（小写 hex）。"""
    if isinstance(text, str):
        text = text.encode("utf-8")
    return sha256_bytes(text)


def sha256_file(path):
    """流式计算文件 sha256（小写 hex），不整体载入内存。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(obj, indent=2, sort_keys=False):
    """把对象序列化为**规范 JSON 文本**（LF 结尾、UTF-8 可写）。

    ``ensure_ascii=False`` 保留中文可读；``separators`` 固定保证同一对象
    在不同 Python 版本上产出相同字节。
    """
    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=indent,
        sort_keys=sort_keys,
        separators=(",", ": ") if indent else (",", ":"),
    )


def write_text_lf(path, text):
    """以 LF 行尾写文本（跨平台字节一致）。"""
    path = Path(path)
    parent = path.parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def write_json(path, obj, indent=2, sort_keys=False):
    """确定性写 JSON 文件（LF 行尾、结尾换行）。"""
    text = canonical_json(obj, indent=indent, sort_keys=sort_keys)
    if not text.endswith("\n"):
        text += "\n"
    return write_text_lf(path, text)


def load_json(path, use_decimal=False, error_cls=UsageError):
    """读取 JSON 文件，失败时抛出带路径信息的指定异常。

    :param use_decimal: True 时浮点数解析为 :class:`decimal.Decimal`
        （金额/阈值比较用，避免二进制浮点尾差）。
    :param error_cls: 抛出的异常类型（读数据文件用 ``UsageError``，
        读规则库用 ``EnvironmentError_``，以对到正确退出码）。
    """
    path = Path(path)
    if not path.is_file():
        raise error_cls("文件不存在：{0}".format(path))
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise error_cls("文件不是合法 UTF-8：{0}（{1}）".format(path, exc))
    except OSError as exc:
        raise error_cls("无法读取文件：{0}（{1}）".format(path, exc))

    try:
        if use_decimal:
            return json.loads(text, parse_float=Decimal)
        return json.loads(text)
    except ValueError as exc:
        raise error_cls("JSON 解析失败：{0}（{1}）".format(path, exc))


def load_json_str(text, use_decimal=False, error_cls=UsageError):
    """从字符串解析 JSON（供 stdin / 测试使用）。"""
    try:
        if use_decimal:
            return json.loads(text, parse_float=Decimal)
        return json.loads(text)
    except ValueError as exc:
        raise error_cls("JSON 解析失败：（{0}）".format(exc))


__all__ = [
    "sha256_bytes",
    "sha256_text",
    "sha256_file",
    "canonical_json",
    "write_text_lf",
    "write_json",
    "load_json",
    "load_json_str",
]
