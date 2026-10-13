# -*- coding: utf-8 -*-
"""打包支持（PyInstaller onedir 双 exe）：**白名单内嵌数据 + 构建后校验**。

契约见 plan/03 §六 / plan/04 §十二。本模块**顶层零 PyInstaller 依赖**（PyInstaller 只在
``build_*.py`` 脚本与 spec 里用），故可被无 ``pkg`` extra 的环境导入与测试。

**为什么必须"白名单"而不是"整仓 data/ 都塞进去"**：``data/`` 里既有运行必需的资产
（规则库/映射表/真值库/解析算例/样本/依据快照），也可能有本地私有件
（``data/**/_private/``，见 .gitignore）与报告输出目录。一律内嵌会把不该发布的文件
打进 exe（体积 + 泄露），故只内嵌**明确的运行必需子目录**，并由
:func:`verify_dist` 在**构建后**断言"解析到的数据目录落在 dist 之内"。

**验伪要点（系列实测假结果陷阱）**：冻结态若"验了个寂寞"——即自检实际读到了**仓库**
``data/`` 而非 dist 内嵌数据——exe 看着能跑，换台机器就崩。故 :func:`verify_dist`
必须同时检查：① 数据目录存在；② 其**真实路径落在 dist 之内**；③ 哨兵文件
``rules/registry.json`` 可读且解析出的规则数 > 0。干净验证还须在**中立目录** +
``env -i``（清空环境变量）下跑，避免 ``LABELCHECK_DATA_DIR`` 或 CWD 上溯"兜底命中"。
"""

import os
import subprocess
import sys
from pathlib import Path

from ..errors import EnvironmentError_
from ..paths import ENV_VAR, SENTINEL, find_data_dir

#: 内嵌进 dist 的数据子目录（**白名单**；顺序固定 → 构建可复现）。
#: 每个都是运行期真正会被读到的资产；``_private/`` 等本地件**不在此列**。
DATA_SUBDIRS = ("rules", "mapping", "truth", "parse", "samples", "knowledge")

#: dist 内的数据挂载点（PyInstaller 的 ``--add-data`` 目标目录）。
DIST_DATA_DIRNAME = "data"

#: 双 exe 的名字（onedir 下是 ``<name>.exe``）
GUI_EXE_NAME = "labelcheck-gui"
CLI_EXE_NAME = "labelcheck"

#: 冻结态自检子命令（GUI exe 与 CLI exe 都支持；CLI exe 用它做无显示冒烟）
SELFCHECK_ARGS = ("selfcheck", "--json")

#: GUI exe 的自检参数（窗口版 stdout 不接终端 → 结果写文件；见 tools/entry_gui.py）
GUI_SELFTEST_FLAG = "--selftest"


def default_dist_dir(root=None):
    """默认 dist 目录（仓库根的 ``dist/``；已被 .gitignore 排除）。"""
    root = Path(root) if root else repo_root()
    return root / "dist"


def repo_root():
    """仓库根（``src/labelcheck/packaging/__init__.py`` 上溯三级）。"""
    return Path(__file__).resolve().parents[3]


def build_datas(data_dir=None, root=None):
    """构造 PyInstaller ``datas`` 白名单：``[(源路径, dist 内相对目录)]``。

    只包含 :data:`DATA_SUBDIRS` 中**实际存在**的子目录；缺一个就少一个（构建脚本会
    通过 :func:`missing_data_subdirs` 显式报缺，不静默放过）。

    :param data_dir: 源数据目录（缺省 = 仓库 ``data/``）
    :param root: 仓库根（用于定位默认数据目录）
    """
    root = Path(root) if root else repo_root()
    data_dir = Path(data_dir) if data_dir else root / "data"
    datas = []
    for name in DATA_SUBDIRS:
        source = data_dir / name
        if source.is_dir():
            datas.append((str(source), "{0}/{1}".format(DIST_DATA_DIRNAME, name)))
    return datas


def missing_data_subdirs(data_dir=None, root=None):
    """白名单里**缺失**的子目录（构建前显式报缺，不静默少打包）。"""
    root = Path(root) if root else repo_root()
    data_dir = Path(data_dir) if data_dir else root / "data"
    return [name for name in DATA_SUBDIRS if not (data_dir / name).is_dir()]


