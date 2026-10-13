# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 规格文件：onedir **双 exe**（GUI ``console=False`` + CLI ``console=True``）。

用法（仓库根）：

    py -3.8 -m PyInstaller --noconfirm --clean tools/labelcheck.spec

产物：``dist/labelcheck-gui/labelcheck-gui.exe``（无控制台窗口）
与 ``dist/labelcheck/labelcheck.exe``（控制台，可管道取 JSON、可判退出码）。
两者共用**同一份**内嵌 ``data/``。

**为什么双 exe**：GUI 双击即用；CLI 供脚本化/无 GUI 机器验证（``selfcheck --json``）。

**数据白名单**：``datas`` 由 :func:`labelcheck.packaging.build_datas` 生成（只含
``rules``/``mapping``/``truth``/``parse``/``samples``/``knowledge``），**不**整仓塞
``data/``——避免把本地私有件（``data/**/_private/``）与报告输出打进发行包。

**构建后必须校验**：本 spec 只负责产出；"内嵌数据真的落在 dist 之内"由
``tools/verify_package.py`` 断言（验伪要点见 plan/03 §六）。
"""

import sys
from pathlib import Path

# spec 由 PyInstaller 执行；SPECPATH 由 PyInstaller 注入（__file__ 在 spec 里不可靠）
_ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(_ROOT / "src"))

from labelcheck.packaging import CLI_EXE_NAME, GUI_EXE_NAME, assert_ready, build_datas  # noqa: E402

# 构建前置：白名单子目录齐全（缺了会静默少打包）
assert_ready(_ROOT / "data")
_DATAS = build_datas(_ROOT / "data", root=_ROOT)

# 排除无用的重件（减小体积；tkinter 与本工具无关）
_EXCLUDES = ["tkinter", "unittest", "pydoc_data", "test", "distutils"]

#: CLI exe 额外排除 PySide6/PIL/numpy——CLI 通路必须能在**无 GUI 依赖**的机器跑
#: （与 CI 的 core-only 冒烟同口径），也不该把 150 MB Qt 打进命令行工具。
#: **保留 openpyxl**：XLSX 报告导出是文档化功能（FR-8），发行包缺它会把
#: `report.xlsx` 静默降级成 CSV，用户还装不上（冻结态无法 pip install）。
_CLI_EXCLUDES = _EXCLUDES + [
    "PySide6", "shiboken6", "PIL", "numpy", "lxml",
    "labelcheck.gui",
]

#: GUI exe 的隐藏导入（Qt 界面模块由入口脚本按需导入，显式列出防漏）
_GUI_HIDDEN = ["labelcheck.gui", "labelcheck.gui.main_window", "labelcheck.gui.tabs"]


def _analysis(script, hiddenimports=None, excludes=None):
    return Analysis(
        [str(_ROOT / "tools" / script)],
        pathex=[str(_ROOT / "src")],
        binaries=[],
        datas=_DATAS,
        hiddenimports=list(hiddenimports or []),
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=list(excludes or _EXCLUDES),
        noarchive=False,
    )


_gui_analysis = _analysis("entry_gui.py", hiddenimports=_GUI_HIDDEN)
_cli_analysis = _analysis("entry_cli.py", excludes=_CLI_EXCLUDES)

# PYZ(a.pure) 是 PyInstaller 5 与 6 都接受的写法（6 已移除 zipped_data）
_gui_pyz = PYZ(_gui_analysis.pure)
_cli_pyz = PYZ(_cli_analysis.pure)

_gui_exe = EXE(
    _gui_pyz,
    _gui_analysis.scripts,
    [],
    exclude_binaries=True,
    name=GUI_EXE_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

_cli_exe = EXE(
    _cli_pyz,
    _cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name=CLI_EXE_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

_gui_coll = COLLECT(
    _gui_exe,
    _gui_analysis.binaries,
    _gui_analysis.datas,
    strip=False,
    upx=False,
    name=GUI_EXE_NAME,
)

_cli_coll = COLLECT(
    _cli_exe,
    _cli_analysis.binaries,
    _cli_analysis.datas,
    strip=False,
    upx=False,
    name=CLI_EXE_NAME,
)
