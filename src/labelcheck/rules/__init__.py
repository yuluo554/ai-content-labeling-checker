"""版本化核查规则库（依据文件 × 版本）。

对外接口：
- :func:`labelcheck.rules.loader.effective_ruleset` —— **单点门控**（pending 不进判定路径）
- :class:`labelcheck.rules.rule.Rule` —— 规则条目
- :func:`labelcheck.rules.rule.evaluate` —— check_type 分派判定
"""

from .rule import (  # noqa: F401
    Rule,
    evaluate,
    CHECK_TYPES,
    SCOPES,
    SCOPE_EXPLICIT,
    SCOPE_IMPLICIT,
    STATUS_VERIFIED,
    STATUS_PENDING,
    VERIFY_STATUSES,
)
from .loader import (  # noqa: F401
    Ruleset,
    effective_ruleset,
    load_registry,
    REGISTRY_NAME,
)

__all__ = [
    "Rule",
    "Ruleset",
    "evaluate",
    "effective_ruleset",
    "load_registry",
    "CHECK_TYPES",
    "SCOPES",
    "SCOPE_EXPLICIT",
    "SCOPE_IMPLICIT",
    "STATUS_VERIFIED",
    "STATUS_PENDING",
    "VERIFY_STATUSES",
    "REGISTRY_NAME",
]