def datas_manifest(datas):
    """把 ``datas`` 归一为可断言的清单：``{子目录名: 源绝对路径}``。"""
    manifest = {}
    for source, target in datas:
        name = Path(target).name
        manifest[name] = str(Path(source).resolve())
    return manifest


def _is_within(path, parent):
    """``path`` 是否落在 ``parent`` 之内（两者都先 resolve；跨盘符返回 False）。"""
    try:
        path = Path(path).resolve()
        parent = Path(parent).resolve()
    except OSError:
        return False
    if path == parent:
        return True
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def verify_dist(dist_dir, exe_name=CLI_EXE_NAME, run=True, timeout=120, gui_selftest=False):
    """**构建后校验**：dist 内嵌数据是否真的落在 dist 之内且可用。

    返回一个结果 dict（``to_dict`` 可直接进 CI 日志 / 证据）：

    - ``dist``：dist 目录绝对路径；
    - ``data_dir``：冻结态定位到的数据目录；
    - ``inside_dist``：数据目录是否**落在 dist 之内**（验伪的核心断言）；
    - ``frozen``：子进程是否报告冻结态；
    - ``verified_rule_count`` / ``pending_rule_count``：自检读到的规则计数；
    - ``ok``：全部断言通过；
    - ``problems``：不通过的原因清单（空 = 通过）。

    :param run: 是否真跑 exe 的自检（``False`` = 只做静态路径检查，供无 exe 的单元测试使用）。
    :param gui_selftest: 为 True 时用 GUI exe 的 ``--selftest <file>``（窗口版 stdout 不接
        终端，结果写文件），而不是 CLI 的 ``selfcheck --json``。
    """
    dist_dir = Path(dist_dir).resolve()
    problems = []
    result = {
        "dist": str(dist_dir),
        "exe": str(dist_dir / "{0}.exe".format(exe_name)),
        "data_dir": "",
        "inside_dist": False,
        "frozen": False,
        "verified_rule_count": 0,
        "pending_rule_count": 0,
        "ok": False,
        "problems": problems,
    }

    embedded = dist_dir / DIST_DATA_DIRNAME
    if not embedded.is_dir():
        # PyInstaller 6 onedir 把数据放在 _internal/ 下
        embedded = dist_dir / "_internal" / DIST_DATA_DIRNAME
    if not (embedded / SENTINEL).is_file():
        problems.append("dist 内未找到内嵌数据（缺 {0}）：{1}".format(
            SENTINEL.as_posix(), embedded))
        return result

    result["data_dir"] = str(embedded)
    result["inside_dist"] = _is_within(embedded, dist_dir)
    if not result["inside_dist"]:
        problems.append("内嵌数据目录不在 dist 之内：{0}".format(embedded))

    if not run:
        result["ok"] = not problems
        return result

    exe = dist_dir / "{0}.exe".format(exe_name)
    if not exe.is_file():
        problems.append("可执行文件不存在：{0}".format(exe))
        return result

    if gui_selftest:
        payload, run_problems = _run_gui_selftest(exe, timeout=timeout)
    else:
        payload, run_problems = _run_selfcheck(exe, timeout=timeout)
    problems.extend(run_problems)
    if payload is not None:
        result["frozen"] = bool(payload.get("frozen"))
        result["data_dir"] = payload.get("data_dir", result["data_dir"])
        result["inside_dist"] = _is_within(result["data_dir"], dist_dir)
        result["verified_rule_count"] = payload.get("verified_rule_count", 0)
        result["pending_rule_count"] = payload.get("pending_rule_count", 0)
        if not result["frozen"]:
            problems.append("子进程未报告冻结态（exe 未真正以冻结态运行）")
        if not result["inside_dist"]:
            problems.append(
                "冻结态解析到的数据目录**不在 dist 之内**（验了个寂寞）：{0}".format(
                    result["data_dir"]))
        if result["verified_rule_count"] <= 0:
            problems.append("冻结态生效规则数为 0（内嵌数据不可用）")
        for problem in payload.get("problems", []) or []:
            problems.append("GUI 自检：{0}".format(problem))

    result["ok"] = not problems
    return result


