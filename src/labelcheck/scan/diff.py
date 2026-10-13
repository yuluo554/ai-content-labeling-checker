# -*- coding: utf-8 -*-
"""两轮扫描对账（FR-7，契约见 plan/04 §七）。

输入上轮与本轮 :class:`~labelcheck.scan.scanner.ScanResult`，按**稳定身份键**
（``ScanItem.identity``，口径见 :mod:`labelcheck.scan` 模块 docstring / plan/06 D28）
配对，产出四类集合 + 内容变动标记：

======================  ==================================================
集合                     判定
======================  ==================================================
**新增违规** ``added``    本轮有 fail 而上轮无此件（或上轮该件无 fail）
**已修复** ``fixed``      上轮有 fail 而本轮无 fail（含"上轮失败件本轮成功"）
**持续违规** ``persistent`` 两轮均 fail（附 ``changed_items``：fail 目标集变了的件）
**内容变动** ``content_changed`` 两轮配对成功但 ``content_sha256`` 不同
======================  ==================================================

其余辅助集合：``new_items``（上轮无此身份）、``removed``（本轮无此身份）、
``stable``（两轮均无 fail）。

**"修复"与"回归"必须可判**：这正是选"稳定身份键"而非内容指纹作主键的理由——
内容指纹一变就换键，"修复"会退化成"新增 + 消失"，整张对账表失去意义（见 plan/06 D28）。

**确定性**：集合内件序 = **本轮件序**（``added/persistent/stable``）或**上轮件序**
（``fixed/removed``）；``to_dict`` 顺序固定 → 相同输入两次对账逐字节一致。
"""

#: 对账状态（件级）
STATUS_ADDED = "added"           # 新增违规
STATUS_FIXED = "fixed"           # 已修复
STATUS_PERSISTENT = "persistent"  # 持续违规
STATUS_STABLE = "stable"         # 两轮均无违规
STATUS_NEW = "new"               # 本轮新增且无违规（辅助集合 new_items）
STATUS_REMOVED = "removed"       # 本轮不再出现（辅助集合 removed）
STATUS_CONTENT_CHANGED = "content_changed"  # 内容指纹变动（独立标记）


class DiffEntry(object):
    """对账中的一条件记录（含两轮状态与变动标记）。"""

    __slots__ = ("identity", "path", "status", "previous_path", "current_path",
                 "previous_grade", "current_grade", "previous_fail_targets",
                 "current_fail_targets", "content_changed", "previous_sha256",
                 "current_sha256", "card_id", "carrier")

    def __init__(self, identity, status, path="", previous_path="", current_path="",
                 previous_grade="", current_grade="", previous_fail_targets=None,
                 current_fail_targets=None, content_changed=False,
                 previous_sha256="", current_sha256="", card_id="", carrier=""):
        self.identity = identity
        self.status = status
        self.path = path
        self.previous_path = previous_path
        self.current_path = current_path
        self.previous_grade = previous_grade
        self.current_grade = current_grade
        self.previous_fail_targets = list(previous_fail_targets or [])
        self.current_fail_targets = list(current_fail_targets or [])
        self.content_changed = content_changed
        self.previous_sha256 = previous_sha256
        self.current_sha256 = current_sha256
        self.card_id = card_id
        self.carrier = carrier

    @property
    def changed_targets(self):
        """fail 目标集的**对称差**（新增的违规项 ∪ 消失的违规项），保序去重。"""
        before = self.previous_fail_targets
        after = self.current_fail_targets
        out = []
        seen = set()
        for target in after:
            if target not in before and target not in seen:
                seen.add(target)
                out.append(target)
        for target in before:
            if target not in after and target not in seen:
                seen.add(target)
                out.append(target)
        return out

    def to_dict(self):
        return {
            "identity": self.identity,
            "status": self.status,
            "path": self.path,
            "card_id": self.card_id,
            "carrier": self.carrier,
            "previous_grade": self.previous_grade,
            "current_grade": self.current_grade,
            "previous_fail_targets": list(self.previous_fail_targets),
            "current_fail_targets": list(self.current_fail_targets),
            "changed_targets": self.changed_targets,
            "content_changed": self.content_changed,
        }

    def __repr__(self):
        return "DiffEntry({0!r}, {1}, content_changed={2})".format(
            self.identity, self.status, self.content_changed)


