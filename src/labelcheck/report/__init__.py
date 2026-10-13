# -*- coding: utf-8 -*-
"""报告导出与证据链（FR-8 / FR-9，契约见 plan/04 §八）。

**定位**：把一次批量扫描（:class:`~labelcheck.scan.scanner.ScanResult`）导出为
人类可读报告与机器可读明细，并固化证据链。

导出格式（plan/04 §八.2）：

============================  ================  ==========================
文件                           依赖              降级
============================  ================  ==========================
``report.md``                  无                —
``summary.csv``                无                —
``detail.csv``                 无                —
``report.xlsx``                ``openpyxl``      缺失 → 打印安装提示并**只导 CSV**（exit 0，不崩）
``evidence.json``              无                —
============================  ================  ==========================

**证据链（FR-9 / 系列招牌）**：``evidence.json`` 固化每件 ``content_sha256``、
规则库坐标，并写入**报告自身的 sha256**——报告被改动即可检出（对照复现）。

**确定性（NFR-3）**：``generated_at`` **由调用方传入**（基准/测试传固定值），
产物无时钟/随机 → 相同输入两次导出**逐字节一致**（守门测试锁死）。

**零第三方（NFR-1/D05）**：本模块顶层只依赖 stdlib；``openpyxl`` 在函数体内惰性
导入（架构守门测试允许 ``report`` 模块 import 第三方重件，见 ``test_guard_imports``）。
"""

import csv
import io

from .. import DISCLAIMER
from ..jsonio import canonical_json, sha256_bytes, sha256_text, write_text_lf
from ..model import (
    GRADE_COMPLIANT, GRADE_NON_COMPLIANT, GRADE_NOT_ASSESSED, GRADE_PARTIAL,
    SEVERITY_CRITICAL, SEVERITY_MAJOR, SEVERITY_MINOR,
)

#: 导出文件名（固定 → 证据链可引用）
REPORT_MD = "report.md"
SUMMARY_CSV = "summary.csv"
DETAIL_CSV = "detail.csv"
REPORT_XLSX = "report.xlsx"
EVIDENCE_JSON = "evidence.json"

#: 严重度排序权重（违规清单按此排序：critical → major → minor）
_SEVERITY_ORDER = {SEVERITY_CRITICAL: 0, SEVERITY_MAJOR: 1, SEVERITY_MINOR: 2}

#: 等级中文名（报告可读性；数值口径仍是英文枚举）
GRADE_LABELS = {
    GRADE_COMPLIANT: "完全合规",
    GRADE_PARTIAL: "部分合规",
    GRADE_NON_COMPLIANT: "不合规",
    GRADE_NOT_ASSESSED: "未评估",
}


class ReportBundle(object):
    """一次导出的产物集合：文件相对名 → 文本内容 + 各文件 sha256。"""

    def __init__(self, files=None, xlsx_written=False, xlsx_hint="", evidence=None):
        self.files = dict(files or {})          # {relname: text}
        self.xlsx_written = xlsx_written
        self.xlsx_hint = xlsx_hint
        self.evidence = dict(evidence or {})

    @property
    def file_hashes(self):
        return dict((name, sha256_text(text)) for name, text in self.files.items())

    @property
    def report_sha256(self):
        """报告主体（``report.md``）的 sha256（证据链核心）。"""
        return sha256_text(self.files.get(REPORT_MD, ""))

    def write_to(self, out_dir):
        """把全部产物落盘（文本以 LF 写，二进制原样写），返回写出路径（顺序固定）。"""
        from pathlib import Path

        out_dir = Path(out_dir)
        written = []
        for name in sorted(self.files):
            path = out_dir / name
            content = self.files[name]
            if isinstance(content, bytes):
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(str(path), "wb") as handle:
                    handle.write(content)
            else:
                write_text_lf(path, content)
            written.append(path)
        return written

    def __repr__(self):
        return "ReportBundle(files={0}, xlsx={1})".format(
            sorted(self.files), self.xlsx_written)


