# -*- coding: utf-8 -*-
"""GUI 文本与表格渲染：把引擎对象转成界面可显示的行/文本（**零判定逻辑**）。

本模块是**表现层**：只做"引擎字段 → 展示行"的搬运，不新增任何判定、分级或分派。
每一行的取值都直接来自引擎对象的既有属性（``CheckReport`` / ``ScanResult`` /
``DiffResult`` / ``BenchReport`` / ``Ruleset``），所以界面与 CLI 的结论天然一致。

**为什么不做成"CLI 输出复用"**：CLI 的人类可读输出是为终端排版（缩进 + 中文冒号）而写，
直接塞进表格控件既不好看也不好选；这里改成"结构化行 + 概要文本"两种形态，Qt 层各取所需。
标签类文案（等级中文名）从 :mod:`labelcheck.report` 复用，避免出现第二份口径。
"""

from ..report import GRADE_LABELS

#: 判定状态的中文名（**展示用**；数值口径仍是引擎的英文枚举）
STATUS_LABELS = {
    "pass": "通过",
    "fail": "违规",
    "unknown": "待人工确认",
    "skipped": "不适用",
}

#: 严重度的中文名（展示用）
SEVERITY_LABELS = {
    "critical": "严重",
    "major": "主要",
    "minor": "轻微",
}


def grade_label(grade):
    """合规等级中文名（未收录的取值原样返回，不臆造）。"""
    return GRADE_LABELS.get(grade, grade)


def status_label(status):
    return STATUS_LABELS.get(status, status)


def severity_label(severity):
    return SEVERITY_LABELS.get(severity, severity)


def _clause_text(clause):
    """条款展示串：``条号 — 要点``（缺一即省略，不编造）。"""
    if not clause:
        return ""
    article = clause.get("article", "") or ""
    excerpt = clause.get("excerpt", "") or ""
    if article and excerpt:
        return "{0} — {1}".format(article, excerpt)
    return article or excerpt


# ------------------------------------------------------------------ 单件核验
def report_summary(report):
    """单件核验概要：``[(标签, 值)]``（顺序固定）。"""
    rows = [
        ("件标识", report.card_id),
        ("载体", report.carrier),
        ("场景", report.scenario),
        ("来源", report.source),
        ("合规等级", "{0}（{1}）".format(report.grade, grade_label(report.grade))),
        ("内容指纹", report.content_sha256),
        ("规则库坐标", report.ruleset_coordinate),
        ("生效/待核对规则", "{0} / {1}".format(
            report.verified_rule_count, report.pending_rule_count)),
        ("违规项", "{0} 项".format(len(report.violations))),
        ("待人工确认", "{0} 项".format(len(report.reviews))),
    ]
    unobserved = report.unobserved_scopes
    rows.append(("未观测作用域", "、".join(unobserved) if unobserved else "无"))
    if report.missing:
        rows.append(("缺失项", "、".join(report.missing)))
    if report.errors:
        rows.append(("错误码", "、".join(report.errors)))
    return rows


def finding_rows(report):
    """逐条判定行：``(作用域, 目标, 状态, 严重度, 原因码, 说明, 条款)``。"""
    rows = []
    for finding in report.all_findings:
        rows.append((
            finding.scope,
            finding.target,
            "{0}（{1}）".format(finding.status, status_label(finding.status)),
            severity_label(finding.severity),
            finding.code,
            finding.message,
            _clause_text(finding.clause),
        ))
    return rows


FINDING_COLUMNS = ("作用域", "目标", "状态", "严重度", "原因码", "说明", "条款")


def report_text(result):
    """单件核验的整段可读文本（供"复制结果"与文本框展示）。"""
    report = result.report
    lines = ["核查结论：{0}".format(report.card_id)]
    if result.parsed_from_container:
        lines.append("输入路径：{0}（容器解析通路）".format(result.path))
    else:
        lines.append("输入路径：{0}（标识卡通路）".format(result.path))
    for label, value in report_summary(report):
        lines.append("  {0}：{1}".format(label, value))
    if result.parse is not None:
        lines.append("  解析：容器={0} AIGC 字段={1} 载荷块={2}".format(
            result.parse.container or "(未识别)",
            result.parse.aigc_field_count, result.parse.payload_count))
        for reason in result.parse.reasons:
            lines.append("    解析提示：{0}".format(reason))
    if report.all_findings:
        lines.append("逐条判定：")
        for row in finding_rows(report):
            lines.append("  [{0}] {1}:{2} {3}{4}".format(
                row[2], row[0], row[1], row[4],
                (" — " + row[5]) if row[5] else ""))
    else:
        lines.append("逐条判定：（无——当前场景/载体下无适用规则，属未评估）")
    lines.append(report.disclaimer)
    return "\n".join(lines)


