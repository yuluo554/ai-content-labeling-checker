"""规则库加载与 **status 门控**（NFR-4 的唯一实现点）。

组织形态：``data/rules/`` 按「依据文件 × 版本」一份 JSON + 一份 ``registry.json``
（契约见 plan/04 §三）。切换核查口径 = 改 ``registry.json`` 的 ``active``。

**核心纪律**：``pending`` 条目绝不进入判定路径。这是"未挂原文核对不得落库/生效/
进入判定路径"的唯一落点，测试锁死（``tests/test_rules_gate.py``）。
"""

import re

from ..errors import RulesetError
from ..jsonio import load_json, sha256_text, canonical_json
from ..paths import SENTINEL  # noqa: F401  (保持 discoverable 语义一致)
from .rule import (
    Rule, CHECK_TYPES, SCOPES, VERIFY_STATUSES, SCENARIOS,
    SCOPE_IMPLICIT, STATUS_VERIFIED, STATUS_PENDING,
)

REGISTRY_NAME = "registry.json"

_DOC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Ruleset(object):
    """一次加载结果：**生效规则** + **待核对规则** + 版本坐标。

    属性：
    - ``effective``：只含 ``status=verified`` 且所属文档 ``status=verified`` 的规则；
    - ``pending``：其余规则（供 selfcheck/报告展示"还有多少条待核对"）；
    - ``documents``：本次纳入的报告头坐标（doc_id/version/sha256/status）；
    - ``coordinate``：报告头固定输出的规则库坐标串；
    - ``warnings``：加载期的非致命提示（如 active 指向缺失文件）。
    """

    def __init__(self, effective, pending, documents, coordinate, warnings=None):
        self.effective = list(effective)
        self.pending = list(pending)
        self.documents = list(documents)
        self.coordinate = coordinate
        self.warnings = list(warnings) if warnings else []

    # ------------------------------------------------------------------ 查询
    def rules_for(self, scope, carrier):
        """取适用于指定 scope 与载体的**生效**规则（顺序 = 加载顺序，确定）。"""
        return [
            r for r in self.effective
            if r.scope == scope and r.applies_to_carrier(carrier)
        ]

    def rules_for_card(self, scope, carrier, scenario):
        """取适用于 scope × 载体 × **场景**的生效规则（适用性画像的单一查询点）。

        场景不适用的条目仍要产出 ``skipped`` 判定（"为什么没查"必须可见），
        故这里返回 ``(applicable, skipped)`` 两个列表，顺序均为加载顺序。
        """
        applicable = []
        skipped = []
        for rule in self.effective:
            if rule.scope != scope or not rule.applies_to_carrier(carrier):
                continue
            if rule.applies_to_scenario(scenario):
                applicable.append(rule)
            else:
                skipped.append(rule)
        return applicable, skipped

    @property
    def verified_rule_count(self):
        return len(self.effective)

    @property
    def pending_rule_count(self):
        return len(self.pending)

    @property
    def doc_versions(self):
        """报告头/依据清单用的文档坐标列表（顺序 = 加载顺序）。

        除坐标（doc_id/version/sha256/status）外，附带 registry 里的书目元数据
        （title/doc_number/issuer/effective_from）——报告"依据清单"段直接取用，
        避免报告层再去读一遍 registry（单一来源）。
        """
        return [
            {
                "doc_id": doc.get("doc_id", ""),
                "version": doc.get("version", ""),
                "sha256": doc.get("sha256", ""),
                "status": doc.get("status", ""),
                "title": doc.get("title", ""),
                "doc_number": doc.get("doc_number", ""),
                "issuer": doc.get("issuer", ""),
                "kind": doc.get("kind", ""),
                "effective_from": doc.get("effective_from", ""),
                "next_review": doc.get("next_review", ""),
            }
            for doc in self.documents
        ]

    def __repr__(self):
        return "Ruleset(effective={0}, pending={1}, coordinate={2!r})".format(
            self.verified_rule_count, self.pending_rule_count, self.coordinate
        )