# ------------------------------------------------------------------ Markdown
def render_markdown(scan, diff=None, generated_at=""):
    """渲染 ``report.md``（固定骨架见 plan/04 §八.1）。"""
    lines = []
    summary = scan.summary
    lines.append("# AI 生成合成内容标识合规核查报告")
    lines.append("")
    lines.append("- 生成时间：{0}".format(generated_at or "(未提供)"))
    lines.append("- 规则库坐标：{0}".format(scan.ruleset_coordinate or "(无)"))
    lines.append("- 生效规则 / 待核对：{0} / {1}".format(
        scan.verified_rule_count, scan.pending_rule_count))
    if scan.root:
        lines.append("- 扫描根：{0}".format(scan.root))
    lines.append("")

    # 免责声明（强制段，不可省略）
    lines.append("> **免责声明**：{0}".format(DISCLAIMER))
    lines.append("")

    # 核查范围
    lines.append("## 一、核查范围")
    lines.append("")
    lines.append("- 件数：共 {0} 件（已核验 {1}，失败 {2}）".format(
        summary["total"], summary["checked"], summary["failed"]))
    lines.append("- 检出违规件：{0}；含待人工确认项件：{1}".format(
        summary["violations"], summary["reviews"]))
    lines.append("- 载体分布：{0}".format(_kv(summary["carriers"])))
    lines.append("- 数据来源分布：{0}".format(_kv(summary["sources"]) or "(无)"))
    lines.append("- 合规等级分布：{0}".format(_grade_kv(summary["grades"])))
    scenarios = _distinct(item.scenario for item in scan.checked)
    if scenarios:
        lines.append("- 适用场景：{0}".format("、".join(scenarios)))
    unobserved = _distinct(
        scope for item in scan.checked for scope in
        [key for key in ("explicit", "implicit") if not item.observed.get(key, True)])
    if unobserved:
        lines.append("- 未观测作用域（相关判定为 unknown，**不代表合规或违规**）：{0}".format(
            "、".join(unobserved)))
    degraded = [(item.path, item.reasons) for item in scan.checked if item.reasons]
    if degraded:
        lines.append("- 解析降级件（原因码见明细）：{0} 件".format(len(degraded)))
        for path, reasons in degraded:
            lines.append("  - {0}：{1}".format(path, "、".join(reasons)))
    lines.append("")

    # 依据清单
    lines.append("## 二、依据清单")
    lines.append("")
    for entry in _basis_entries(scan):
        lines.append("- **{0}**（{1}，{2}）—— 版本 {3}，施行 {4}；status={5}".format(
            entry.get("title", entry.get("doc_id", "")),
            entry.get("doc_number", ""),
            entry.get("issuer", ""),
            entry.get("version", ""),
            entry.get("effective_from", ""),
            entry.get("status", ""),
        ))
    lines.append("")

    # 逐件逐字段结果
    lines.append("## 三、逐件逐字段结果")
    lines.append("")
    lines.append("### 3.1 逐件可观测性（M2 口径：解析件显式恒未观测，不代表合规或违规）")
    lines.append("")
    lines.append("| 件 id | 路径 | 来源 | 场景 | 显式已观测 | 隐式已观测 | 解析降级原因 |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in scan.items:
        if item.failed:
            lines.append("| （失败件） | {0} | — | — | — | — | {1} |".format(
                _cell(item.path), _cell(item.error)))
            continue
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
            _cell(item.card_id), _cell(item.path), _cell(item.source),
            _cell(item.scenario),
            _observed_label(item.observed.get("explicit", True)),
            _observed_label(item.observed.get("implicit", True)),
            _cell("、".join(item.reasons) or "—")))
    lines.append("")

    lines.append("### 3.2 逐要素/逐字段判定")
    lines.append("")
    lines.append("| 件 id | 载体 | 要素/字段 | 状态 | 严重度 | 原因码 | 条款 |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in scan.items:
        if item.failed:
            lines.append("| {0} | — | — | failed | — | {1} | — |".format(
                _cell(item.card_id or item.path), _cell(item.code)))
            continue
        for finding in item.report.all_findings:
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
                _cell(item.card_id), _cell(item.carrier), _cell(finding.target),
                _cell(finding.status), _cell(finding.severity), _cell(finding.code),
                _cell(_clause_text(finding.clause))))
    lines.append("")

    # 违规清单
    lines.append("## 四、违规清单（按严重度排序）")
    lines.append("")
    violations = _violations_sorted(scan)
    if not violations:
        lines.append("（无明确不合规项）")
    else:
        lines.append("| 件 id | 载体 | 要素/字段 | 严重度 | 原因码 | 条款 |")
        lines.append("|---|---|---|---|---|---|")
        for item, finding in violations:
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                _cell(item.card_id), _cell(item.carrier), _cell(finding.target),
                _cell(finding.severity), _cell(finding.code),
                _cell(_clause_text(finding.clause))))
    lines.append("")

    # 失败件清单（失败隔离的可观测输出）
    if scan.failed:
        lines.append("## 五、失败件清单（未中断整批，逐件原因见下）")
        lines.append("")
        lines.append("| 件 | 原因码 | 说明 |")
        lines.append("|---|---|---|")
        for item in scan.failed:
            lines.append("| {0} | {1} | {2} |".format(
                _cell(item.path), _cell(item.code), _cell(item.error)))
        lines.append("")

    # 两轮对账
    if diff is not None:
        lines.append("## 六、两轮对账")
        lines.append("")
        lines.append("- 上轮坐标：{0}".format(diff.previous_coordinate or "(无)"))
        lines.append("- 本轮坐标：{0}".format(diff.current_coordinate or "(无)"))
        dsummary = diff.summary
        lines.append("- 新增违规 {0}；已修复 {1}；持续违规 {2}（其中违规项变化 {3}）；"
                     "内容变动 {4}".format(
                         dsummary["added"], dsummary["fixed"], dsummary["persistent"],
                         dsummary["persistent_changed"], dsummary["content_changed"]))
        lines.append("")
        for title, entries in (
            ("新增违规", diff.added), ("已修复", diff.fixed),
            ("持续违规", diff.persistent), ("内容变动", diff.content_changed),
        ):
            if not entries:
                continue
            lines.append("### {0}".format(title))
            lines.append("")
            for entry in entries:
                lines.append("- {0}（{1}）：{2} → {3}{4}".format(
                    entry.card_id or entry.identity, entry.path,
                    entry.previous_grade or "—", entry.current_grade or "—",
                    "（内容已变动）" if entry.content_changed else ""))
            lines.append("")

    # 结论与建议
    lines.append("## 七、结论与建议")
    lines.append("")
    lines.append("- 等级汇总：{0}".format(_grade_kv(summary["grades"])))
    if summary["violations"]:
        lines.append("- 建议：优先整改 **critical/major** 级违规项（见第四节）；"
                     "对 `unknown` 项补充输入后复检。")
    elif summary["failed"]:
        lines.append("- 建议：先修复失败件（读取/格式问题），再复核其标识。")
    else:
        lines.append("- 未发现明确不合规项；`unknown` 项需人工确认后定论。")
    lines.append("- {0}".format(DISCLAIMER))
    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ CSV