class DiffResult(object):
    """两轮对账结果（契约见 plan/04 §七）。"""

    SCHEMA_VERSION = 1

    def __init__(self, added=None, fixed=None, persistent=None, stable=None,
                 new_items=None, removed=None, content_changed=None,
                 previous_coordinate="", current_coordinate="", generated_at=""):
        self.added = list(added or [])
        self.fixed = list(fixed or [])
        self.persistent = list(persistent or [])
        self.stable = list(stable or [])
        self.new_items = list(new_items or [])
        self.removed = list(removed or [])
        self.content_changed = list(content_changed or [])
        self.previous_coordinate = previous_coordinate
        self.current_coordinate = current_coordinate
        self.generated_at = generated_at

    @property
    def persistent_with_changes(self):
        """持续违规中 fail 目标集发生变化的件（计划里记作 ``changed_items``）。"""
        return [entry for entry in self.persistent if entry.changed_targets]

    @property
    def summary(self):
        return {
            "added": len(self.added),
            "fixed": len(self.fixed),
            "persistent": len(self.persistent),
            "persistent_changed": len(self.persistent_with_changes),
            "stable": len(self.stable),
            "new_items": len(self.new_items),
            "removed": len(self.removed),
            "content_changed": len(self.content_changed),
        }

    def to_dict(self):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "generated_at": self.generated_at,
            "previous_coordinate": self.previous_coordinate,
            "current_coordinate": self.current_coordinate,
            "summary": self.summary,
            "added": [entry.to_dict() for entry in self.added],
            "fixed": [entry.to_dict() for entry in self.fixed],
            "persistent": [entry.to_dict() for entry in self.persistent],
            "stable": [entry.to_dict() for entry in self.stable],
            "new_items": [entry.to_dict() for entry in self.new_items],
            "removed": [entry.to_dict() for entry in self.removed],
            "content_changed": [entry.to_dict() for entry in self.content_changed],
        }

    @classmethod
    def from_dict(cls, data):
        def entries(key):
            out = []
            for raw in data.get(key, []) or []:
                out.append(DiffEntry(
                    identity=raw.get("identity", ""),
                    status=raw.get("status", ""),
                    path=raw.get("path", ""),
                    previous_grade=raw.get("previous_grade", ""),
                    current_grade=raw.get("current_grade", ""),
                    previous_fail_targets=raw.get("previous_fail_targets"),
                    current_fail_targets=raw.get("current_fail_targets"),
                    content_changed=raw.get("content_changed", False),
                    card_id=raw.get("card_id", ""),
                    carrier=raw.get("carrier", ""),
                ))
            return out

        return cls(
            added=entries("added"),
            fixed=entries("fixed"),
            persistent=entries("persistent"),
            stable=entries("stable"),
            new_items=entries("new_items"),
            removed=entries("removed"),
            content_changed=entries("content_changed"),
            previous_coordinate=data.get("previous_coordinate", ""),
            current_coordinate=data.get("current_coordinate", ""),
            generated_at=data.get("generated_at", ""),
        )

    def __repr__(self):
        return "DiffResult(added={0}, fixed={1}, persistent={2}, stable={3})".format(
            len(self.added), len(self.fixed), len(self.persistent), len(self.stable))


def _has_fail(item):
    return bool(item.fail_targets)


