# -*- coding: utf-8 -*-
"""``constructed`` 基准：构造真值的检出率 / 误报率（FR-11，契约见 plan/04 §九）。

用例来自 :func:`labelcheck.benchmark.cases.constructed_cases`（**单一实现源**）：
程序化构造带**已知标识配置**的合成件——注入点已知（缺字段/错取值/错格式/错位置/
元数据剥离/显式缺失/重复保留/场景义务），故期望值由**注入点**推出，不抄引擎输出。

两条指标：

- **检出率** ≥ 0.95：分母 = 有注入的用例；分子 = 引擎判出的 ``fail`` 目标集与注入
  期望**完全一致**的用例（含"多报/少报"都算未检出——只看"有没有报违规"会漏掉错报）；
- **误报率** = 0：分母 = 无注入的用例（全要素合规、作用域未观测、引擎分支）；分子 =
  被引擎判出 ``fail`` 的用例数。**误报 0 是硬口径**：把合规件判成违规是工具的致命错误。

检出率不足时**逐例列出**未检出/错报的用例与差异；误报非 0 时逐例列出误报件。
"""

from .cases import check_constructed_case, constructed_cases
from .metrics import OP_AT_LEAST, OP_AT_MOST, Metric, SuiteResult, rate

#: 基准名
NAME = "constructed"
#: 标题
TITLE = "构造真值基准（已知标识配置的合成件：检出率 / 误报率）"
#: 检出率阈值
TARGET_DETECTION = 0.95
#: 误报率阈值（硬口径：0）
TARGET_FALSE_POSITIVE = 0.0


def run(ruleset, mapping, data_dir, synthetic_dirs=None):
    """跑 ``constructed`` 基准，返回 :class:`SuiteResult`。

    :param synthetic_dirs: 引擎分支用例所需的合成数据目录（``None`` 时该类用例跳过）
    """
    cases = constructed_cases(ruleset, mapping, synthetic_dirs=synthetic_dirs, data_dir=data_dir)

    detection_total = 0
    detection_hit = 0
    clean_total = 0
    clean_hit = 0
    failures = []
    false_positives = []
    passed = 0

    for case in cases:
        case_dir = case.get("data_dir") or data_dir
        mismatches = check_constructed_case(case, case_dir)
        if not mismatches:
            passed += 1

        if case.get("detection"):
            detection_total += 1
            if not mismatches:
                detection_hit += 1
            else:
                failures.append("{0}（{1}）：{2}".format(
                    case["case_id"], case["description"], "；".join(mismatches)))
        elif case.get("clean"):
            clean_total += 1
            if not mismatches:
                clean_hit += 1
            else:
                # 无误报用例上的任何 fail 都是致命错误
                false_positives.append("{0}（{1}）：{2}".format(
                    case["case_id"], case["description"], "；".join(mismatches)))

    detection = rate(detection_hit, detection_total)
    false_positive = 1.0 - rate(clean_hit, clean_total)

    metrics = [
        Metric("检出率", detection, target=TARGET_DETECTION, op=OP_AT_LEAST,
               detail="{0}/{1} 例注入被正确检出".format(detection_hit, detection_total)),
        Metric("误报率", false_positive, target=TARGET_FALSE_POSITIVE, op=OP_AT_MOST,
               detail="{0} 例误报 / {1} 例无误报用例".format(
                   clean_total - clean_hit, clean_total)),
    ]

    notes = []
    if synthetic_dirs is None:
        notes.append("未提供合成数据目录 → 引擎分支用例（未映射字段/无适用规则）未生成")
    elif not any(case.get("group") == "engine_branch" for case in cases):
        notes.append("引擎分支用例未生成（合成数据目录缺少必要分支）")

    all_failures = failures + false_positives
    return SuiteResult(
        name=NAME, title=TITLE, metrics=metrics,
        cases_total=len(cases), cases_passed=passed, failures=all_failures, notes=notes,
    )


__all__ = ["NAME", "TITLE", "TARGET_DETECTION", "TARGET_FALSE_POSITIVE", "run"]