# -*- coding: utf-8 -*-
"""批量扫描：目录/清单投喂 → 逐件核验 → :class:`ScanResult`（FR-6，plan/04 §七）。

**逐件走同一条分派**：每件都经 ``engine.check_file``（标识卡 JSON 或容器文件），
与 ``check`` 单件**行为完全一致**——批量与单件不得各写一套分派，否则同一文件
两条通路会给出不同结论（最隐蔽的口径漂移）。

**失败隔离（NFR-8，硬要求）**：单件异常（坏 JSON、非法卡、不可解析容器、读盘失败、
容器过大）**不得**中断整批。该件记一条 ``kind="failed"`` 的记录（``code=scan_error``
或更具体的原因码）后**继续**下一件；批次末尾汇总 ``failed`` 清单。

**确定性（NFR-3）**：件序 = 输入发现序（目录递归时**排序**）；产物无时钟/随机；
``ScanResult.to_dict`` 顺序固定 → 相同输入两次扫描逐字节一致。

**身份键（对账主键，plan/06 D28）**：每件解析出一个**稳定身份键**，用于两轮对账
（见 :mod:`.diff`）：

- 标识卡 JSON 件 → ``card:<card_id>``（人工/上游赋予的逻辑身份；改文件名不改身份）；
- 解析容器件 / 失败件 → ``file:<相对路径>``（容器内容可改而路径稳定；解析件的
  ``card_id`` 由内容派生，内容一变就变，**不能**作身份）。

``content_sha256`` **不参与配对**，只用于独立检测"内容是否变动"（``content_changed``）。
"""

from pathlib import Path

from ..errors import LabelCheckError
from ..jsonio import sha256_file
from ..model import (
    CARRIERS, GRADE_COMPLIANT, GRADE_NON_COMPLIANT, GRADE_NOT_ASSESSED, GRADE_PARTIAL,
    STATUS_FAIL,
)
from ..parse.containers import SUFFIX_TO_CONTAINER

#: 件类型
KIND_CARD = "card"
KIND_CONTAINER = "container"
KIND_FAILED = "failed"

#: 单件失败的原因码（进结果，供报告与对账；**不中断整批**）
CODE_SCAN_ERROR = "scan_error"
CODE_CONTAINER_TOO_LARGE = "container_too_large"

#: 单件容器解析的字节上限（安全阀：超大容器不整体读入，防"一个文件拖垮整批"）。
#: 元数据块本身远小于此；此处只挡"把整部影片读进内存"这一类。可用
#: :func:`scan_paths` 的 ``max_container_bytes`` 覆盖（测试用）。
MAX_CONTAINER_BYTES = 512 * 1024 * 1024

#: 目录递归时纳入的输入后缀（标识卡 JSON + 可解析容器）
INPUT_SUFFIXES = (".json",) + tuple(sorted(SUFFIX_TO_CONTAINER))

#: 清单文件后缀（每行一个路径；``#`` 起始为注释）
MANIFEST_SUFFIXES = (".lst", ".list", ".manifest", ".txt")