# ---------------------------------------------------------------- 结构校验
def _require(condition, message):
    if not condition:
        raise RulesetError(message)


def _parse_rule(raw, doc_id, version, where):
    """把单条 JSON 解析为 :class:`Rule` 并做结构校验。"""
    _require(isinstance(raw, dict), "{0}: 规则必须是对象".format(where))
    rule_id = raw.get("rule_id")
    _require(isinstance(rule_id, str) and rule_id, "{0}: 缺少合法 rule_id".format(where))

    scope = raw.get("scope")
    _require(scope in SCOPES, "{0} ({1}): scope 非法 {2!r}".format(where, rule_id, scope))

    check_type = raw.get("check_type")
    _require(
        check_type in CHECK_TYPES,
        "{0} ({1}): check_type 非法 {2!r}（须为 {3}）".format(
            where, rule_id, check_type, "/".join(CHECK_TYPES)
        ),
    )

    target = raw.get("target")
    _require(isinstance(target, str) and target, "{0} ({1}): 缺少合法 target".format(where, rule_id))

    status = raw.get("status", STATUS_PENDING)
    _require(
        status in VERIFY_STATUSES,
        "{0} ({1}): status 非法 {2!r}（须为 {3}）".format(
            where, rule_id, status, "/".join(VERIFY_STATUSES)
        ),
    )

    carrier = raw.get("carrier", [])
    if carrier is None:
        carrier = []
    _require(isinstance(carrier, list), "{0} ({1}): carrier 必须是数组".format(where, rule_id))

    params = raw.get("params", {})
    if params is None:
        params = {}
    _require(isinstance(params, dict), "{0} ({1}): params 必须是对象".format(where, rule_id))

    if check_type in ("position", "enum"):
        _require(
            isinstance(params.get("allowed"), list) and params["allowed"],
            "{0} ({1}): {2} 规则必须给 params.allowed 非空数组".format(where, rule_id, check_type),
        )
    if check_type == "pattern":
        _require(
            isinstance(params.get("regex"), str) and params["regex"],
            "{0} ({1}): pattern 规则必须给 params.regex".format(where, rule_id),
        )
    if check_type == "unique":
        _require(
            scope == SCOPE_IMPLICIT,
            "{0} ({1}): unique 规则只能用于 implicit scope（整块隐式标识上下文）".format(where, rule_id),
        )

    # 场景门控（适用性画像）：only_if.scenario 只许声明已知场景，否则门控会静默失效
    only_if = raw.get("only_if", {}) or {}
    _require(isinstance(only_if, dict), "{0} ({1}): only_if 必须是对象".format(where, rule_id))
    declared_scenarios = only_if.get("scenario") or []
    _require(
        isinstance(declared_scenarios, list),
        "{0} ({1}): only_if.scenario 必须是数组".format(where, rule_id),
    )
    for scenario in declared_scenarios:
        _require(
            scenario in SCENARIOS,
            "{0} ({1}): only_if.scenario 含未知场景 {2!r}（须为 {3}）".format(
                where, rule_id, scenario, "/".join(SCENARIOS)
            ),
        )

    # verified 条目必须挂条款与出处（"无出处的值不得以确定语气落库"）
    if status == STATUS_VERIFIED:
        clause = raw.get("clause") or {}
        _require(
            isinstance(clause, dict) and clause.get("article"),
            "{0} ({1}): status=verified 的规则必须挂 clause.article（条款号）".format(where, rule_id),
        )
        _require(
            isinstance(raw.get("source_url"), str) and raw["source_url"],
            "{0} ({1}): status=verified 的规则必须挂 source_url".format(where, rule_id),
        )

    return Rule(
        rule_id=rule_id,
        scope=scope,
        target=target,
        check_type=check_type,
        carrier=carrier,
        params=params,
        severity=raw.get("severity", "major"),
        only_if=raw.get("only_if", {}),
        clause=raw.get("clause", {}),
        status=status,
        source_url=raw.get("source_url", ""),
        verified_at=raw.get("verified_at"),
        doc_id=doc_id,
        version=version,
    )


