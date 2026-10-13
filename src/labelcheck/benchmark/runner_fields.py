# -*- coding: utf-8 -*-
"""``fields`` 基准：元数据字段判定准确率（FR-11，契约见 plan/04 §九）。

用例来自 :func:`labelcheck.benchmark.cases.field_cases`（**单一实现源**）：
逐 ``check_type``（存在性 / 位置 / 格式 / 取值 / 类型 / 唯一性 / 场景门控）枚举
边界与畸形输入，断言引擎产出的判定四元组（scope × target × status × code）。

**指标 = 判定准确率**：目标 100%（全部为确定性用例——期望值取自规则库语义，
不存在"统计意义上的接近"）。任何一例不一致都会**列出具体用例与差异**，
不静默降级为"大概通过"。
"""

from .cases import check_field_case, field_cases, missing_check_types
from .metrics import OP_AT_LEAST, Metric, SuiteResult, rate

#: 基准名
NAME = "fields"
#: 标题
TITLE = "字段规则基准（逐 check_type 的边界/畸形用例判定准确率）"
#: 达标阈值（确定性用例 → 100%）
TARGET_ACCURACY = 1.0


def run(ruleset, mapping, data_dir):
    """跑 ``fields`` 基准，返回 :class:`SuiteResult`。

    :param ruleset: :class:`labelcheck.rules.Ruleset`（生效规则）
    :param mapping: :class:`labelcheck.mapping.MappingTable`
    :param data_dir: 数据目录（用例的实际核验在此目录的规则库下进行）
    """
    cases = field_cases(ruleset, mapping)
    failures = []
    passed = 0
    for case in cases:
        mismatches = check_field_case(case, data_dir)
        if mismatches:
            failures.append("{0}（{1}）：{2}".format(
                case["case_id"], case["description"], "；".join(mismatches)))
        else:
            passed += 1

    total = len(cases)
    accuracy = rate(passed, total)
    metrics = [
        Metric("判定准确率", accuracy, target=TARGET_ACCURACY, op=OP_AT_LEAST,
               detail="{0}/{1} 例一致".format(passed, total)),
    ]

    notes = []
    missing = missing_check_types(ruleset)
    if missing:
        notes.append(
            "当前生效规则库中无 {0} 类型的规则 → 该类用例未生成（如实说明，不假装覆盖；"
            "建条决策见 plan/06 D27）".format("/".join(missing)))

    return SuiteResult(
        name=NAME, title=TITLE, metrics=metrics,
        cases_total=total, cases_passed=passed, failures=failures, notes=notes,
    )


__all__ = ["NAME", "TITLE", "TARGET_ACCURACY", "run"]