# -*- coding: utf-8 -*-
"""CLI exe 的入口脚本（PyInstaller 打包用；``console=True``）。

只转发到 ``labelcheck.cli.main``；``sys.frozen`` 由 PyInstaller 设置，:mod:`labelcheck.paths`
据此走冻结态数据目录分支（``sys._MEIPASS/data`` → ``<exe>/_internal/data`` → ``<exe>/data``）。

运行（源码态）：``py tools/entry_cli.py selfcheck``。
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from labelcheck.cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
