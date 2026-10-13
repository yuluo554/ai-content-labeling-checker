# -*- coding: utf-8 -*-
"""基准指标与达标判定（FR-11，契约见 plan/04 §九）。

指标形态只有两种，达标方向**必须显式**给出：

- **越大越好**（``op=">="``）：判定准确率、检出率、对账集合一致率；
- **越小越好**（``op="<="``）：误报率（目标 0）。

"误报率越低越好"不能靠单一 ``>=`` 糊过去——故 :class:`Metric` 把**方向与阈值**一并固化，
``bench`` 的达标判定、``bench --json`` 与 README 指标表共用同一份指标对象，
避免"文档一个数、程序另一个数"。

**零时钟**：本模块不读系统时钟（NFR-3 的同一条纪律——产物不得带时刻）。
"""

#: 达标方向：越大越好 / 越小越好
OP_AT_LEAST = ">="
OP_AT_MOST = "<="
_OPERATORS = (OP_AT_LEAST, OP_AT_MOST)


def rate(numerator, denominator, empty=1.0):
    """比率；分母为 0 时返回 ``empty``（默认 1.0 = "没有可失败的对象"）。

    "0 个样本"不等于"全错"，也不等于"全对"——调用方必须显式声明空集口径，
    故此处把 ``empty`` 作为参数暴露，而不是隐式定死。
    """
    if denominator <= 0:
        return empty
    return float(numerator) / float(denominator)


class Metric(object):
    """一条基准指标（名称 + 实测值 + 达标方向 + 阈值）。

    :param name: 指标名（进 README 表格与 ``bench --json``）
    :param value: 实测值（比率 ∈ [0,1]，或计数）
    :param target: 阈值；``None`` = 仅展示、不参与达标判定
    :param op: 达标方向（:data:`OP_AT_LEAST` / :data:`OP_AT_MOST`）
    :param detail: 人类可读补充（如 ``"19/19 例"``）
    :param percent: 展示时是否按百分比格式化
    """

    __slots__ = ("name", "value", "target", "op", "detail", "percent")

    def __init__(self, name, value, target=None, op=OP_AT_LEAST, detail="", percent=True):
        if op not in _OPERATORS:
            raise ValueError("非法达标方向：{0!r}（须为 {1}）".format(op, "/".join(_OPERATORS)))
        self.name = name
        self.value = value
        self.target = target
        self.op = op
        self.detail = detail
        self.percent = percent

    @property
    def passed(self):
        """是否达标（无阈值 = 仅展示，恒视为达标）。"""
        if self.target is None:
            return True
        if self.op == OP_AT_LEAST:
            return self.value >= self.target
        return self.value <= self.target

    def _fmt(self, value):
        if value is None:
            return "-"
        if self.percent:
            return "{0:.2f}%".format(value * 100.0)
        return "{0}".format(value)

    @property
    def display(self):
        """实测值的人类可读形态。"""
        return self._fmt(self.value)

    @property
    def requirement(self):
        """达标要求的可读形态（``">= 95.00%"``）。"""
        if self.target is None:
            return "（仅展示）"
        return "{0} {1}".format(self.op, self._fmt(self.target))

    def to_dict(self):
        return {
            "name": self.name,
            "value": self.value,
            "target": self.target,
            "op": self.op,
            "passed": self.passed,
            "detail": self.detail,
        }

    def __repr__(self):
        return "Metric({0}={1}, {2} {3}, passed={4})".format(
            self.name, self.display, self.op, self._fmt(self.target), self.passed)


class SuiteResult(object):
    """一类基准的运行结果（指标 + 用例计数 + 失败明细）。

    :param name: 基准名（``fields`` / ``constructed`` / ``diff``）
    :param title: 人类可读标题
    :param metrics: :class:`Metric` 列表（顺序固定）
    :param cases_total: 参与判定的用例数
    :param cases_passed: 通过用例数
    :param failures: 失败用例的描述列表（顺序 = 用例声明序）
    :param notes: 运行说明（如"某类规则在当前规则库中不存在，未生成用例"）
    :param skipped: 因数据不足而未生成的用例（不静默吞掉）
    """

    __slots__ = ("name", "title", "metrics", "cases_total", "cases_passed",
                 "failures", "notes", "skipped")

    def __init__(self, name, title, metrics=None, cases_total=0, cases_passed=0,
                 failures=None, notes=None, skipped=None):
        self.name = name
        self.title = title
        self.metrics = list(metrics or [])
        self.cases_total = cases_total
        self.cases_passed = cases_passed
        self.failures = list(failures or [])
        self.notes = list(notes or [])
        self.skipped = list(skipped or [])

    @property
    def passed(self):
        """全部指标达标且无失败用例。"""
        return all(metric.passed for metric in self.metrics) and not self.failures

    def to_dict(self):
        return {
            "name": self.name,
            "title": self.title,
            "passed": self.passed,
            "cases_total": self.cases_total,
            "cases_passed": self.cases_passed,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "failures": list(self.failures),
            "notes": list(self.notes),
            "skipped": list(self.skipped),
        }

    def __repr__(self):
        return "SuiteResult({0}, passed={1}, cases={2}/{3})".format(
            self.name, self.passed, self.cases_passed, self.cases_total)


class BenchReport(object):
    """三类基准的汇总结果（``bench`` 子命令与 README 指标表的共同来源）。"""

    SCHEMA_VERSION = 1

    def __init__(self, suites, data_dir="", coordinate="", only=None):
        self.suites = list(suites)
        self.data_dir = data_dir
        self.coordinate = coordinate
        self.only = list(only) if only else []

    @property
    def passed(self):
        """全部基准达标（决定 ``bench`` 退出码 0/1）。"""
        return all(suite.passed for suite in self.suites)

    def suite(self, name):
        for item in self.suites:
            if item.name == name:
                return item
        return None

    @property
    def metrics(self):
        """扁平化指标列表（``(suite_name, Metric)``，顺序固定）。"""
        out = []
        for suite in self.suites:
            for metric in suite.metrics:
                out.append((suite.name, metric))
        return out

    @property
    def failures(self):
        out = []
        for suite in self.suites:
            for line in suite.failures:
                out.append("[{0}] {1}".format(suite.name, line))
        return out

    def to_dict(self):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "passed": self.passed,
            "data_dir": self.data_dir,
            "ruleset_coordinate": self.coordinate,
            "only": list(self.only),
            "suites": [suite.to_dict() for suite in self.suites],
        }

    def __repr__(self):
        return "BenchReport(passed={0}, suites={1})".format(
            self.passed, [suite.name for suite in self.suites])


__all__ = [
    "OP_AT_LEAST", "OP_AT_MOST", "rate", "Metric", "SuiteResult", "BenchReport",
]