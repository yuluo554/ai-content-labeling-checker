"""标识完整性判定与分级（契约见 plan/04 §六）。

综合显式 + 隐式判定 → 合规等级 + 缺失项 + 错误码清单。

**分级规则（定稿，无魔数）**：

0. **无任何生效规则**（``findings`` 为空且无规则可施）→ ``not_assessed``。
   这是"未核对不得生效"在**输出侧**的对应纪律：规则库条目全 ``pending`` 时，
   工具必须说"没检查"而不是"合规"（**绝不输出假合规结论**）。
1. 无 ``fail``：有 ``unknown`` → ``partial``（无明确违规但有待人工确认项）；
   否则 → ``compliant``。
2. 有 ``fail``：存在 ``critical`` 或 ``major`` 级 fail → ``non_compliant``；
   仅 ``minor`` 级 fail → ``partial``。

**边界情形显式处理**（01 §三.3 要求）：元数据被剥离但显式标识在 —— 隐式字段全
``fail``；若其中有 critical/major 级规则 → ``non_compliant``，``missing`` 列出
被剥离字段（该情形须进基准枚举，M4）。
"""

from ..model import (
    GRADE_COMPLIANT, GRADE_NON_COMPLIANT, GRADE_NOT_ASSESSED, GRADE_PARTIAL,
    SEVERITY_CRITICAL, SEVERITY_MAJOR,
)

#: 触发"不合规"的严重度（critical 或 major 任一条 fail 即成立）
_HIGH_SEVERITIES = (SEVERITY_CRITICAL, SEVERITY_MAJOR)


def _ordered_unique(items):
    """保序去重（顺序敏感，不用 set 迭代）。"""
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def grade_findings(findings):
    """按定稿规则给出一件内容的合规等级。

    :returns: ``(grade, missing, errors)``
        - ``missing``：所有 ``fail`` 的 target（保序去重）
        - ``errors``：所有 ``fail`` 的 code（保序去重）

    引擎不变量：**每条生效规则恰好产出一条 Finding**，故 ``findings`` 为空 ⟺
    没有任何生效规则被施加 → ``not_assessed``。
    """
    if not findings:
        return GRADE_NOT_ASSESSED, [], []

    fails = [f for f in findings if f.status == "fail"]
    unknowns = [f for f in findings if f.status == "unknown"]

    missing = _ordered_unique([f.target for f in fails])
    errors = _ordered_unique([f.code for f in fails if f.code])

    if not fails:
        grade = GRADE_PARTIAL if unknowns else GRADE_COMPLIANT
        return grade, missing, errors

    if any(f.severity in _HIGH_SEVERITIES for f in fails):
        return GRADE_NON_COMPLIANT, missing, errors

    return GRADE_PARTIAL, missing, errors


__all__ = ["grade_findings"]