# ------------------------------------------------------------------ 批量扫描
def scan_summary(result):
    """批量概要：``[(标签, 值)]``。"""
    summary = result.summary
    grades = summary["grades"]
    return [
        ("扫描根", result.root or "(单文件)"),
        ("规则库坐标", result.ruleset_coordinate),
        ("生效/待核对规则", "{0} / {1}".format(
            result.verified_rule_count, result.pending_rule_count)),
        ("件数", "{0}（已核验 {1}，失败 {2}）".format(
            summary["total"], summary["checked"], summary["failed"])),
        ("检出违规", "{0} 件；待人工确认 {1} 件".format(
            summary["violations"], summary["reviews"])),
        ("等级分布", "、".join("{0}={1}".format(grade_label(k), v)
                            for k, v in sorted(grades.items()) if v)),
        ("载体分布", "、".join("{0}={1}".format(k, v)
                            for k, v in sorted(summary["carriers"].items()) if v)),
    ]


SCAN_ITEM_COLUMNS = ("状态", "件标识", "路径", "载体", "等级", "违规目标", "待确认目标")


def scan_item_rows(result):
    """逐件行：``(状态, 件标识, 路径, 载体, 等级, 违规目标, 待确认目标)``。"""
    rows = []
    for item in result.items:
        if item.failed:
            rows.append(("失败", item.card_id or "-", item.path, "-", "-",
                         item.code, item.error))
            continue
        rows.append((
            "已核验",
            item.card_id,
            item.path,
            item.carrier,
            "{0}（{1}）".format(item.grade, grade_label(item.grade)),
            "、".join(item.fail_targets) or "-",
            "、".join(item.review_targets) or "-",
        ))
    return rows


def scan_text(batch):
    """批量扫描的整段可读文本（含对账段）。"""
    result = batch.result
    lines = ["批量扫描完成"]
    for label, value in scan_summary(result):
        lines.append("  {0}：{1}".format(label, value))
    if batch.diff is not None:
        lines.append("两轮对账：")
        for label, value in diff_summary(batch.diff):
            lines.append("  {0}：{1}".format(label, value))
    if result.failed:
        lines.append("失败件（已隔离，未中断整批）：")
        for item in result.failed:
            lines.append("  - {0} [{1}] {2}".format(item.path, item.code, item.error))
    return "\n".join(lines)


# ------------------------------------------------------------------ 两轮对账
def diff_summary(diff):
    """对账概要：``[(标签, 值)]``。"""
    summary = diff.summary
    return [
        ("新增违规", "{0} 件".format(summary["added"])),
        ("已修复", "{0} 件".format(summary["fixed"])),
        ("持续违规", "{0} 件（其中违规项变化 {1} 件）".format(
            summary["persistent"], summary["persistent_changed"])),
        ("稳定（两轮均无违规）", "{0} 件".format(summary["stable"])),
        ("新增件（无违规）", "{0} 件".format(summary["new_items"])),
        ("本轮消失", "{0} 件".format(summary["removed"])),
        ("内容变动", "{0} 件".format(summary["content_changed"])),
        ("上轮规则库坐标", diff.previous_coordinate),
        ("本轮规则库坐标", diff.current_coordinate),
    ]


DIFF_COLUMNS = ("对账状态", "件标识", "路径", "上轮等级", "本轮等级", "违规项变化", "内容变动")

#: 对账集合 → 展示名（顺序固定 = 报告与表格顺序）
DIFF_SECTIONS = (
    ("added", "新增违规"),
    ("fixed", "已修复"),
    ("persistent", "持续违规"),
    ("stable", "稳定"),
    ("new_items", "新增件"),
    ("removed", "本轮消失"),
    ("content_changed", "内容变动"),
)


def diff_rows(diff, sections=None):
    """对账逐条行：``(对账状态, 件标识, 路径, 上轮等级, 本轮等级, 违规项变化, 内容变动)``。"""
    rows = []
    names = dict(DIFF_SECTIONS)
    for key, _title in DIFF_SECTIONS:
        if sections is not None and key not in sections:
            continue
        for entry in getattr(diff, key):
            rows.append((
                names.get(entry.status, entry.status),
                entry.card_id or entry.identity,
                entry.path,
                entry.previous_grade or "-",
                entry.current_grade or "-",
                "、".join(entry.changed_targets) or "-",
                "是" if entry.content_changed else "否",
            ))
    return rows


# ------------------------------------------------------------------ 基准指标
BENCH_COLUMNS = ("基准", "指标", "实测", "要求", "是否达标")


def bench_rows(report):
    """基准指标行：``(基准, 指标, 实测, 要求, 是否达标)``。"""
    rows = []
    for suite in report.suites:
        for metric in suite.metrics:
            rows.append((
                suite.name, metric.name, metric.display, metric.requirement,
                "达标" if metric.passed else "未达标",
            ))
    return rows


