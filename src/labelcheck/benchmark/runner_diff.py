# -*- coding: utf-8 -*-
"""``diff`` 基准：两轮扫描对账的确定性验证（FR-11，契约见 plan/04 §九）。

用例来自 :func:`labelcheck.benchmark.cases.diff_scenarios`（**单一实现源**）：
构造两轮扫描（新增违规 / 已修复 / 持续违规 / 稳定 / 新增件 / 移除 / 内容变动全覆盖），
断言对账产出的**每一个集合**与声明**完全一致**（"三类集合完全一致"的验收口径，
三类 = 新增违规 / 已修复 / 持续违规；辅助集合一并核对）。

**指标 = 集合一致率**（目标 100%）：确定性对账不存在"接近一致"。不一致时逐场景列出
哪个集合差了哪几件——不给出"大体一致"这种无法整改的结论。
"""

from .cases import check_diff_scenario, diff_scenarios
from .metrics import OP_AT_LEAST, Metric, SuiteResult, rate

#: 基准名
NAME = "diff"
#: 标题
TITLE = "两轮对账基准（新增违规 / 已修复 / 持续违规 三类集合完全一致）"
#: 达标阈值（确定性对账 → 100%）
TARGET_CONSISTENCY = 1.0


def run(ruleset, data_dir):
    """跑 ``diff`` 基准，返回 :class:`SuiteResult`。"""
    scenarios = diff_scenarios(ruleset, data_dir)
    failures = []
    passed = 0
    for scenario in scenarios:
        mismatches = check_diff_scenario(scenario)
        scenario_id, description = scenario[0], scenario[1]
        if mismatches:
            failures.append("{0}（{1}）：{2}".format(
                scenario_id, description, "；".join(mismatches)))
        else:
            passed += 1

    total = len(scenarios)
    metrics = [
        Metric("对账集合一致率", rate(passed, total), target=TARGET_CONSISTENCY,
               op=OP_AT_LEAST, detail="{0}/{1} 场景全集合一致".format(passed, total)),
    ]

    notes = []
    if total == 0:
        notes.append("未生成对账场景（规则库无可用的隐式字段，无法构造两轮差异）")

    return SuiteResult(
        name=NAME, title=TITLE, metrics=metrics,
        cases_total=total, cases_passed=passed, failures=failures, notes=notes,
    )


__all__ = ["NAME", "TITLE", "TARGET_CONSISTENCY", "run"]