class ScanItem(object):
    """一件的扫描结果（成功件含 :class:`CheckReport`；失败件含原因）。"""

    __slots__ = ("path", "kind", "identity", "content_sha256", "card_id", "carrier",
                 "grade", "report", "error", "code", "parse", "reasons",
                 "scenario", "source", "observed")

    def __init__(self, path, kind, identity="", content_sha256="", card_id="",
                 carrier="", grade="", report=None, error="", code="",
                 parse=None, reasons=None, scenario="", source="", observed=None):
        self.path = path
        self.kind = kind
        self.identity = identity
        self.content_sha256 = content_sha256
        self.card_id = card_id
        self.carrier = carrier
        self.grade = grade
        self.report = report
        self.error = error
        self.code = code
        self.parse = parse
        self.reasons = list(reasons) if reasons else []
        self.scenario = scenario
        self.source = source
        self.observed = dict(observed) if observed else {}

    # ------------------------------------------------------------------ 查询
    @property
    def failed(self):
        return self.kind == KIND_FAILED

    @property
    def fail_targets(self):
        """该件全部 ``fail`` 的 target（保序去重；失败件为空）。"""
        if self.report is None:
            return []
        seen = set()
        out = []
        for finding in self.report.all_findings:
            if finding.status == STATUS_FAIL and finding.target not in seen:
                seen.add(finding.target)
                out.append(finding.target)
        return out

    @property
    def review_targets(self):
        """该件全部 ``unknown``（待人工确认）的 target（保序去重）。"""
        if self.report is None:
            return []
        seen = set()
        out = []
        for finding in self.report.all_findings:
            if finding.needs_review and finding.target not in seen:
                seen.add(finding.target)
                out.append(finding.target)
        return out

    @property
    def has_violation(self):
        return bool(self.report is not None and self.report.has_violation)

    # ------------------------------------------------------------------ 序列化
    def to_dict(self):
        payload = {
            "path": self.path,
            "kind": self.kind,
            "identity": self.identity,
            "content_sha256": self.content_sha256,
            "card_id": self.card_id,
            "carrier": self.carrier,
            "source": self.source,
            "scenario": self.scenario,
            "grade": self.grade,
            "observed": dict(self.observed),
            "fail_targets": self.fail_targets,
            "review_targets": self.review_targets,
        }
        if self.failed:
            payload["error"] = self.error
            payload["code"] = self.code
        else:
            payload["report"] = self.report.to_dict()
            if self.parse is not None:
                payload["parse"] = dict(self.parse)
        return payload

    @classmethod
    def from_dict(cls, data):
        """从 :meth:`to_dict` 的产物还原（供 ``scan --baseline`` 读上轮结果）。"""
        kind = data.get("kind", KIND_CARD)
        report = None
        report_data = data.get("report")
        if report_data:
            report = _report_from_dict(report_data)
        parse = data.get("parse")
        return cls(
            path=data.get("path", ""),
            kind=kind,
            identity=data.get("identity", ""),
            content_sha256=data.get("content_sha256", ""),
            card_id=data.get("card_id", ""),
            carrier=data.get("carrier", ""),
            grade=data.get("grade", ""),
            report=report,
            error=data.get("error", ""),
            code=data.get("code", ""),
            parse=parse,
            reasons=(parse or {}).get("reasons", []),
            scenario=data.get("scenario", ""),
            source=data.get("source", ""),
            observed=data.get("observed"),
        )

    def __repr__(self):
        return "ScanItem({0!r}, kind={1}, grade={2!r})".format(
            self.path, self.kind, self.grade)


