"""CLI 包（argparse）。

`main.py` 顶层**不得 import GUI/PySide6**（AST 守门测试锁死）。
`gui` 子命令（M5）须在本包内**惰性导入**，缺依赖时打印安装提示并以 exit 2 退出。
"""

from .main import main  # noqa: F401

__all__ = ["main"]
