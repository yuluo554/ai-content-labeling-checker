# -*- coding: utf-8 -*-
"""内置评测基准（FR-11，契约见 plan/04 §九）。

三类基准，**零 API 依赖、纯规则通路**，一条命令跑全（CLI ``bench``）：

============  ====================================================  ==================
基准           内容                                                   指标（达标线）
============  ====================================================  ==================
``fields``     逐 ``check_type`` 的边界/畸形用例（存在性/位置/格式/    判定准确率（100%）
               取值/类型/唯一性/场景门控）
``constructed`` 程序化构造带**已知标识配置**的合成件                   检出率（≥0.95）
                                                                       误报率（=0）
``diff``       两轮扫描对账的确定性验证                                 对账集合一致率（100%）
============  ====================================================  ==================

**为什么需要它**（FR-11 的动因）：没有标注数据，核验正确性无法证明。本模块把"规则库 +
引擎"的正确性做成**可重复、可对照、零外部依赖**的指标——指标进 README，任何人可复现。

**口径纪律**：

- **单一实现源**：三类基准的算例与对账口径都在 :mod:`.cases`——真值库对账测试
  （``tests/test_generators.py``）与解析回归（``tests/test_parse_regression.py``）
  与基准共用同一套 :func:`~labelcheck.benchmark.cases.observed_nonpass` /
  :func:`~labelcheck.benchmark.cases.compare_nonpass`，不会出现"基准说达标、测试说不过"；
- **不许改真值凑引擎**：期望值由注入点/规则库语义推出，不抄引擎输出；
- **复用既有真值**：``data/truth/``（标识卡算例）与 ``data/parse/fixtures.json``
  （容器算例）是现成算例，基准不另造一套（各自的回归测试仍逐例跑）；
- **零时钟**：产物无时间戳（NFR-3 同一条纪律）。

退出码（CLI ``bench``）：``0`` 全部达标 / ``1`` 有基准未达标 / ``2`` 用法错误。
"""

import shutil
import tempfile

from .cases import load_ruleset_and_mapping
from .metrics import (
    OP_AT_LEAST, OP_AT_MOST, BenchReport, Metric, SuiteResult, rate,
)
from .runner_constructed import run as _run_constructed
from .runner_diff import run as _run_diff
from .runner_fields import run as _run_fields

#: 三类基准名（顺序固定 = 报告与 README 表格顺序）
BENCH_NAMES = ("fields", "constructed", "diff")

#: 基准名 → 说明（CLI 帮助与报告用）
BENCH_TITLES = {
    "fields": "字段规则基准（逐 check_type 的边界/畸形用例判定准确率）",
    "constructed": "构造真值基准（已知标识配置的合成件：检出率 / 误报率）",
    "diff": "两轮对账基准（三类集合完全一致）",
}


def run_benchmark(data_dir, only=None, work_dir=None):
    """跑内置基准，返回 :class:`~labelcheck.benchmark.metrics.BenchReport`。

    :param data_dir: 数据目录（规则库 + 映射表所在）
    :param only: 只跑指定基准（``None`` = 全跑）；未知名字抛 :class:`ValueError`
    :param work_dir: 合成数据目录的父目录（``None`` = 临时目录，跑完即清理）

    ``fields`` / ``diff`` 用**仓库规则库**跑；``constructed`` 另需两个合成数据目录
    （引擎分支用例：未映射字段 / 无适用规则）——在 ``work_dir`` 下临时构造，不污染仓库。
    """
    selected = _select(only)
    ruleset, mapping = load_ruleset_and_mapping(data_dir)

    cleanup = None
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix="labelcheck-bench-")
        cleanup = work_dir
    try:
        synthetic_dirs = None
        if "constructed" in selected:
            from .cases import build_synthetic_data_dirs

            synthetic_dirs = build_synthetic_data_dirs(work_dir)

        suites = []
        for name in selected:
            if name == "fields":
                suites.append(_run_fields(ruleset, mapping, data_dir))
            elif name == "constructed":
                suites.append(_run_constructed(ruleset, mapping, data_dir, synthetic_dirs))
            elif name == "diff":
                suites.append(_run_diff(ruleset, data_dir))
    finally:
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)

    return BenchReport(
        suites=suites,
        data_dir=str(data_dir),
        coordinate=ruleset.coordinate,
        only=list(selected),
    )


def _select(only):
    """把 ``only`` 归一为基准名列表（保序去重）；未知名字报错（不静默跳过）。"""
    if only is None:
        return list(BENCH_NAMES)
    if isinstance(only, str):
        only = [only]
    selected = []
    for name in only:
        if name not in BENCH_NAMES:
            raise ValueError(
                "未知基准名：{0!r}（可选 {1}）".format(name, "/".join(BENCH_NAMES)))
        if name not in selected:
            selected.append(name)
    return selected


def parse_only(value):
    """把 ``--only a,b`` 的字符串解析为基准名列表（供 CLI 使用）。"""
    if value is None:
        return None
    names = [item.strip() for item in value.split(",") if item.strip()]
    return names or None


__all__ = [
    "BENCH_NAMES", "BENCH_TITLES", "run_benchmark", "parse_only",
    "BenchReport", "SuiteResult", "Metric", "rate", "OP_AT_LEAST", "OP_AT_MOST",
    "load_ruleset_and_mapping",
]