# -*- coding: utf-8 -*-
"""内置基准运行测试（FR-11，契约见 plan/04 §九）。

锁死四件事：

1. **三类基准在仓库真实数据上全部达标**：判定准确率 100%、检出率 ≥0.95、误报率 0、
   对账集合一致率 100%；
2. **指标形态正确**：误报率是"越小越好"（``op="<="``），检出率/准确率是"越大越好"；
3. **确定性**：同一输入两次跑 ``to_dict`` 逐字节一致（基准可复现）；
4. **失败可诊断**：注入一个不达标条件时，报告**列出具体失败用例**（不是"大概通过"），
   且 ``BenchReport.passed`` 转为 ``False``。

指标阈值口径见 :mod:`labelcheck.benchmark.runner_fields` 等（**单一来源**，
README 指标表与之一致）。
"""

import json

import pytest

from labelcheck.benchmark import BENCH_NAMES, run_benchmark
from labelcheck.benchmark.metrics import OP_AT_LEAST, OP_AT_MOST, Metric, rate
from labelcheck.benchmark.runner_constructed import TARGET_DETECTION, TARGET_FALSE_POSITIVE
from labelcheck.benchmark.runner_diff import TARGET_CONSISTENCY
from labelcheck.benchmark.runner_fields import TARGET_ACCURACY
from labelcheck.paths import find_data_dir


@pytest.fixture(scope="module")
def data_dir():
    return find_data_dir()


@pytest.fixture(scope="module")
def report(data_dir):
    return run_benchmark(data_dir)


# ------------------------------------------------------------------ 全部达标
def test_all_three_suites_run(report):
    assert [suite.name for suite in report.suites] == list(BENCH_NAMES)


def test_repository_data_passes_all_suites(report):
    """仓库真实数据下三类基准全部达标（这是 FR-11 的核心验收）。"""
    failures = report.failures
    assert report.passed, "基准未达标：\n" + "\n".join(failures)
    for suite in report.suites:
        assert suite.passed, suite.name
        assert suite.failures == [], suite.name


def test_fields_accuracy_is_one_hundred_percent(report):
    suite = report.suite("fields")
    metric = suite.metrics[0]
    assert metric.name == "判定准确率"
    assert metric.op == OP_AT_LEAST
    assert metric.target == TARGET_ACCURACY
    assert metric.value == 1.0
    assert suite.cases_total == suite.cases_passed > 0


def test_constructed_meets_detection_and_false_positive(report):
    suite = report.suite("constructed")
    detection, false_positive = suite.metrics
    assert detection.name == "检出率"
    assert detection.op == OP_AT_LEAST
    assert detection.value >= TARGET_DETECTION

    assert false_positive.name == "误报率"
    assert false_positive.op == OP_AT_MOST, "误报率必须按'越小越好'判定"
    assert false_positive.value <= TARGET_FALSE_POSITIVE
    assert false_positive.value == 0.0


def test_diff_collections_fully_consistent(report):
    suite = report.suite("diff")
    metric = suite.metrics[0]
    assert metric.name == "对账集合一致率"
    assert metric.target == TARGET_CONSISTENCY
    assert metric.value == 1.0


# ------------------------------------------------------------------ 指标形态
def test_metric_direction_semantics():
    """达标方向语义：``>=`` 与 ``<=`` 各自成立（误报率不能用 ``>=`` 判）。"""
    high = Metric("x", 0.9, target=0.8, op=OP_AT_LEAST)
    assert high.passed
    assert not Metric("x", 0.7, target=0.8, op=OP_AT_LEAST).passed

    low = Metric("y", 0.0, target=0.0, op=OP_AT_MOST)
    assert low.passed
    assert not Metric("y", 0.01, target=0.0, op=OP_AT_MOST).passed

    with pytest.raises(ValueError):
        Metric("z", 1.0, target=1.0, op="==")


def test_rate_handles_empty_denominator():
    """空分母口径显式：默认视为"没有可失败的对象"（1.0），且可覆盖。"""
    assert rate(0, 0) == 1.0
    assert rate(0, 0, empty=0.0) == 0.0
    assert rate(1, 4) == 0.25


# ------------------------------------------------------------------ 确定性
def test_benchmark_output_is_deterministic(data_dir):
    first = run_benchmark(data_dir).to_dict()
    second = run_benchmark(data_dir).to_dict()
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
        json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_benchmark_only_selects_subset(data_dir):
    report = run_benchmark(data_dir, only=["diff"])
    assert [suite.name for suite in report.suites] == ["diff"]
    assert report.only == ["diff"]
    assert report.passed


def test_benchmark_rejects_unknown_suite(data_dir):
    with pytest.raises(ValueError):
        run_benchmark(data_dir, only=["nope"])


def test_benchmark_does_not_touch_repository_data(data_dir):
    """基准只在临时目录构造合成数据目录（不在仓库 data/ 下落任何文件）。"""
    before = sorted(path.name for path in data_dir.iterdir())
    run_benchmark(data_dir)
    after = sorted(path.name for path in data_dir.iterdir())
    assert before == after


# ------------------------------------------------------------------ 失败可诊断
def test_benchmark_reports_failures_with_case_ids(data_dir, monkeypatch):
    """注入一处口径漂移 → 报告须**列出具体用例**且 ``passed`` 转 False。

    做法：把 ``runner_fields`` 里的 ``check_field_case`` 打桩为"永远报一处不一致"——
    这模拟"引擎口径变了、期望没跟上"的真实故障形态，验证基准**不会静默通过**。
    （须打在 **runner 模块**的绑定上：runner 用 ``from .cases import check_field_case``
    绑定了名字，打 ``cases`` 模块上的原函数不会影响已绑定的引用。）
    """
    from labelcheck.benchmark import runner_fields

    monkeypatch.setattr(runner_fields, "check_field_case",
                        lambda case, d: ["注入的模拟不一致"])
    report = run_benchmark(data_dir, only=["fields"])
    suite = report.suite("fields")
    assert not suite.passed
    assert not report.passed
    assert suite.failures, "失败明细不得为空"
    assert "FIELD-" in suite.failures[0], "失败明细须含具体用例 id"
    assert suite.metrics[0].value == 0.0


def test_constructed_runner_flags_false_positive(data_dir, monkeypatch):
    """误报用例上出现 fail → 误报率 > 0 且列出误报件（致命错误的可见化）。"""
    from labelcheck.benchmark import runner_constructed

    monkeypatch.setattr(runner_constructed, "check_constructed_case",
                        lambda case, d: ["注入的模拟误报"])
    report = run_benchmark(data_dir, only=["constructed"])
    suite = report.suite("constructed")
    false_positive = suite.metrics[1]
    assert false_positive.value > 0.0
    assert not false_positive.passed
    assert not suite.passed