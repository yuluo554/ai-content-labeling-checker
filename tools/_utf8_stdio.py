# -*- coding: utf-8 -*-
"""把 stdout/stderr 切到 UTF-8（**仅当当前编码不是 UTF-8 家族时**）。

**为什么需要独立模块**：本仓库的 CLI 与 `tools/` 脚本都输出中文。GitHub Actions 的
Windows runner 在没有控制台时，stdout 编码是 **cp1252** —— 任何中文 `print`/`sys.stdout.write`
都会抛 ``UnicodeEncodeError``，而本地 Git Bash（UTF-8）完全看不出来。这类故障最阴的地方是
它发生在**真实工作开始之前或之后**（如"已清理 build/"、"冻结态包验收：通过"），
让 CI 红在一句无害的日志上。

与 :func:`labelcheck.cli.main._ensure_utf8_stdio` 同一口径；后者保留自身实现以维持
"CLI 模块零内部依赖"的独立性（此处供 `tools/` 复用）。

**不做的事**：不改变已有 UTF-8 家族的流；中文控制台（cp936）**保持不动**——它能显示中文，
只在"会在非 ASCII 上崩"的编码上切换。永不抛异常（编码切换失败就沿用原状）。
"""

import sys


#: 已是 UTF-8 家族、无需切换的编码名（已去掉 ``-`` 并小写）
_UTF8_ENCODINGS = ("utf8", "utf8mb4", "cp65001")


def ensure_utf8_stdio():
    """就地切换 stdout/stderr 到 UTF-8；非 UTF-8 家族且可 ``reconfigure`` 时才动。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding in _UTF8_ENCODINGS:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


__all__ = ["ensure_utf8_stdio"]