def _run_selfcheck(exe, timeout=120):
    """在**中立环境**下跑 ``<exe> selfcheck --json``（清空 LABELCHECK_DATA_DIR 等）。

    中立环境是验伪的前提：若沿用当前环境变量（尤其 ``LABELCHECK_DATA_DIR``）或
    从仓库根启动，冻结态自检会**兜底命中仓库 data/**，看起来通过、实际没验到内嵌数据。
    """
    import json

    env = dict(os.environ)
    env.pop(ENV_VAR, None)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            [str(exe)] + list(SELFCHECK_ARGS),
            cwd=str(Path(exe).parent),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, ["无法运行冻结态自检：{0}".format(exc)]

    stdout = completed.stdout.decode("utf-8", "replace")
    stderr = completed.stderr.decode("utf-8", "replace")
    if completed.returncode != 0:
        return None, ["冻结态自检退出码 {0}（stderr：{1}）".format(
            completed.returncode, stderr.strip()[:400])]
    try:
        payload = json.loads(stdout)
    except ValueError:
        return None, ["冻结态自检输出不是 JSON：{0}".format(stdout.strip()[:400])]
    return payload, []


def neutral_env(env=None):
    """构造中立环境（去掉数据目录相关变量）；供构建脚本与验证脚本共用。"""
    result = dict(os.environ if env is None else env)
    result.pop(ENV_VAR, None)
    result["PYTHONIOENCODING"] = "utf-8"
    return result


def _run_gui_selftest(exe, timeout=120):
    """在**中立环境**下跑 ``<exe> --selftest <tmp.json>``（GUI 窗口版专用）。

    GUI exe 为 ``console=False``，stdout 不接终端，故自检结果写临时 JSON 文件。
    """
    import json
    import tempfile

    env = neutral_env()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    tmp_dir = Path(tempfile.mkdtemp(prefix="labelcheck-gui-selftest-"))
    out_path = tmp_dir / "selftest.json"
    try:
        completed = subprocess.run(
            [str(exe), GUI_SELFTEST_FLAG, str(out_path)],
            cwd=str(Path(exe).parent),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, ["无法运行 GUI 冻结态自检：{0}".format(exc)]

    if not out_path.is_file():
        stderr = completed.stderr.decode("utf-8", "replace").strip()[:400]
        return None, ["GUI 自检未产出结果文件（退出码 {0}；stderr：{1}）".format(
            completed.returncode, stderr)]
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    except ValueError:
        return None, ["GUI 自检结果不是 JSON：{0}".format(out_path)]
    problems = []
    if completed.returncode != 0:
        problems.append("GUI 自检退出码 {0}".format(completed.returncode))
    return payload, problems


def assert_ready(data_dir=None, root=None):
    """构建前置检查：白名单子目录齐全 + 哨兵文件存在；否则抛 :class:`EnvironmentError_`。"""
    root = Path(root) if root else repo_root()
    data_dir = Path(data_dir) if data_dir else root / "data"
    missing = missing_data_subdirs(data_dir)
    if missing:
        raise EnvironmentError_(
            "数据目录缺少白名单子目录（构建会漏打包）：{0}".format("、".join(missing)))
    if not (data_dir / SENTINEL).is_file():
        raise EnvironmentError_("数据目录缺少哨兵文件：{0}".format(SENTINEL.as_posix()))
    return data_dir


def frozen_data_dir_hint():
    """冻结态数据目录的候选提示（诊断用；真实定位仍走 :func:`find_data_dir`）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return str(Path(meipass) / DIST_DATA_DIRNAME)
    return str(Path(sys.executable).parent / "_internal" / DIST_DATA_DIRNAME)


__all__ = [
    "DATA_SUBDIRS", "DIST_DATA_DIRNAME", "GUI_EXE_NAME", "CLI_EXE_NAME", "SELFCHECK_ARGS",
    "GUI_SELFTEST_FLAG",
    "repo_root", "default_dist_dir", "build_datas", "missing_data_subdirs",
    "datas_manifest", "verify_dist", "neutral_env", "assert_ready",
    "frozen_data_dir_hint",
]