def _csv_text(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def render_summary_csv(scan):
    """汇总表：每件一行（件 id、路径、载体、来源、场景、等级、违规/待确认目标、解析降级）。"""
    header = ["card_id", "path", "kind", "carrier", "source", "scenario",
              "grade", "fail_targets", "review_targets", "parse_reasons", "error"]
    rows = []
    for item in scan.items:
        rows.append([
            item.card_id,
            item.path,
            item.kind,
            item.carrier,
            item.source,
            item.scenario,
            item.grade,
            ";".join(item.fail_targets),
            ";".join(item.review_targets),
            ";".join(item.reasons),
            item.error,
        ])
    return _csv_text(header, rows)


def render_detail_csv(scan):
    """明细表：每个 Finding 一行（含条款与证据）。"""
    header = ["card_id", "path", "carrier", "scope", "target", "status", "severity",
              "code", "scenario", "clause_article", "clause_doc", "observed", "expected"]
    rows = []
    for item in scan.items:
        if item.failed:
            rows.append([item.card_id, item.path, "", "", "", "failed", "", item.code,
                         "", "", "", "", item.error])
            continue
        for finding in item.report.all_findings:
            evidence = finding.evidence or {}
            rows.append([
                item.card_id,
                item.path,
                item.carrier,
                finding.scope,
                finding.target,
                finding.status,
                finding.severity,
                finding.code,
                finding.scenario,
                finding.clause.get("article", ""),
                finding.clause.get("doc_id", ""),
                _evidence_text(evidence.get("observed")),
                _evidence_text(evidence.get("expected")),
            ])
    return _csv_text(header, rows)


# ------------------------------------------------------------------ XLSX
#: XLSX 文档属性的确定性时间基准（openpyxl 默认把文档属性写成"当前时刻" → 产物不可复现）。
#: 无 ``generated_at`` 时用此固定常量；有则可解析的 ISO 时间时用调用方传入值。
_XLSX_EPOCH = "2025-01-01T00:00:00"


def _xlsx_timestamp(generated_at):
    """把调用方时间戳转成 XLSX 文档属性用的 ``datetime``（不可解析则用固定基准）。

    openpyxl 会在 ``docProps/core.xml`` 写入 ``created``/``modified``——默认取系统时钟，
    会让"相同输入两次导出逐字节一致"失效。故**显式钉死**为调用方传入值或固定常量。
    """
    import datetime

    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(generated_at, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.datetime.strptime(_XLSX_EPOCH, "%Y-%m-%dT%H:%M:%S")


def render_xlsx_bytes(scan, generated_at=""):
    """用 ``openpyxl`` 生成 XLSX 字节；**缺失时抛 ImportError**（由调用方降级）。

    文档属性时间戳**钉死**为 ``generated_at``（或固定基准）→ 产物可复现。
    """
    from openpyxl import Workbook  # 惰性导入（第三方重件，仅本函数需要）

    workbook = Workbook()
    stamp = _xlsx_timestamp(generated_at)
    workbook.properties.created = stamp
    workbook.properties.modified = stamp

    sheet = workbook.active
    sheet.title = "summary"
    header = ["card_id", "path", "kind", "carrier", "source", "scenario", "grade",
              "fail_targets", "review_targets", "parse_reasons", "error"]
    sheet.append(header)
    for item in scan.items:
        sheet.append([
            item.card_id, item.path, item.kind, item.carrier, item.source,
            item.scenario, item.grade, ";".join(item.fail_targets),
            ";".join(item.review_targets), ";".join(item.reasons), item.error,
        ])

    detail = workbook.create_sheet("detail")
    detail.append(["card_id", "path", "carrier", "scope", "target", "status",
                   "severity", "code", "scenario", "clause_article"])
    for item in scan.items:
        if item.failed:
            continue
        for finding in item.report.all_findings:
            detail.append([
                item.card_id, item.path, item.carrier, finding.scope, finding.target,
                finding.status, finding.severity, finding.code, finding.scenario,
                finding.clause.get("article", ""),
            ])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return _normalize_xlsx_zip(buffer.getvalue(), generated_at=generated_at)


def _normalize_xlsx_zip(raw, generated_at=""):
    """把 XLSX（zip）重打包为**确定性字节**：条目顺序、压缩级别、时间戳全部钉死。

    ``openpyxl`` 落盘的 zip 条目带**当前系统时间**（``ZipInfo.date_time``），且
    ``docProps/core.xml`` 的 ``modified`` 由 openpyxl 在 save 时写成当前时刻
    ——两者都会让"相同输入两次导出逐字节一致"失效（实测：间隔 1 秒以上导出即不同字节）。
    故解包后：条目按名排序、时间戳钉为 ``(1980,1,1,0,0,0)``，并把 ``core.xml`` 的
    ``created``/``modified`` 重写为钉死值——纯 stdlib。
    """
    import zipfile

    stamp = generated_at if _is_iso(generated_at) else _XLSX_EPOCH
    source = zipfile.ZipFile(io.BytesIO(raw))
    names = sorted(source.namelist())
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for name in names:
            payload = source.read(name)
            if name == "docProps/core.xml":
                payload = _pin_core_timestamps(payload, stamp)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            target.writestr(info, payload)
    source.close()
    return out.getvalue()


def _is_iso(value):
    if not value:
        return False
    import re
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2})?$", value))


