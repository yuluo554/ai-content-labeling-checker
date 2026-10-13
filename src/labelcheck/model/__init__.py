"""统一中间表示（UMR）：标识卡、判定结果与报告对象的**纯数据模型**。

设计契约见 plan/04-模块详设.md §一。字段名与枚举值属**既定口径**（plan/04 §十一），
后续里程碑不得漂移。

本模块**零业务逻辑**：只做结构定义、构造与输入校验（把畸形输入挡在判定路径之前）。
"""

import re

from .. import DISCLAIMER as _DISCLAIMER
from ..errors import InputError

#: 载体枚举（既定口径）
CARRIERS = ("text", "image", "audio", "video")

#: 输入来源枚举
SOURCES = ("synthetic", "manual", "parsed")

#: 判定状态枚举（语义见 plan/04 §一.3）
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_UNKNOWN = "unknown"
STATUS_SKIPPED = "skipped"
STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN, STATUS_SKIPPED)

#: 合规等级枚举（语义见 plan/04 §六）
GRADE_COMPLIANT = "compliant"
GRADE_PARTIAL = "partial"
GRADE_NON_COMPLIANT = "non_compliant"
#: 未评估：**没有任何生效规则可施加**（如规则库条目全部 pending）。
#: 与 compliant 严格区分——"没查出问题"与"没检查过"不是一回事，绝不输出假合规。
GRADE_NOT_ASSESSED = "not_assessed"

#: 严重度枚举
SEVERITY_CRITICAL = "critical"
SEVERITY_MAJOR = "major"
SEVERITY_MINOR = "minor"
SEVERITIES = (SEVERITY_CRITICAL, SEVERITY_MAJOR, SEVERITY_MINOR)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LabelCard(object):
    """标识卡：显式要素 + 隐式字段字典（核验器的统一输入）。

    :param card_id: 件唯一标识（必填、非空）
    :param carrier: 载体，∈ :data:`CARRIERS`
    :param content_sha256: 内容指纹（64 位小写 hex）；缺失/不合法 → 输入非法
    :param explicit: 显式要素列表，每项为 dict（``element``/``present``/``position``/...）
    :param implicit: 隐式字段字典（容器原始键 → 值）
    :param source: 来源，∈ :data:`SOURCES`（默认 ``manual``）
    :param notes: 人工备注（不参与判定）
    """

    __slots__ = ("card_id", "carrier", "content_sha256", "explicit", "implicit", "source", "notes")

    def __init__(self, card_id, carrier, content_sha256, explicit=None, implicit=None,
                 source="manual", notes=""):
        self.card_id = card_id
        self.carrier = carrier
        self.content_sha256 = content_sha256
        self.explicit = list(explicit) if explicit else []
        self.implicit = dict(implicit) if implicit else {}
        self.source = source
        self.notes = notes

    # ------------------------------------------------------------------ 校验
    @classmethod
    def from_dict(cls, data):
        """从 dict 构造并**校验**；不合法抛 :class:`InputError`（exit 2）。"""
        if not isinstance(data, dict):
            raise InputError("标识卡必须是 JSON 对象，得到 {0}".format(type(data).__name__))

        card_id = data.get("card_id")
        if not isinstance(card_id, str) or not card_id.strip():
            raise InputError("标识卡缺少合法 card_id（须为非空字符串）")

        carrier = data.get("carrier")
        if carrier not in CARRIERS:
            raise InputError(
                "标识卡 {0} 的 carrier 非法：{1!r}（须为 {2} 之一）".format(
                    card_id, carrier, "/".join(CARRIERS)
                )
            )

        content_sha256 = data.get("content_sha256")
        if not isinstance(content_sha256, str) or not _SHA256_RE.match(content_sha256):
            raise InputError(
                "标识卡 {0} 的 content_sha256 缺失或不合法（须为 64 位小写 hex）".format(card_id)
            )

        source = data.get("source", "manual")
        if source not in SOURCES:
            raise InputError(
                "标识卡 {0} 的 source 非法：{1!r}（须为 {2} 之一）".format(
                    card_id, source, "/".join(SOURCES)
                )
            )

        explicit = data.get("explicit", [])
        if not isinstance(explicit, list):
            raise InputError("标识卡 {0} 的 explicit 必须是数组".format(card_id))
        for index, item in enumerate(explicit):
            if not isinstance(item, dict):
                raise InputError(
                    "标识卡 {0} 的 explicit[{1}] 必须是对象".format(card_id, index)
                )
            if not isinstance(item.get("element"), str) or not item["element"]:
                raise InputError(
                    "标识卡 {0} 的 explicit[{1}] 缺少合法 element".format(card_id, index)
                )

        implicit = data.get("implicit", {})
        if not isinstance(implicit, dict):
            raise InputError("标识卡 {0} 的 implicit 必须是对象".format(card_id))

        notes = data.get("notes", "")
        if notes is None:
            notes = ""
        if not isinstance(notes, str):
            raise InputError("标识卡 {0} 的 notes 必须是字符串".format(card_id))

        return cls(
            card_id=card_id,
            carrier=carrier,
            content_sha256=content_sha256,
            explicit=explicit,
            implicit=implicit,
            source=source,
            notes=notes,
        )

    # ------------------------------------------------------------------ 查询
    def find_explicit(self, element_id):
        """按 element id 取显式要素（返回首个匹配的 dict，无则 None）。"""
        for item in self.explicit:
            if item.get("element") == element_id:
                return item
        return None

    def to_dict(self):
        """回写为 dict（顺序固定，保证规范化输出可复现）。"""
        return {
            "card_id": self.card_id,
            "carrier": self.carrier,
            "content_sha256": self.content_sha256,
            "source": self.source,
            "explicit": [dict(item) for item in self.explicit],
            "implicit": dict(self.implicit),
            "notes": self.notes,
        }

    def __repr__(self):
        return "LabelCard(card_id={0!r}, carrier={1!r}, explicit={2}, implicit={3})".format(
            self.card_id, self.carrier, len(self.explicit), len(self.implicit)
        )


