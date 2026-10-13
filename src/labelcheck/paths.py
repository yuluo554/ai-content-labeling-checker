"""数据目录定位（冻结态失真的唯一防线）。

优先级（**既定口径**，改动会打挂测试，见 plan/03 §六 / plan/04 §十）：

1. 显式参数 ``explicit``
2. 环境变量 ``LABELCHECK_DATA_DIR``（空串视为未设置）
3. 冻结态内嵌（PyInstaller）：
   - PyInstaller 6：``sys._MEIPASS/data``
   - PyInstaller 5 平铺：``<exe目录>/_internal/data`` 或 ``<exe目录>/data``
4. 源码态：从 ``__file__`` 上溯找含 ``rules/registry.json`` 的仓库 ``data/``；
   再兜底 CWD 上溯。

**验伪要点**：冻结态自检必须断言解析到的目录落在 dist 之内；落到仓库
``data/`` 说明内嵌数据"验了个寂寞"（系列实测假结果陷阱）。
"""

import os
import sys
from pathlib import Path

from .errors import EnvironmentError_

ENV_VAR = "LABELCHECK_DATA_DIR"

#: 数据目录的识别标志（同时用于源码态上溯与冻结态校验）
SENTINEL = Path("rules") / "registry.json"


def _looks_like_data_dir(path):
    """目录是否像一个数据根（含 rules/registry.json）。"""
    if path is None:
        return False
    try:
        return (Path(path) / SENTINEL).is_file()
    except OSError:
        return False


def _frozen_candidates():
    """PyInstaller 冻结态候选数据目录（按优先级）。"""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        # PyInstaller 6 单目录/单文件内嵌布局
        candidates.append(Path(meipass) / "data")
    exe_dir = Path(sys.executable).parent
    # PyInstaller 5 平铺布局（无 _internal/）
    candidates.append(exe_dir / "_internal" / "data")
    # onedir 变体
    candidates.append(exe_dir / "data")
    return candidates


def _source_candidates():
    """源码态候选数据目录（仓库树内的 data/）。"""
    here = Path(__file__).resolve()
    # src/labelcheck/paths.py → 上溯到仓库根
    for parent in list(here.parents)[:6]:
        candidate = parent / "data"
        if _looks_like_data_dir(candidate):
            return [candidate]
    return []


def _cwd_candidates():
    """兜底：从当前工作目录上溯。"""
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return []
    for parent in [cwd] + list(cwd.parents)[:5]:
        candidate = parent / "data"
        if _looks_like_data_dir(candidate):
            return [candidate]
    return []


def find_data_dir(explicit=None, require=True):
    """定位数据目录，返回绝对 :class:`pathlib.Path`。

    :param explicit: 显式指定的数据目录（字符串或 Path），优先级最高。
    :param require: 为 True 时定位失败抛 :class:`EnvironmentError_`（exit 3）。
    :raises EnvironmentError_: 定位失败且 ``require=True``。
    """
    if explicit:
        path = Path(explicit).expanduser()
        if _looks_like_data_dir(path):
            return path.resolve()
        # 显式指定但内容不符：仍然返回（调用方可能用非标准数据目录），
        # 仅在 require 且完全不存在时报错。
        if path.is_dir():
            return path.resolve()
        if require:
            raise EnvironmentError_(
                "显式指定的数据目录不可用（缺少 {0}）：{1}".format(SENTINEL.as_posix(), path)
            )
        return path.resolve()

    env_value = os.environ.get(ENV_VAR, "").strip()
    if env_value:
        path = Path(env_value).expanduser()
        if path.is_dir():
            return path.resolve()
        if require:
            raise EnvironmentError_(
                "环境变量 {0} 指向的目录不存在：{1}".format(ENV_VAR, path)
            )

    for candidate in _frozen_candidates() + _source_candidates() + _cwd_candidates():
        if _looks_like_data_dir(candidate):
            return candidate.resolve()

    if require:
        raise EnvironmentError_(
            "无法定位数据目录：请用 --data-dir 指定、或设置环境变量 {0}、"
            "或从仓库根运行。".format(ENV_VAR)
        )
    return None


def is_frozen():
    """当前是否运行在 PyInstaller 冻结态。"""
    return bool(getattr(sys, "frozen", False))


__all__ = ["find_data_dir", "is_frozen", "ENV_VAR", "SENTINEL"]