def bench_text(report):
    """基准结果整段文本（含说明与失败明细）。"""
    lines = ["内置基准：{0}".format("全部达标" if report.passed else "存在未达标")]
    lines.append("  数据目录：{0}".format(report.data_dir))
    lines.append("  规则库坐标：{0}".format(report.coordinate))
    for suite in report.suites:
        lines.append("  [{0}] {1}：{2}（用例 {3}/{4}）".format(
            "达标" if suite.passed else "未达标", suite.name, suite.title,
            suite.cases_passed, suite.cases_total))
        for metric in suite.metrics:
            lines.append("      {0}：{1}（要求 {2}）{3}".format(
                metric.name, metric.display, metric.requirement,
                "" if metric.passed else " ← 未达标"))
            if metric.detail:
                lines.append("          {0}".format(metric.detail))
        for note in suite.notes:
            lines.append("      说明：{0}".format(note))
    if report.failures:
        lines.append("失败明细：")
        for line in report.failures:
            lines.append("  - {0}".format(line))
    return "\n".join(lines)


# ------------------------------------------------------------------ 规则库与依据
DOCUMENT_COLUMNS = ("文档", "版本", "文号/标准号", "施行日", "状态", "sha256")


def document_rows(ruleset):
    """依据清单行（取自规则库坐标，单一来源）。"""
    rows = []
    for doc in ruleset.doc_versions:
        rows.append((
            doc.get("title", "") or doc.get("doc_id", ""),
            doc.get("version", ""),
            doc.get("doc_number", ""),
            doc.get("effective_from", ""),
            doc.get("status", ""),
            doc.get("sha256", ""),
        ))
    return rows


RULE_COLUMNS = ("规则 id", "作用域", "判定类型", "目标", "载体", "严重度", "场景门控", "条款", "状态")


def rule_rows(ruleset):
    """规则条目行（生效在前，其后待核对）。"""
    rows = []
    for rule in list(ruleset.effective) + list(ruleset.pending):
        rows.append((
            rule.rule_id,
            rule.scope,
            rule.check_type,
            rule.target,
            "、".join(rule.carrier) or "全部",
            severity_label(rule.severity),
            "、".join(rule.scenarios) or "全部",
            _clause_text(rule.clause),
            "生效" if rule.is_effective else "待核对",
        ))
    return rows


MAPPING_COLUMNS = ("国标字段", "别名（容器键）", "状态", "条款")


def mapping_rows(table):
    """映射字段行（容器键 → 国标字段）。"""
    rows = []
    for field in table.fields:
        rows.append((
            field.national_field,
            "、".join(field.aliases) or "-",
            "已核对" if field.status == "verified" else "待核对",
            _clause_text(field.clause),
        ))
    return rows


def rules_text(overview):
    """规则库与依据的整段文本。"""
    ruleset = overview.ruleset
    lines = ["数据目录：{0}".format(overview.data_dir)]
    lines.append("规则库坐标：{0}".format(ruleset.coordinate))
    lines.append("生效规则 {0} 条 / 待核对 {1} 条".format(
        ruleset.verified_rule_count, ruleset.pending_rule_count))
    lines.append("映射字段 {0} 个（已核对 {1} / 待核对 {2}）".format(
        len(overview.mapping_table),
        overview.mapping_table.verified_field_count,
        overview.mapping_table.pending_field_count))
    if ruleset.warnings:
        lines.append("加载期提示：")
        for warning in ruleset.warnings:
            lines.append("  - {0}".format(warning))
    lines.append("依据清单：")
    for doc in ruleset.doc_versions:
        lines.append("  - {0} {1}（{2}，{3} 施行，{4}）".format(
            doc.get("title", "") or doc.get("doc_id", ""),
            doc.get("version", ""), doc.get("doc_number", "") or "—",
            doc.get("effective_from", "") or "—", doc.get("status", "")))
    return "\n".join(lines)


__all__ = [
    "GRADE_LABELS", "STATUS_LABELS", "SEVERITY_LABELS",
    "grade_label", "status_label", "severity_label",
    "report_summary", "finding_rows", "FINDING_COLUMNS", "report_text",
    "scan_summary", "scan_item_rows", "SCAN_ITEM_COLUMNS", "scan_text",
    "diff_summary", "diff_rows", "DIFF_COLUMNS", "DIFF_SECTIONS",
    "bench_rows", "BENCH_COLUMNS", "bench_text",
    "document_rows", "DOCUMENT_COLUMNS", "rule_rows", "RULE_COLUMNS",
    "mapping_rows", "MAPPING_COLUMNS", "rules_text",
]