class Finding(object):
    """逐要素/逐字段判定（契约见 plan/04 §一.3）。"""

    __slots__ = ("scope", "target", "status", "code", "message", "clause", "evidence", "severity")

    def __init__(self, scope, target, status, code="", message="", clause=None, evidence=None,
                 severity="major"):
        if status not in STATUSES:
            raise ValueError("非法 status：{0!r}".format(status))
        if severity not in SEVERITIES:
            raise ValueError("非法 severity：{0!r}".format(severity))
        self.scope = scope
        self.target = target
        self.status = status
        self.code = code
        self.message = message
        self.clause = dict(clause) if clause else {}
        self.evidence = dict(evidence) if evidence else {}
        self.severity = severity

    @property
    def is_violation(self):
        """是否计入违规（``fail`` 是；``unknown`` 否，见 plan/04 §一.3）。"""
        return self.status == STATUS_FAIL

    @property
    def needs_review(self):
        """是否需人工确认（``unknown``）。"""
        return self.status == STATUS_UNKNOWN

    def to_dict(self):
        return {
            "scope": self.scope,
            "target": self.target,
            "status": self.status,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "clause": dict(self.clause),
            "evidence": dict(self.evidence),
        }

    def __repr__(self):
        return "Finding({0}:{1} → {2}{3})".format(
            self.scope, self.target, self.status,
            " [{0}]".format(self.code) if self.code else "",
        )


class CheckReport(object):
    """单件核验报告（契约见 plan/04 §一.2）。"""

    __slots__ = ("card_id", "carrier", "ruleset_coordinate", "documents",
                 "verified_rule_count", "pending_rule_count",
                 "explicit", "implicit", "grade", "missing", "errors",
                 "disclaimer", "content_sha256", "generated_at")

    DISCLAIMER = _DISCLAIMER

    def __init__(self, card_id, carrier, ruleset_coordinate="",
                 documents=None, verified_rule_count=0, pending_rule_count=0,
                 explicit=None, implicit=None, grade=GRADE_PARTIAL,
                 missing=None, errors=None, content_sha256="",
                 generated_at="", disclaimer=None):
        self.card_id = card_id
        self.carrier = carrier
        self.ruleset_coordinate = ruleset_coordinate
        self.documents = list(documents) if documents else []
        self.verified_rule_count = verified_rule_count
        self.pending_rule_count = pending_rule_count
        self.explicit = list(explicit) if explicit else []
        self.implicit = list(implicit) if implicit else []
        self.grade = grade
        self.missing = list(missing) if missing else []
        self.errors = list(errors) if errors else []
        self.content_sha256 = content_sha256
        self.generated_at = generated_at
        self.disclaimer = self.DISCLAIMER if disclaimer is None else disclaimer

    @property
    def all_findings(self):
        """显式 + 隐式全部判定（顺序固定：显式在前）。"""
        return list(self.explicit) + list(self.implicit)

    @property
    def violations(self):
        return [f for f in self.all_findings if f.is_violation]

    @property
    def reviews(self):
        return [f for f in self.all_findings if f.needs_review]

    @property
    def has_violation(self):
        """是否存在 fail（决定 CLI 退出码 0/1）。"""
        return any(f.is_violation for f in self.all_findings)

    def to_dict(self):
        return {
            "card_id": self.card_id,
            "carrier": self.carrier,
            "content_sha256": self.content_sha256,
            "generated_at": self.generated_at,
            "ruleset": {
                "coordinate": self.ruleset_coordinate,
                "documents": [dict(doc) for doc in self.documents],
                "verified_rule_count": self.verified_rule_count,
                "pending_rule_count": self.pending_rule_count,
            },
            "explicit": [f.to_dict() for f in self.explicit],
            "implicit": [f.to_dict() for f in self.implicit],
            "grade": self.grade,
            "missing": list(self.missing),
            "errors": list(self.errors),
            "disclaimer": self.disclaimer,
        }

    def __repr__(self):
        return "CheckReport(card_id={0!r}, grade={1!r}, findings={2}/{3})".format(
            self.card_id, self.grade, len(self.all_findings), len(self.violations)
        )


__all__ = [
    "CARRIERS", "SOURCES", "STATUSES", "SEVERITIES",
    "STATUS_PASS", "STATUS_FAIL", "STATUS_UNKNOWN", "STATUS_SKIPPED",
    "GRADE_COMPLIANT", "GRADE_PARTIAL", "GRADE_NON_COMPLIANT", "GRADE_NOT_ASSESSED",
    "SEVERITY_CRITICAL", "SEVERITY_MAJOR", "SEVERITY_MINOR",
    "LabelCard", "Finding", "CheckReport",
]