def _load_ruleset_file(path, doc_id, version):
    """加载单份规则文件，返回 ``(rules, file_sha256)``。"""
    data = load_json(path, error_cls=RulesetError)
    _require(isinstance(data, dict), "规则文件必须是 JSON 对象：{0}".format(path))
    _require(
        data.get("doc_id") == doc_id,
        "规则文件 doc_id 与注册表不一致：{0}（文件 {1!r} vs 注册表 {2!r}）".format(
            path, data.get("doc_id"), doc_id
        ),
    )
    _require(
        data.get("version") == version,
        "规则文件 version 与注册表不一致：{0}（文件 {1!r} vs 注册表 {2!r}）".format(
            path, data.get("version"), version
        ),
    )
    raw_rules = data.get("rules")
    _require(isinstance(raw_rules, list), "规则文件的 rules 必须是数组：{0}".format(path))

    rules = []
    seen = set()
    for index, raw in enumerate(raw_rules):
        where = "{0}#rules[{1}]".format(path, index)
        rule = _parse_rule(raw, doc_id, version, where)
        if rule.rule_id in seen:
            raise RulesetError("规则 id 重复：{0}（{1}）".format(rule.rule_id, path))
        seen.add(rule.rule_id)
        rules.append(rule)

    # 文件指纹以**规范化文本**计算：跨平台/行尾无关，随内容变
    file_sha256 = sha256_text(canonical_json(data, indent=None, sort_keys=True))
    return rules, file_sha256


def load_registry(data_dir):
    """加载 ``registry.json``（结构校验）。"""
    registry_path = _registry_path(data_dir)
    data = load_json(registry_path, error_cls=RulesetError)
    _require(isinstance(data, dict), "registry.json 必须是 JSON 对象：{0}".format(registry_path))
    documents = data.get("documents")
    _require(isinstance(documents, list) and documents, "registry.json 的 documents 必须是非空数组")

    ids = set()
    for index, doc in enumerate(documents):
        _require(isinstance(doc, dict), "registry.documents[{0}] 必须是对象".format(index))
        doc_id = doc.get("doc_id")
        _require(
            isinstance(doc_id, str) and _DOC_ID_RE.match(doc_id),
            "registry.documents[{0}].doc_id 非法：{1!r}".format(index, doc_id),
        )
        _require(doc_id not in ids, "registry 中 doc_id 重复：{0}".format(doc_id))
        ids.add(doc_id)
        doc_status = doc.get("status", STATUS_PENDING)
        _require(
            doc_status in VERIFY_STATUSES,
            "registry 文档 {0} 的 status 非法：{1!r}".format(doc_id, doc_status),
        )
        versions = doc.get("versions")
        _require(
            isinstance(versions, list) and versions,
            "registry 文档 {0} 的 versions 必须是非空数组".format(doc_id),
        )
        for vindex, ver in enumerate(versions):
            _require(isinstance(ver, dict), "registry 文档 {0} versions[{1}] 必须是对象".format(doc_id, vindex))
            version = ver.get("version")
            _require(
                isinstance(version, str) and _VERSION_RE.match(version),
                "registry 文档 {0} versions[{1}].version 非法：{2!r}（须为 YYYY-MM-DD）".format(
                    doc_id, vindex, version
                ),
            )
            _require(
                isinstance(ver.get("rules_file"), str) and ver["rules_file"],
                "registry 文档 {0} 版本 {1} 缺少 rules_file".format(doc_id, version),
            )

    active = data.get("active", {})
    _require(isinstance(active, dict), "registry.active 必须是对象")
    for doc_id in active:
        _require(doc_id in ids, "registry.active 引用了未注册的 doc_id：{0}".format(doc_id))

    return data, registry_path


