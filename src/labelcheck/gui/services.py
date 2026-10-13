# -*- coding: utf-8 -*-
"""GUI 服务层：**唯一**的引擎调用点（零 Qt、零判定逻辑）。

分层纪律（plan/03 §一 分层图）：GUI 是**薄表现层**，只渲染引擎结果。本模块把
``engine`` / ``scan`` / ``benchmark`` / ``rules`` 的返回值整理成 Qt 层可直接使用的
**纯数据**；此处**不得**出现任何判定、分级、分派或对账逻辑——那些口径只存在于引擎，
GUI 复制一份就会与 CLI 给出不同结论（最隐蔽的口径漂移）。

**为什么单独一层**（而不是把调用写进 Qt 控件）：

1. Qt 控件难以在无显示环境里做细粒度断言；把"调引擎 + 整理数据"与"画控件"分开后，
   本模块用普通 pytest 即可全覆盖（无需 ``QApplication``）；
2. 本模块**零第三方依赖**，``import labelcheck.gui.services`` 在没有 PySide6 的机器上
   也能跑——GUI 依赖缺失时只有 Qt 层失败，不会连累服务层测试与 CLI。

调用点与 CLI 完全同源（``engine.check_file`` / ``scan.scan_target`` / ``scan.diff_scans`` /
``benchmark.run_benchmark``），保证"同一输入，界面与命令行结论一致"。
"""

from pathlib import Path

from ..benchmark import run_benchmark
from ..engine import check_file
from ..errors import LabelCheckError
from ..jsonio import load_json
from ..mapping import load_mapping_table
from ..model import SCENARIOS
from ..paths import find_data_dir
from ..rules import effective_ruleset
from ..scan import ScanResult, diff_scans, scan_target

#: 场景的展示名（GUI 下拉框用；**数值口径仍是** :data:`labelcheck.model.SCENARIOS` 的英文枚举）。
#: 仅作界面文案，不参与任何判定——判定用的场景值原样传给引擎。
SCENARIO_LABELS = {
    "authored": "产出/交付（authored）",
    "exported": "导出/下载（exported）",
    "propagated": "网络传播（propagated）",
}

#: 下拉框"不覆盖卡内声明"选项的哨兵值（映射为引擎的 ``scenario=None``）。
SCENARIO_FROM_CARD = "__from_card__"


def scenario_options():
    """GUI 下拉框选项：``[(显示名, 传给引擎的值)]``（首项 = 用卡内声明）。"""
    options = [("用卡内声明", SCENARIO_FROM_CARD)]
    for name in SCENARIOS:
        options.append((SCENARIO_LABELS.get(name, name), name))
    return options


def normalize_scenario(value):
    """把下拉框取值归一为引擎参数（哨兵 → ``None``）。"""
    if value in (None, "", SCENARIO_FROM_CARD):
        return None
    return value


class SingleCheckResult(object):
    """单件核验的服务层结果（引擎对象 + 输入路径，纯数据）。"""

    __slots__ = ("path", "report", "parse")

    def __init__(self, path, report, parse=None):
        self.path = str(path)
        self.report = report
        self.parse = parse

    @property
    def card_id(self):
        return self.report.card_id

    @property
    def grade(self):
        return self.report.grade

    @property
    def has_violation(self):
        return self.report.has_violation

    @property
    def unobserved_scopes(self):
        return self.report.unobserved_scopes

    @property
    def parsed_from_container(self):
        """本次是否走解析通路（容器文件）。"""
        return self.parse is not None

    def __repr__(self):
        return "SingleCheckResult(path={0!r}, grade={1!r})".format(self.path, self.grade)


class BatchScanResult(object):
    """批量扫描的服务层结果（含可选两轮对账）。"""

    __slots__ = ("result", "diff", "out_dir", "written")

    def __init__(self, result, diff=None, out_dir="", written=None):
        self.result = result
        self.diff = diff
        self.out_dir = str(out_dir) if out_dir else ""
        self.written = list(written or [])

    @property
    def summary(self):
        return self.result.summary

    def __repr__(self):
        return "BatchScanResult(items={0}, diff={1})".format(
            len(self.result.items), self.diff is not None)


class RulesOverview(object):
    """规则库与依据的服务层结果。"""

    __slots__ = ("data_dir", "ruleset", "mapping_table")

    def __init__(self, data_dir, ruleset, mapping_table):
        self.data_dir = str(data_dir)
        self.ruleset = ruleset
        self.mapping_table = mapping_table

    def __repr__(self):
        return "RulesOverview(data_dir={0!r}, verified={1})".format(
            self.data_dir, self.ruleset.verified_rule_count)