def _pin_core_timestamps(payload, stamp):
    """把 ``core.xml`` 里的 ``dcterms:created`` / ``dcterms:modified`` 值换成钉死时间。"""
    import re

    iso = stamp.replace(" ", "T")
    if len(iso) == 10:
        iso += "T00:00:00"
    text = payload.decode("utf-8")
    for tag in ("created", "modified"):
        text = re.sub(
            r"(<dcterms:{0}[^>]*>)[^<]*(</dcterms:{0}>)".format(tag),
            r"\g<1>{0}Z\g<2>".format(iso), text)
    return text.encode("utf-8")


# ------------------------------------------------------------------ 证据链
def render_evidence(scan, artifacts, generated_at="", diff=None):
    """构造 ``evidence.json`` 载荷（含报告自身 sha256）。

    :param artifacts: ``{文件名: 文本内容}``——用于计算各产物 sha256；
        ``report.md`` 的 sha256 即"报告自身指纹"。
    """
    report_sha = sha256_text(artifacts.get(REPORT_MD, ""))
    items = []
    for item in scan.items:
        record = {
            "identity": item.identity,
            "path": item.path,
            "card_id": item.card_id,
            "content_sha256": item.content_sha256,
            "carrier": item.carrier,
            "grade": item.grade,
            "fail_targets": item.fail_targets,
        }
        if item.failed:
            record["error"] = item.error
            record["code"] = item.code
        items.append(record)

    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "ruleset_coordinate": scan.ruleset_coordinate,
        "verified_rule_count": scan.verified_rule_count,
        "pending_rule_count": scan.pending_rule_count,
        "report_sha256": report_sha,
        "artifacts": dict(
            (name, sha256_text(text)) for name, text in sorted(artifacts.items())),
        "summary": scan.summary,
        "items": items,
        "disclaimer": DISCLAIMER,
    }
    if diff is not None:
        payload["diff"] = diff.to_dict()
    return payload