class ScanResult(object):
    """一次批量扫描的结果（契约见 plan/04 §七）。"""

    SCHEMA_VERSION = 1

    def __init__(self, items, generated_at="", ruleset_coordinate="",
                 verified_rule_count=0, pending_rule_count=0, root="", warnings=None,
                 ruleset_documents=None):
        self.items = list(items)
        self.generated_at = generated_at
        self.ruleset_coordinate = ruleset_coordinate
        self.verified_rule_count = verified_rule_count
        self.pending_rule_count = pending_rule_count
        self.root = root
        self.warnings = list(warnings) if warnings else []
        #: 依据清单（doc 坐标 + 书目元数据；报告"依据清单"段直接取用）
        self.ruleset_documents = list(ruleset_documents) if ruleset_documents else []

    # ------------------------------------------------------------------ 查询
    @property
    def failed(self):
        return [item for item in self.items if item.failed]

    @property
    def checked(self):
        return [item for item in self.items if not item.failed]

    @property
    def violations(self):
        return [item for item in self.checked if item.has_violation]

    def items_by_identity(self):
        """``identity → item``（顺序 = 件序；重复身份按发现序加序号，见 :func:`_assign_identities`）。"""
        return {item.identity: item for item in self.items}

    @property
    def summary(self):
        """批次汇总（顺序固定，确定性）。"""
        grades = {}
        for grade in (GRADE_COMPLIANT, GRADE_PARTIAL, GRADE_NON_COMPLIANT, GRADE_NOT_ASSESSED):
            grades[grade] = 0
        carriers = dict((c, 0) for c in CARRIERS)
        sources = {}
        for item in self.items:
            if item.failed:
                continue
            if item.grade in grades:
                grades[item.grade] += 1
            if item.carrier in carriers:
                carriers[item.carrier] += 1
            sources[item.source] = sources.get(item.source, 0) + 1
        return {
            "total": len(self.items),
            "checked": len(self.checked),
            "failed": len(self.failed),
            "violations": len(self.violations),
            "reviews": sum(1 for item in self.checked if item.review_targets),
            "grades": grades,
            "carriers": carriers,
            "sources": sources,
        }

    # ------------------------------------------------------------------ 序列化
    def to_dict(self):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "root": self.root,
            "generated_at": self.generated_at,
            "ruleset": {
                "coordinate": self.ruleset_coordinate,
                "verified_rule_count": self.verified_rule_count,
                "pending_rule_count": self.pending_rule_count,
                "documents": [dict(doc) for doc in self.ruleset_documents],
            },
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data):
        """从 :meth:`to_dict` 的产物还原（供两轮对账读上轮结果）。"""
        ruleset = data.get("ruleset", {}) or {}
        return cls(
            items=[ScanItem.from_dict(item) for item in data.get("items", [])],
            generated_at=data.get("generated_at", ""),
            ruleset_coordinate=ruleset.get("coordinate", ""),
            verified_rule_count=ruleset.get("verified_rule_count", 0),
            pending_rule_count=ruleset.get("pending_rule_count", 0),
            root=data.get("root", ""),
            warnings=data.get("warnings", []),
            ruleset_documents=ruleset.get("documents"),
        )

    def __repr__(self):
        return "ScanResult(items={0}, violations={1}, failed={2})".format(
            len(self.items), len(self.violations), len(self.failed))


def _report_from_dict(data):
    """把报告 dict 还原为**最小** :class:`CheckReport`（供对账/展示；不重跑规则）。"""
    from ..model import CheckReport, Finding

    def findings(scope):
        out = []
        for raw in data.get(scope, []) or []:
            out.append(Finding(
                scope=raw.get("scope", scope),
                target=raw.get("target", ""),
                status=raw.get("status", ""),
                code=raw.get("code", ""),
                message=raw.get("message", ""),
                clause=raw.get("clause"),
                evidence=raw.get("evidence"),
                severity=raw.get("severity", "major"),
                scenario=raw.get("scenario", "") or "",
            ))
        return out

    ruleset = data.get("ruleset", {}) or {}
    return CheckReport(
        card_id=data.get("card_id", ""),
        carrier=data.get("carrier", ""),
        ruleset_coordinate=ruleset.get("coordinate", ""),
        documents=ruleset.get("documents"),
        verified_rule_count=ruleset.get("verified_rule_count", 0),
        pending_rule_count=ruleset.get("pending_rule_count", 0),
        explicit=findings("explicit"),
        implicit=findings("implicit"),
        grade=data.get("grade", ""),
        missing=data.get("missing"),
        errors=data.get("errors"),
        content_sha256=data.get("content_sha256", ""),
        generated_at=data.get("generated_at", ""),
        disclaimer=data.get("disclaimer"),
        scenario=data.get("scenario", ""),
        source=data.get("source", ""),
        observed=data.get("observed"),
    )


# ---------------------------------------------------------------- 输入发现
def _looks_like_manifest(path):
    return path.suffix.lower() in MANIFEST_SUFFIXES


def iter_input_paths(target, max_depth=None):
    """把扫描目标展开为**输入路径列表**（顺序 = 发现序，确定性）。

    - 目录 → 递归收集 :data:`INPUT_SUFFIXES` 内的文件（**排序**，跨平台一致）；
    - 清单文件（``.lst/.list/.manifest/.txt``）→ 每行一个路径（``#`` 起始为注释；
      相对路径按清单文件所在目录解析）；
    - 其它文件 → 单件。

    :raises UsageError: 目标不存在。
    """
    from ..errors import UsageError

    target = Path(target)
    if not target.exists():
        raise UsageError("扫描目标不存在：{0}".format(target))

    if target.is_dir():
        return _collect_dir(target, max_depth)

    if _looks_like_manifest(target):
        return _collect_manifest(target)

    return [target]