def _entry(identity, status, previous=None, current=None, content_changed=False):
    """由两轮的 :class:`ScanItem` 组装一条 :class:`DiffEntry`。"""
    prev_path = previous.path if previous is not None else ""
    cur_path = current.path if current is not None else ""
    prev_targets = previous.fail_targets if previous is not None else []
    cur_targets = current.fail_targets if current is not None else []
    display = current.path if current is not None else prev_path
    card_id = (current.card_id if current is not None and current.card_id
               else (previous.card_id if previous is not None else ""))
    carrier = (current.carrier if current is not None and current.carrier
               else (previous.carrier if previous is not None else ""))
    return DiffEntry(
        identity=identity,
        status=status,
        path=display,
        previous_path=prev_path,
        current_path=cur_path,
        previous_grade=previous.grade if previous is not None else "",
        current_grade=current.grade if current is not None else "",
        previous_fail_targets=prev_targets,
        current_fail_targets=cur_targets,
        content_changed=content_changed,
        previous_sha256=previous.content_sha256 if previous is not None else "",
        current_sha256=current.content_sha256 if current is not None else "",
        card_id=card_id,
        carrier=carrier,
    )


def _content_changed(previous, current):
    """两轮内容指纹是否不同（**仅在双方都有指纹时**才判"变动"）。

    指纹缺失（如失败件读不到字节）不冒充"未变动"，也不冒充"已变动"——返回 False，
    由调用方从 ``previous_sha256``/``current_sha256`` 的空值看出"无从比较"。
    """
    if previous is None or current is None:
        return False
    before = previous.content_sha256
    after = current.content_sha256
    if not before or not after:
        return False
    return before != after


def diff_scans(previous, current, generated_at=""):
    """对账两轮扫描结果，返回 :class:`DiffResult`（契约见 plan/04 §七）。

    :param previous: 上轮 :class:`ScanResult`
    :param current: 本轮 :class:`ScanResult`
    :param generated_at: 对账时间戳（**由调用方传入**，保证可复现）

    配对按 ``identity``（稳定身份键，口径见 :mod:`labelcheck.scan`）。件序：
    ``added/persistent/stable`` 用**本轮序**，``fixed/removed`` 用**上轮序**
    （确定性；相同输入两次对账逐字节一致）。
    """
    prev_by_id = previous.items_by_identity()
    cur_by_id = current.items_by_identity()

    added = []
    fixed = []
    persistent = []
    stable = []
    new_items = []
    content_changed = []

    for item in current.items:
        identity = item.identity
        before = prev_by_id.get(identity)
        changed = _content_changed(before, item)
        if before is None:
            if _has_fail(item):
                added.append(_entry(identity, STATUS_ADDED, None, item))
            else:
                new_items.append(_entry(identity, STATUS_NEW, None, item))
            if changed:
                content_changed.append(_entry(identity, STATUS_CONTENT_CHANGED, before, item, True))
            continue

        before_fail = _has_fail(before)
        after_fail = _has_fail(item)
        if before_fail and after_fail:
            persistent.append(_entry(identity, STATUS_PERSISTENT, before, item, changed))
        elif before_fail and not after_fail:
            fixed.append(_entry(identity, STATUS_FIXED, before, item, changed))
        elif not before_fail and after_fail:
            added.append(_entry(identity, STATUS_ADDED, before, item, changed))
        else:
            stable.append(_entry(identity, STATUS_STABLE, before, item, changed))

        if changed:
            content_changed.append(_entry(identity, STATUS_CONTENT_CHANGED, before, item, True))

    removed = []
    for item in previous.items:
        if item.identity not in cur_by_id:
            removed.append(_entry(item.identity, STATUS_REMOVED, item, None))

    return DiffResult(
        added=added,
        fixed=fixed,
        persistent=persistent,
        stable=stable,
        new_items=new_items,
        removed=removed,
        content_changed=content_changed,
        previous_coordinate=previous.ruleset_coordinate,
        current_coordinate=current.ruleset_coordinate,
        generated_at=generated_at,
    )


__all__ = [
    "diff_scans", "DiffResult", "DiffEntry",
    "STATUS_ADDED", "STATUS_FIXED", "STATUS_PERSISTENT", "STATUS_STABLE", "STATUS_RESOLVED",
]