# ------------------------------------------------------------------ 编排
def build_report(scan, generated_at="", diff=None, include_xlsx=True):
    """渲染全部产物（**不落盘**），返回 :class:`ReportBundle`。

    XLSX 生成失败（``openpyxl`` 缺失）→ 只导 CSV，``xlsx_hint`` 带安装提示，
    **不抛异常、不影响 exit 0**（plan/04 §八.2）。
    """
    files = {
        REPORT_MD: render_markdown(scan, diff=diff, generated_at=generated_at),
        SUMMARY_CSV: render_summary_csv(scan),
        DETAIL_CSV: render_detail_csv(scan),
    }

    xlsx_written = False
    xlsx_hint = ""
    if include_xlsx:
        try:
            raw = render_xlsx_bytes(scan, generated_at=generated_at)
        except ImportError:
            from ..paths import is_frozen

            if is_frozen():
                # 冻结态 exe：用户装不了 openpyxl（那是在源码环境里的办法），
                # 故提示改为"该发行包未内嵌 XLSX 导出"，不误导用户去 pip install。
                xlsx_hint = (
                    "本发行包未内嵌 XLSX 导出，已导出 CSV（report.xlsx 跳过）。"
                    "CSV 可用 Excel 直接打开；如需 XLSX，请用带 report extra 的源码安装。")
            else:
                xlsx_hint = (
                    "未安装 openpyxl，已跳过 report.xlsx（已导出 CSV）。"
                    "如需 XLSX：pip install openpyxl 或 pip install -e \".[report]\"")
        else:
            files[REPORT_XLSX] = raw
            xlsx_written = True

    # evidence 的 artifacts 指纹只覆盖**文本产物**（XLSX 为二进制，另行按字节计）
    text_artifacts = dict((name, text) for name, text in files.items()
                          if isinstance(text, str))
    evidence = render_evidence(scan, text_artifacts, generated_at=generated_at, diff=diff)
    if xlsx_written:
        evidence["artifacts"][REPORT_XLSX] = sha256_bytes(files[REPORT_XLSX])
    files[EVIDENCE_JSON] = canonical_json(evidence, indent=2) + "\n"

    return ReportBundle(files=files, xlsx_written=xlsx_written,
                        xlsx_hint=xlsx_hint, evidence=evidence)