# ------------------------------------------------------------------ 调用点
def resolve_data_dir(explicit=None):
    """定位数据目录（与 CLI 同一 :func:`labelcheck.paths.find_data_dir` 四分支）。"""
    return find_data_dir(explicit)


def check_single(path, data_dir, scenario=None, generated_at=""):
    """单件核验：**只调** ``engine.check_file``（单件/批量共用分派，plan/06 D32）。

    :raises LabelCheckError: 文件不存在 / 既非标识卡也非容器（调用方转成界面提示）。
    """
    report, parse_outcome = check_file(
        path, data_dir, generated_at=generated_at, scenario=normalize_scenario(scenario))
    return SingleCheckResult(path, report, parse=parse_outcome)


def scan_batch(target, data_dir, scenario=None, generated_at="", baseline=None,
               progress_every=0):
    """批量扫描（可选带两轮对账）：**只调** ``scan.scan_target`` + ``scan.diff_scans``。

    :param baseline: 上轮 ``ScanResult`` 对象（``None`` = 不做对账）。
    """
    result = scan_target(
        target, data_dir, generated_at=generated_at,
        scenario=normalize_scenario(scenario), progress_every=progress_every)
    diff = None
    if baseline is not None:
        diff = diff_scans(baseline, result, generated_at=generated_at)
    return BatchScanResult(result, diff=diff)


def load_baseline(path):
    """读上轮 ``ScanResult`` JSON（``scan --json`` 的产物）→ :class:`ScanResult`。

    :raises LabelCheckError: 文件不可读或不是合法 ``ScanResult``（缺 ``items``）。
    """
    from ..errors import UsageError

    payload = load_json(path, error_cls=UsageError)
    if not isinstance(payload, dict) or "items" not in payload:
        raise UsageError("上轮结果不是合法 ScanResult JSON（缺 items）：{0}".format(path))
    return ScanResult.from_dict(payload)


def diff_files(previous_path, current_path, generated_at=""):
    """两轮对账（**独立通路**）：读两份 ``ScanResult`` JSON → ``diff_scans`` → ``DiffResult``。

    与 :func:`scan_batch` 的 ``baseline`` 参数是**同一引擎入口**（``scan.diff_scans``），
    区别只在于输入来源：这里直接吃两份已导出的结果文件（不必重扫），
    供"两轮对账"页签单独使用。

    :raises LabelCheckError: 任一文件不是合法 ``ScanResult`` JSON。
    """
    previous = load_baseline(previous_path)
    current = load_baseline(current_path)
    return diff_scans(previous, current, generated_at=generated_at)


def export_report(batch, out_dir, generated_at="", include_xlsx=True):
    """把批量结果导出为报告产物（**只调** ``report.write_report``）。

    返回写出路径列表；缺 ``openpyxl`` 时自动降级为 CSV（引擎层既定行为，不在此重写）。
    """
    from ..report import write_report

    _bundle, written = write_report(
        batch.result, out_dir, generated_at=generated_at, diff=batch.diff,
        include_xlsx=include_xlsx)
    batch.out_dir = str(out_dir)
    batch.written = list(written)
    return list(written)


def run_bench(data_dir, only=None):
    """跑内置基准：**只调** ``benchmark.run_benchmark``（三类 runner 的唯一入口）。"""
    return run_benchmark(data_dir, only=only)


def rules_overview(data_dir):
    """规则库 + 映射表概览（供"规则库与依据"页签渲染）。"""
    ruleset = effective_ruleset(data_dir)
    table = load_mapping_table(data_dir)
    return RulesOverview(data_dir, ruleset, table)


def is_labelcheck_error(exc):
    """异常是否为本工具的可预期错误（界面提示 vs. 内部缺陷的分流）。"""
    return isinstance(exc, LabelCheckError)


__all__ = [
    "SCENARIO_LABELS", "SCENARIO_FROM_CARD",
    "scenario_options", "normalize_scenario", "is_labelcheck_error",
    "SingleCheckResult", "BatchScanResult", "RulesOverview",
    "resolve_data_dir", "check_single", "scan_batch", "load_baseline", "diff_files",
    "export_report", "run_bench", "rules_overview",
]
