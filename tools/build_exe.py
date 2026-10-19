# -*- coding: utf-8 -*-
"""构建 PyInstaller onedir 双 exe（M5）。

用法（仓库根，**用 py 启动器**，Windows 上 ``python`` 是商店占位符）：

    py -3.12 -m tools.build_exe                # 构建 + 自动校验
    py -3.12 -m tools.build_exe --no-verify    # 只构建
    py -3.12 -m tools.build_exe --clean        # 先清 dist/build

流程：① 前置检查数据白名单齐全 → ② 调 PyInstaller（``tools/labelcheck.spec``）→
③ 调 :func:`labelcheck.packaging.verify_dist` 断言"内嵌数据落在 dist 之内且可用"。

**为什么把校验串进构建**：打包"成功"（exit 0）不代表内嵌数据可用——冻结态数据定位
可能兜底命中仓库 ``data/``，exe 在本机看着能跑、换台机器就崩（系列实测假结果陷阱）。
故构建脚本默认在构建后**立即**跑中立环境校验，任一断言不过即非零退出。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
# ``python -m tools.build_exe`` 时 sys.path[0] 是仓库根（不是 tools/），故共享模块要显式可导入。
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from labelcheck.packaging import (  # noqa: E402
    CLI_EXE_NAME, GUI_EXE_NAME, assert_ready, default_dist_dir, repo_root, verify_dist,
)

SPEC = _ROOT / "tools" / "labelcheck.spec"


def _ensure_utf8_stdio():
    """把 stdout/stderr 切到 UTF-8（仅当当前编码不是 UTF-8 家族时）。

    **为什么必须有**（CI 实测，run 39255079702）：GitHub Actions 的 Windows runner 在
    无控制台时 stdout 编码是 **cp1252**，本脚本的中文输出会在 ``print()`` 处抛
    ``UnicodeEncodeError`` —— 构建还没开始就失败，而本地 Git Bash（UTF-8）看不出来。
    实现见 ``tools/_utf8_stdio.py``（各 tools 脚本共用同一处置口径）。
    """
    from _utf8_stdio import ensure_utf8_stdio

    ensure_utf8_stdio()


def build(clean=False, dist_dir=None):
    """调 PyInstaller 构建；返回 (returncode, dist 目录)。"""
    dist_dir = Path(dist_dir) if dist_dir else default_dist_dir()
    if clean:
        for name in ("build", "dist"):
            shutil.rmtree(_ROOT / name, ignore_errors=True)
        print("已清理 build/ 与 dist/")
    assert_ready(_ROOT / "data")
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm",
        "--distpath", str(dist_dir),
        "--workpath", str(_ROOT / "build"),
        str(SPEC),
    ]
    if clean:
        cmd.insert(3, "--clean")
    print("运行：{0}".format(" ".join(cmd)))
    return subprocess.call(cmd, cwd=str(_ROOT)), dist_dir


def _exe_path(dist_dir, name):
    """PyInstaller 6 onedir 为 ``dist/<name>/<name>.exe``；5 平铺为 ``dist/<name>.exe``。"""
    candidate = Path(dist_dir) / name / "{0}.exe".format(name)
    if candidate.is_file():
        return candidate.parent
    flat = Path(dist_dir) / "{0}.exe".format(name)
    if flat.is_file():
        return Path(dist_dir)
    return Path(dist_dir) / name


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="构建 onedir 双 exe（GUI + CLI）")
    parser.add_argument("--clean", action="store_true", help="构建前清理 build/ 与 dist/")
    parser.add_argument("--no-verify", action="store_true", help="构建后不跑校验")
    parser.add_argument("--dist", default=None, metavar="DIR", help="dist 输出目录（默认 dist/）")
    args = parser.parse_args(argv)

    code, dist_dir = build(clean=args.clean, dist_dir=args.dist)
    if code != 0:
        sys.stderr.write("构建失败（PyInstaller 退出码 {0}）\n".format(code))
        return code

    gui_dir = _exe_path(dist_dir, GUI_EXE_NAME)
    cli_dir = _exe_path(dist_dir, CLI_EXE_NAME)
    print("产物：\n  GUI: {0}\n  CLI: {1}".format(
        gui_dir / "{0}.exe".format(GUI_EXE_NAME), cli_dir / "{0}.exe".format(CLI_EXE_NAME)))

    if args.no_verify:
        print("已跳过校验（--no-verify）")
        return 0

    # GUI exe 为窗口版（console=False），用 --selftest 写文件方式做冻结态实跑；
    # CLI exe 为控制台版，用 selfcheck --json 直接管道取结果。
    gui_live = verify_dist(gui_dir, exe_name=GUI_EXE_NAME, run=True, gui_selftest=True)
    cli_live = verify_dist(cli_dir, exe_name=CLI_EXE_NAME, run=True)
    for label, result in (("GUI（冻结态实跑）", gui_live), ("CLI（冻结态实跑）", cli_live)):
        print("[{0}] {1}：data_dir={2} inside_dist={3} frozen={4} rules={5}".format(
            label, "通过" if result["ok"] else "未通过", result["data_dir"],
            result["inside_dist"], result["frozen"], result["verified_rule_count"]))
        for problem in result["problems"]:
            sys.stderr.write("  - {0}\n".format(problem))
    return 0 if (gui_live["ok"] and cli_live["ok"]) else 1


if __name__ == "__main__":
    sys.exit(main())