def _registry_path(data_dir):
    from pathlib import Path
    return Path(data_dir) / SENTINEL


def _resolve_version(doc, active_version):
    """在文档的 versions 中取目标版本记录（无则 None）。"""
    for ver in doc.get("versions", []):
        if ver.get("version") == active_version:
            return ver
    return None


def effective_ruleset(data_dir):
    """**单点门控**：加载 registry + active 版本的规则文件，分离 effective / pending。

    规则生效需**双重 satisfied**：
    1. 该**文档**在 ``registry`` 中 ``status=verified``；
    2. 该**条目**自身 ``status=verified``。

    未满足者一律进 ``pending``（绝不参与判定）。M0 时两份文档均为 ``pending`` → ``effective``
    为空；M1 后 GB 45438-2025 已逐页核对原文转 ``verified``（22 条生效），
    《标识办法》条目记录法定义务与真实条号、保持 ``pending``（判定由国标承担）。
    """
    registry, registry_path = load_registry(data_dir)
    active = registry.get("active", {})
    docs_by_id = {doc["doc_id"]: doc for doc in registry["documents"]}

    effective = []
    pending = []
    documents = []
    warnings = []
    from pathlib import Path

    # rules_file 是相对 data/rules/ 的路径（不是相对 data/）
    rules_root = Path(data_dir) / "rules"

    for doc_id, doc in docs_by_id.items():
        doc_status = doc.get("status", STATUS_PENDING)
        active_version = active.get(doc_id)
        if active_version is None:
            warnings.append("文档 {0} 未在 registry.active 中声明生效版本，跳过加载".format(doc_id))
            continue

        ver = _resolve_version(doc, active_version)
        if ver is None:
            warnings.append(
                "文档 {0} 的 active 版本 {1} 不在 versions 列表中，跳过加载".format(doc_id, active_version)
            )
            continue

        rules_path = rules_root / ver["rules_file"]
        rules, file_sha256 = _load_ruleset_file(rules_path, doc_id, active_version)

        declared = ver.get("sha256")
        if declared and declared != file_sha256:
            raise RulesetError(
                "规则文件指纹与注册表登记值不一致：{0}\n  注册表：{1}\n  实际  ：{2}\n"
                "（数据变更须走生成器重生成并同步 registry.sha256）".format(
                    rules_path, declared, file_sha256
                )
            )

        documents.append({
            "doc_id": doc_id,
            "version": active_version,
            "sha256": file_sha256,
            "status": doc_status,
            # 书目元数据（报告"依据清单"段直接取用；单一来源 = registry）
            "title": doc.get("title", ""),
            "doc_number": doc.get("doc_number", ""),
            "issuer": doc.get("issuer", ""),
            "kind": doc.get("kind", ""),
            "effective_from": ver.get("effective_from", ""),
            "next_review": doc.get("next_review") or ver.get("next_review", ""),
        })

        for rule in rules:
            # 双重门控：文档级 + 条目级
            if doc_status == STATUS_VERIFIED and rule.is_effective:
                effective.append(rule)
            else:
                pending.append(rule)

    pending = _dedupe_rules(pending)
    effective = _dedupe_rules(effective)

    coordinate = "+".join(
        "{0}@{1}".format(d["doc_id"], d["version"]) for d in documents
    ) or "(no-active-ruleset)"

    # 顺序固定：先按 doc 加载序，再按规则文件内声明序（list 顺序，非 set）
    return Ruleset(effective, pending, documents, coordinate, warnings)


def _dedupe_rules(rules):
    """按 rule_id 保序去重（防御性；重复 id 已在文件级拦截）。"""
    seen = set()
    out = []
    for rule in rules:
        if rule.rule_id in seen:
            continue
        seen.add(rule.rule_id)
        out.append(rule)
    return out


__all__ = ["Ruleset", "effective_ruleset", "load_registry", "REGISTRY_NAME"]