def _collect_dir(root, max_depth=None):
    """递归收集目录内的输入文件（排序；``max_depth`` 限定层级，1 = 仅本层）。"""
    found = []
    base_depth = len(root.parts)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if max_depth is not None and (len(path.parts) - base_depth) > max_depth:
            continue
        if path.suffix.lower() in INPUT_SUFFIXES:
            found.append(path)
    # 排序键取相对路径的 POSIX 形态 → Windows/Linux 顺序一致
    found.sort(key=lambda p: p.relative_to(root).as_posix())
    return found


def _collect_manifest(path):
    """读取清单文件（每行一个路径；空行与 ``#`` 注释忽略）。"""
    from ..errors import UsageError

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError("无法读取清单文件：{0}（{1}）".format(path, exc))

    base = path.parent
    items = []
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        candidate = Path(entry)
        if not candidate.is_absolute():
            candidate = base / candidate
        items.append(candidate)
    if not items:
        raise UsageError("清单文件不含任何路径：{0}".format(path))
    return items


# ---------------------------------------------------------------- 扫描主流程
def scan_paths(paths, data_dir, generated_at="", scenario=None, root="",
               progress_every=0, progress_stream=None, max_container_bytes=None,
               quiet=False):
    """逐件核验给定路径，返回 :class:`ScanResult`（失败件隔离，不中断整批）。

    :param paths: 输入路径序列（:func:`iter_input_paths` 的产物或任意可迭代）
    :param data_dir: 数据目录
    :param generated_at: 报告时间戳（**由调用方传入**，保证可复现）
    :param scenario: 覆盖卡内场景（``None`` = 用卡内声明/默认）
    :param root: 扫描根（进结果，作展示与身份键的相对基准）
    :param progress_every: 每 N 件向 ``progress_stream`` 打一行进度（0 = 关闭）
    :param max_container_bytes: 单件容器解析字节上限（``None`` = :data:`MAX_CONTAINER_BYTES`）
    :param quiet: 关闭进度（``progress_every`` 同时给出时以 ``quiet`` 为准）
    """
    import sys

    from ..rules import effective_ruleset

    data_dir = Path(data_dir)
    root_path = Path(root) if root else None
    limit = MAX_CONTAINER_BYTES if max_container_bytes is None else max_container_bytes
    stream = progress_stream if progress_stream is not None else sys.stderr

    paths = list(paths)
    ruleset = effective_ruleset(data_dir)

    items = []
    for index, path in enumerate(paths, start=1):
        item = _scan_one(path, data_dir, generated_at, scenario, root_path, limit)
        items.append(item)
        if progress_every and not quiet and (index % progress_every == 0):
            stream.write("扫描进度：{0}/{1}（已检出违规 {2}、失败 {3}）\n".format(
                index, len(paths),
                sum(1 for it in items if it.has_violation),
                sum(1 for it in items if it.failed),
            ))

    _assign_identities(items)
    return ScanResult(
        items=items,
        generated_at=generated_at,
        ruleset_coordinate=ruleset.coordinate,
        verified_rule_count=ruleset.verified_rule_count,
        pending_rule_count=ruleset.pending_rule_count,
        root=str(root_path) if root_path else "",
        warnings=ruleset.warnings,
        ruleset_documents=ruleset.doc_versions,
    )


def scan_target(target, data_dir, **kwargs):
    """:func:`iter_input_paths` + :func:`scan_paths` 的组合（CLI 主通路）。"""
    target = Path(target)
    paths = iter_input_paths(target)
    root = str(target) if target.is_dir() else str(target.parent)
    return scan_paths(paths, data_dir, root=root, **kwargs)


