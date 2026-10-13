# -*- coding: utf-8 -*-
"""冻结态包验收（M5，发布门）：在中立环境下断言"内嵌数据真的可用"。

用法：

    py -3.8 tools/verify_package.py                 # 校验 dist/ 下的双 exe
    py -3.8 tools/verify_package.py --dist path/    # 指定 dist 目录
    py -3.8 tools/verify_package.py --json          # 机器可读（CI 用）

**为什么必须中立目录 + 清环境变量**（plan/03 §六 验伪要点）：数据目录定位有四个
分支，其中"环境变量"与"源码态/CWD 上溯"都能兜底命中**仓库** ``data/``——若沿用当前
环境或从仓库根跑，冻结态自检会命中仓库数据，看起来全绿，实际**没验到内嵌数据**
（"验了个寂寞"）。故本脚本：① 清 ``LABELCHECK_DATA_DIR``；② 以 exe 所在目录为 CWD；
③ 额外断言解析到的数据目录**落在 dist 之内**。

退出码：``0`` 全部通过 / ``1`` 有断言未通过 / ``2`` 用法错误。
"""

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from labelcheck.packaging import (  # noqa: E402
    CLI_EXE_NAME, GUI_EXE_NAME, default_dist_dir, verify_dist,
)


def _resolve_dir(dist_dir, name):
    """定位某个 exe 所在目录（兼容 PyInstaller 5 平铺与 6 onedir 布局）。"""
    dist_dir = Path(dist_dir)
    nested = dist_dir / name
    if (nested / "{0}.exe".format(name)).is_file():
        return nested
    if (dist_dir / "{0}.exe".format(name)).is_file():
        return dist_dir
    return nested


def main(argv=None):
    parser = argparse.ArgumentParser(description="冻结态包验收（内嵌数据可用性）")
    parser.add_argument("--dist", default=None, metavar="DIR", help="dist 目录（默认 dist/）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（CI 用）")
    parser.add_argument("--timeout", type=int, default=120, help="单次自检超时（秒）")
    args = parser.parse_args(argv)

    dist_dir = Path(args.dist) if args.dist else default_dist_dir()
    if not dist_dir.is_dir():
        sys.stderr.write("dist 目录不存在：{0}（先跑 tools/build_exe.py）\n".format(dist_dir))
        return 2

    gui_dir = _resolve_dir(dist_dir, GUI_EXE_NAME)
    cli_dir = _resolve_dir(dist_dir, CLI_EXE_NAME)

    results = {
        "dist": str(dist_dir.resolve()),
        # GUI exe 为窗口版（console=False）→ 用 --selftest 写文件方式做冻结态实跑
        "gui_frozen": verify_dist(
            gui_dir, exe_name=GUI_EXE_NAME, run=True, gui_selftest=True, timeout=args.timeout),
        "cli_frozen": verify_dist(cli_dir, exe_name=CLI_EXE_NAME, run=True, timeout=args.timeout),
    }
    results["ok"] = bool(results["gui_frozen"]["ok"] and results["cli_frozen"]["ok"])

    if args.json:
        sys.stdout.write(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write("冻结态包验收：{0}\n".format("通过" if results["ok"] else "未通过"))
        for key in ("gui_frozen", "cli_frozen"):
            item = results[key]
            sys.stdout.write("  [{0}] {1}\n".format(
                "通过" if item["ok"] else "未通过", key))
            sys.stdout.write("      data_dir    : {0}\n".format(item["data_dir"]))
            sys.stdout.write("      inside_dist : {0}\n".format(item["inside_dist"]))
            sys.stdout.write("      frozen      : {0}\n".format(item["frozen"]))
            sys.stdout.write("      生效规则    : {0}（待核对 {1}）\n".format(
                item["verified_rule_count"], item["pending_rule_count"]))
            for problem in item["problems"]:
                sys.stdout.write("      问题        : {0}\n".format(problem))

    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