def write_report(scan, out_dir, generated_at="", diff=None, include_xlsx=True):
    """渲染并落盘全部产物，返回 ``(bundle, written_paths)``。"""
    bundle = build_report(scan, generated_at=generated_at, diff=diff,
                          include_xlsx=include_xlsx)
    written = bundle.write_to(out_dir)
    return bundle, written


# ------------------------------------------------------------------ 辅助
def _cell(value):
    """Markdown 表格单元转义（``|`` 会打断表格）。"""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _clause_text(clause):
    if not clause:
        return ""
    article = clause.get("article", "")
    doc = clause.get("doc_id", "")
    if doc and article:
        return "{0} {1}".format(doc, article)
    return article or doc


def _observed_label(value):
    return "是" if value else "否（相关判定为 unknown）"


def _evidence_text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def _kv(mapping):
    return "、".join("{0}={1}".format(key, mapping[key]) for key in sorted(mapping))


def _grade_kv(grades):
    parts = []
    for grade in (GRADE_COMPLIANT, GRADE_PARTIAL, GRADE_NON_COMPLIANT, GRADE_NOT_ASSESSED):
        count = grades.get(grade, 0)
        if count:
            parts.append("{0}({1})={2}".format(GRADE_LABELS.get(grade, grade), grade, count))
    return "、".join(parts) if parts else "(无)"


def _distinct(values):
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _violations_sorted(scan):
    """全部违规（件, finding），按 severity → 件序 → 目标 排序（确定性）。"""
    rows = []
    for index, item in enumerate(scan.items):
        if item.failed:
            continue
        for finding in item.report.violations:
            rows.append((index, item, finding))
    rows.sort(key=lambda row: (
        _SEVERITY_ORDER.get(row[2].severity, 9), row[0], row[2].target))
    return [(item, finding) for _, item, finding in rows]


def _basis_entries(scan):
    """依据清单：取扫描结果携带的文档坐标（含 registry 书目元数据，单一来源）。"""
    entries = []
    for doc in getattr(scan, "ruleset_documents", None) or []:
        entries.append({
            "doc_id": doc.get("doc_id", ""),
            "title": doc.get("title") or doc.get("doc_id", ""),
            "doc_number": doc.get("doc_number", ""),
            "issuer": doc.get("issuer", ""),
            "version": doc.get("version", ""),
            "effective_from": doc.get("effective_from") or doc.get("version", ""),
            "status": doc.get("status", ""),
        })
    return entries


__all__ = [
    "build_report", "write_report", "ReportBundle",
    "render_markdown", "render_summary_csv", "render_detail_csv",
    "render_xlsx_bytes", "render_evidence",
    "REPORT_MD", "SUMMARY_CSV", "DETAIL_CSV", "REPORT_XLSX", "EVIDENCE_JSON",
    "GRADE_LABELS",
]