"""pytest 全局配置：把项目 ``src/`` 加入 import 路径（无需安装即可跑测试）。

同时：**强制 UTF-8 输出**，避免 Windows cp936/cp1252 控制台在中文断言信息上崩。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 测试期不写 pyc（本机 pyc 偶发损坏会引发随机 FAIL）
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
# 让被测代码与测试输出在 Windows 控制台上安全处理中文
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


import pytest  # noqa: E402


@pytest.fixture
def repo_root():
    """仓库根目录。"""
    return ROOT


@pytest.fixture
def data_dir():
    """仓库随附的数据目录（``data/``）。"""
    return ROOT / "data"