def _scan_one(path, data_dir, generated_at, scenario, root_path, limit):
    """核验单件；任何异常都转成 ``kind="failed"`` 记录（失败隔离）。"""
    from ..engine import check_file

    path = Path(path)
    display = _display_path(path, root_path)

    # 安全阀：超大容器不整体读入（防一个文件拖垮整批）
    if path.is_file() and path.suffix.lower() in SUFFIX_TO_CONTAINER:
        try:
            size = path.stat().st_size
        except OSError as exc:
            return _failed(display, "file:{0}".format(display), "", "无法读取文件属性：{0}".format(exc),
                           CODE_SCAN_ERROR)
        if limit is not None and size > limit:
            return _failed(
                display, "file:{0}".format(display), "",
                "容器体积 {0} 字节超过单件解析上限 {1} 字节，未解析（避免拖垮整批）".format(size, limit),
                CODE_CONTAINER_TOO_LARGE)

    try:
        report, parse_outcome = check_file(
            path, data_dir, generated_at=generated_at, scenario=scenario)
    except LabelCheckError as exc:
        fingerprint = _safe_file_sha256(path)
        return _failed(display, "file:{0}".format(display), fingerprint,
                       str(exc), CODE_SCAN_ERROR)
    except Exception as exc:  # noqa: BLE001 - 失败隔离：任何单件异常都不得中断整批
        fingerprint = _safe_file_sha256(path)
        return _failed(display, "file:{0}".format(display), fingerprint,
                       "未预期异常：{0}: {1}".format(type(exc).__name__, exc), CODE_SCAN_ERROR)

    if parse_outcome is not None:
        kind = KIND_CONTAINER
        identity = "file:{0}".format(display)
        parse_block = {
            "container": parse_outcome.container,
            "implicit_observed": parse_outcome.implicit_observed,
            "explicit_observed": parse_outcome.explicit_observed,
            "aigc_field_count": parse_outcome.aigc_field_count,
            "payload_count": parse_outcome.payload_count,
            "reasons": list(parse_outcome.reasons),
        }
        reasons = list(parse_outcome.reasons)
    else:
        kind = KIND_CARD
        identity = "card:{0}".format(report.card_id)
        parse_block = None
        reasons = []

    return ScanItem(
        path=display,
        kind=kind,
        identity=identity,
        content_sha256=report.content_sha256,
        card_id=report.card_id,
        carrier=report.carrier,
        grade=report.grade,
        report=report,
        parse=parse_block,
        reasons=reasons,
        scenario=report.scenario,
        source=report.source,
        observed=report.observed,
    )


def _failed(display, identity, fingerprint, message, code):
    return ScanItem(
        path=display, kind=KIND_FAILED, identity=identity,
        content_sha256=fingerprint, error=message, code=code,
    )


def _display_path(path, root_path):
    """展示路径：能相对扫描根表示则用相对 POSIX 形态（跨平台一致），否则原样。"""
    path = Path(path)
    if root_path is not None:
        try:
            return path.resolve().relative_to(Path(root_path).resolve()).as_posix()
        except (ValueError, OSError):
            pass
    return path.as_posix()


def _safe_file_sha256(path):
    try:
        if Path(path).is_file():
            return sha256_file(path)
    except OSError:
        pass
    return ""


def _assign_identities(items):
    """身份键冲突消解：同键按发现序加序号（``#2``、``#3``…），**不丢件**。

    同键冲突（如两张卡声明同一 ``card_id``、或同一路径被清单重复列出）是数据质量
    问题，但批量扫描**不得**因此少算件——故保留全部件并确定性地区分身份。
    """
    seen = {}
    for item in items:
        base = item.identity or "file:{0}".format(item.path)
        count = seen.get(base, 0) + 1
        seen[base] = count
        item.identity = base if count == 1 else "{0}#{1}".format(base, count)


__all__ = [
    "scan_paths", "scan_target", "iter_input_paths",
    "ScanItem", "ScanResult",
    "KIND_CARD", "KIND_CONTAINER", "KIND_FAILED",
    "CODE_SCAN_ERROR", "CODE_CONTAINER_TOO_LARGE",
    "MAX_CONTAINER_BYTES", "INPUT_SUFFIXES", "MANIFEST_SUFFIXES",
]