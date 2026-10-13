# -*- coding: utf-8 -*-
"""GUI exe 的入口脚本（PyInstaller 打包用；``console=False``）。

**为什么单独一个入口脚本**：PyInstaller 需要一个"可执行脚本"作为分析起点；直接指向
``labelcheck/gui/main_window.py`` 会让相对导入（``from .. import``）失去包上下文。
这里只做一件事——把包内入口转发出去，保持 ``labelcheck`` 包结构完整。

**``--selftest <文件>``**：本 exe 是窗口版（``console=False``），stdout 不接终端，
故自检把结果**写进指定 JSON 文件**并以退出码报告成败——这样冻结态 GUI 也能在
无显示环境下被脚本化验收（``tools/verify_package.py`` 用得上）。

运行（源码态）：``py tools/entry_gui.py``（需先 ``PYTHONPATH=src``）。
"""

import sys
from pathlib import Path

# 源码态：把 src/ 加入 import 路径；冻结态 PyInstaller 已内嵌 labelcheck 包。
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _selftest(out_path):
    """离屏装配主窗口 + 定位数据目录，把结果写入 ``out_path``（JSON）。"""
    import json
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from labelcheck.paths import find_data_dir, is_frozen
    from labelcheck.gui.main_window import build_app

    data_dir = find_data_dir(None, require=False)
    payload = {
        "frozen": is_frozen(),
        "data_dir": str(data_dir) if data_dir else "",
        "tab_count": 0,
        "verified_rule_count": 0,
        "pending_rule_count": 0,
        "problems": [],
    }
    try:
        app, window = build_app(argv=[], data_dir=data_dir)
        payload["tab_count"] = len(window.tab_objects)
    except Exception as exc:  # noqa: BLE001 - 自检要把任何问题写进报告而非抛穿
        payload["problems"].append("装配主窗口失败：{0}".format(exc))

    if data_dir:
        try:
            from labelcheck.rules import effective_ruleset

            ruleset = effective_ruleset(data_dir)
            payload["verified_rule_count"] = ruleset.verified_rule_count
            payload["pending_rule_count"] = ruleset.pending_rule_count
        except Exception as exc:  # noqa: BLE001
            payload["problems"].append("加载规则库失败：{0}".format(exc))
    else:
        payload["problems"].append("未定位到数据目录")

    if payload["tab_count"] != 6:
        payload["problems"].append("页签数异常：{0}".format(payload["tab_count"]))
    if payload["verified_rule_count"] <= 0:
        payload["problems"].append("生效规则数为 0")

    Path(out_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if not payload["problems"] else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(_selftest(sys.argv[2]))

    from labelcheck.gui.main_window import main

    sys.exit(main())
