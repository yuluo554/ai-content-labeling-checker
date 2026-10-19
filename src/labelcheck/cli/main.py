"""CLI 入口（argparse，零第三方依赖）。

**纪律**：本模块**顶层不得 import GUI/PySide6**——由 ``tests/test_cli_ast_gate.py``
的 AST 静态断言锁死（CI 的 ``.[dev]`` 通路无 GUI 依赖也必须能跑 CLI 与全量测试）。
"""

import argparse
import sys

from ..model import SCENARIOS


def _ensure_utf8_stdio():
    """把 stdout/stderr 切到 UTF-8（仅当当前编码不是 UTF-8 家族时）。

    本机开发一律 ``py -X utf8`` 会**掩盖**非 ASCII 输出缺口，CI 管道是 cp1252 时
    同样代码就地崩 ``UnicodeEncodeError``。中文控制台（cp936）保持不动——它本就能
    显示中文；只改"会在非 ASCII 上崩"的编码。
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding in ("utf8", "utf8mb4", "cp65001"):
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def _build_parser():
    from .. import __version__

    parser = argparse.ArgumentParser(
        prog="labelcheck",
        description=(
            "AI 生成合成内容标识合规核查器：以《标识办法》+ 强制国标 GB 45438-2025 为规则源，"
            "做显式/隐式标识核验、批量扫描与合规证据链（全本地、零上传）。"
        ),
        epilog="退出码：0=完成无违规  1=检出不合规  2=用法/输入错误  3=环境/依赖错误",
    )
    parser.add_argument("--version", action="version", version="labelcheck {0}".format(__version__))
    parser.add_argument(
        "--data-dir", default=None, metavar="PATH",
        help="数据目录（规则库/映射表所在）；默认自动定位（环境变量 %s 次之）" % "LABELCHECK_DATA_DIR",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="输出更多细节到 stderr")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_check = sub.add_parser("check", help="单件核验（标识卡 JSON 或可解析容器文件）")
    p_check.add_argument("card", metavar="CARD.json|FILE", help="标识卡 JSON 或 PNG/JPEG/MP4/M4A 容器文件")
    p_check.add_argument("--json", action="store_true", help="以 JSON 输出报告（供程序消费）")
    p_check.add_argument(
        "--generated-at", default="", metavar="TS",
        help="报告时间戳（默认空字符串，保证相同输入两次导出逐字节一致）",
    )
    p_check.add_argument(
        "--scenario", default=None, choices=SCENARIOS, metavar="SCENE",
        help="适用场景（authored/exported/propagated）；缺省用卡内声明或 authored",
    )
    p_check.add_argument("-v", "--verbose", action="store_true", help="逐条输出判定明细")

    p_parse = sub.add_parser("parse", help="解析可解析容器文件的元数据标识（M2）")
    p_parse.add_argument("file", metavar="FILE", help="PNG/JPEG/MP4/M4A 容器文件")
    p_parse.add_argument("--json", action="store_true", help="以 JSON 输出标识卡（供上游消费）")
    p_parse.add_argument(
        "--scenario", default=None, choices=SCENARIOS, metavar="SCENE",
        help="适用场景（authored/exported/propagated）；缺省 authored",
    )
    p_parse.add_argument(
        "--out", default=None, metavar="PATH",
        help="把解析出的标识卡写到指定文件（JSON、LF）",
    )

    p_selfcheck = sub.add_parser("selfcheck", help="自检：数据定位 + 规则库加载 + 门控计数")
    p_selfcheck.add_argument("--json", action="store_true", help="以 JSON 输出自检结果")

    p_rules = sub.add_parser("rules", help="规则库只读查询：条目 / 字段映射 / 依据坐标（v0.2.0）")
    p_rules.add_argument(
        "--scope", default=None, choices=("explicit", "implicit"), metavar="SCOPE",
        help="只列指定作用域的条目（explicit/implicit）；缺省全部")
    p_rules.add_argument(
        "--status", default=None, choices=("verified", "pending"), metavar="STATUS",
        help="只列指定核对状态的条目；缺省全部（含 pending，便于看清待核对范围）")
    p_rules.add_argument(
        "--mapping", action="store_true",
        help="同时输出字段映射表（容器键 → 国标字段，含 status）")
    p_rules.add_argument("--json", action="store_true", help="以 JSON 输出（供程序消费）")

    sub.add_parser("version", help="打印版本与规则库坐标")

    p_scan = sub.add_parser("scan", help="批量扫描：目录/清单 → 逐件核验 + 报告导出（M3）")
    p_scan.add_argument(
        "target", metavar="DIR|MANIFEST",
        help="待扫描目录（递归 *.json 与 PNG/JPEG/MP4/M4A），或清单文件（每行一个路径）")
    p_scan.add_argument(
        "--out", default=None, metavar="DIR",
        help="报告导出目录（写 report.md / summary.csv / detail.csv / evidence.json[ / report.xlsx]）",
    )
    p_scan.add_argument(
        "--json", action="store_true",
        help="以 JSON 输出 ScanResult（供程序消费）；与 --out 可同用",
    )
    p_scan.add_argument(
        "--baseline", default=None, metavar="JSON",
        help="上轮 ScanResult JSON（由 scan --json 产出）→ 两轮对账（新增违规/已修复/持续违规）",
    )
    p_scan.add_argument(
        "--generated-at", default="", metavar="TS",
        help="报告/对账时间戳（默认空字符串，保证相同输入两次导出逐字节一致）",
    )
    p_scan.add_argument(
        "--scenario", default=None, choices=SCENARIOS, metavar="SCENE",
        help="适用场景覆盖（authored/exported/propagated）；缺省用各卡内声明",
    )
    p_scan.add_argument(
        "--progress-every", type=int, default=0, metavar="N",
        help="每 N 件向 stderr 打一行进度（0 = 关闭）",
    )
    p_scan.add_argument("--quiet", action="store_true", help="关闭进度输出")
    p_scan.add_argument("-v", "--verbose", action="store_true", help="逐件输出判定明细到 stderr")
    p_scan.add_argument(
        "--sarif", default=None, metavar="FILE",
        help="另存 SARIF 2.1.0 结果文件（只读导出，不进默认报告包 / 不影响证据链指纹）")
    p_scan.add_argument(
        "--html", default=None, metavar="FILE",
        help="另存单文件 HTML 报告（内联 CSS、零 JS、零外链；只读导出）")

    p_bench = sub.add_parser("bench", help="运行内置评测基准（三类：字段规则/构造真值/两轮对账）")
    p_bench.add_argument(
        "--only", default=None, metavar="NAMES",
        help="只跑指定基准（逗号分隔：fields,constructed,diff）；缺省全跑")
    p_bench.add_argument("--json", action="store_true", help="以 JSON 输出基准结果（供程序消费）")
    p_bench.add_argument("-v", "--verbose", action="store_true", help="逐用例输出明细")

    p_gui = sub.add_parser("gui", help="启动桌面界面（PySide6，需安装 gui extra）")
    p_gui.add_argument(
        "--check", action="store_true",
        help="只做 GUI 可加载性自检后退出（无显示环境/CI 冒烟用；不进入事件循环）")

    return parser


# ---------------------------------------------------------------- 子命令实现
def cmd_check(args):
    from ..engine import check_file
    from ..errors import EXIT_FINDINGS, EXIT_OK
    from ..jsonio import canonical_json

    data_dir = _resolve_data_dir(args)
    report, parse_outcome = check_file(
        args.card, data_dir, generated_at=args.generated_at, scenario=args.scenario)

    if args.json:
        payload = report.to_dict()
        if parse_outcome is not None:
            payload["parse"] = _parse_payload(parse_outcome)
        sys.stdout.write(canonical_json(payload, indent=2) + "\n")
    else:
        if parse_outcome is not None:
            _print_parse_summary(parse_outcome)
        _print_report_human(report, verbose=args.verbose)

    _emit_not_assessed_hint(report)
    _emit_unobserved_hint(report)
    return EXIT_FINDINGS if report.has_violation else EXIT_OK


def _parse_payload(outcome):
    return {
        "container": outcome.container,
        "implicit_observed": outcome.implicit_observed,
        "explicit_observed": outcome.explicit_observed,
        "aigc_field_count": outcome.aigc_field_count,
        "payload_count": outcome.payload_count,
        "reasons": list(outcome.reasons),
    }


def _print_parse_summary(outcome):
    sys.stderr.write(
        "解析通路：容器={0} 隐式作用域已观测={1} 显式作用域已观测={2} AIGC 字段={3} 载荷块={4}\n".format(
            outcome.container or "(未识别)", outcome.implicit_observed,
            outcome.explicit_observed, outcome.aigc_field_count, outcome.payload_count))
    for reason in outcome.reasons:
        sys.stderr.write("  解析提示：{0}\n".format(reason))


def _emit_not_assessed_hint(report):
    from ..model import GRADE_NOT_ASSESSED

    if report.grade == GRADE_NOT_ASSESSED:
        sys.stderr.write(
            "提示：本次未进行评估（生效规则为 0）。规则条目仍在逐条核对中，"
            "核对完成后重新运行可得到实际判定。\n"
        )


def _emit_unobserved_hint(report):
    """解析通路的显式作用域未观测：如实提示"显式标识未被检查"，不给假结论。"""
    scopes = report.unobserved_scopes
    if not scopes:
        return
    labels = {"explicit": "显式标识", "implicit": "隐式标识"}
    names = "、".join(labels.get(scope, scope) for scope in scopes)
    sys.stderr.write(
        "提示：{0}作用域未被观测（解析通路无法读取），相关判定为 unknown（待人工确认），"
        "不代表合规或违规。\n".format(names))


def cmd_parse(args):
    from pathlib import Path

    from ..engine import with_scenario
    from ..errors import EXIT_OK, UsageError
    from ..jsonio import canonical_json, write_json
    from ..mapping import load_mapping_table
    from ..parse import parse_bytes
    from ..parse.containers import detect_container

    data_dir = _resolve_data_dir(args)
    path = Path(args.file)
    if not path.is_file():
        raise UsageError("文件不存在：{0}".format(path))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UsageError("无法读取文件：{0}（{1}）".format(path, exc))

    # parse 的输入**必须是可识别容器**：不是容器属用法/输入错误（exit 2）。
    # 与 check 的口径一致（"既非标识卡 JSON 也非容器" → exit 2），不静默给空卡。
    container = detect_container(raw)
    if container is None:
        raise UsageError(
            "不是可解析容器（支持 PNG/JPEG/MP4/M4A）：{0}".format(path))

    table = load_mapping_table(data_dir)
    outcome = parse_bytes(raw, container, table.payload_wrapper)
    card = outcome.card
    if args.scenario:
        card = with_scenario(card, args.scenario)

    payload = card.to_dict()
    if args.out:
        write_json(args.out, payload)
        sys.stderr.write("已写出标识卡：{0}\n".format(args.out))
    elif args.json:
        sys.stdout.write(canonical_json(payload, indent=2) + "\n")
    else:
        sys.stdout.write("解析结果：{0}\n".format(card.card_id))
        sys.stdout.write("  容器        : {0}\n".format(outcome.container or "(未识别)"))
        sys.stdout.write("  载体        : {0}\n".format(card.carrier))
        sys.stdout.write("  内容指纹    : {0}\n".format(card.content_sha256))
        sys.stdout.write("  隐式已观测  : {0}\n".format(outcome.implicit_observed))
        sys.stdout.write("  显式已观测  : {0}（解析通路不含显式标识）\n".format(outcome.explicit_observed))
        sys.stdout.write("  AIGC 字段数 : {0}（载荷块 {1}）\n".format(
            outcome.aigc_field_count, outcome.payload_count))
        if outcome.reasons:
            sys.stdout.write("  解析提示    : {0}\n".format("、".join(outcome.reasons)))
    return EXIT_OK


def cmd_scan(args):
    """批量扫描：目录/清单 → 逐件核验 → （可选）报告导出 + 两轮对账（M3）。"""
    from ..errors import EXIT_FINDINGS, EXIT_OK
    from ..jsonio import canonical_json
    from ..report import write_report
    from ..scan import diff_scans, scan_target

    data_dir = _resolve_data_dir(args)

    result = scan_target(
        args.target, data_dir,
        generated_at=args.generated_at,
        scenario=args.scenario,
        progress_every=args.progress_every,
        quiet=args.quiet,
    )

    diff = None
    if args.baseline:
        previous = _load_baseline(args.baseline)
        diff = diff_scans(previous, result, generated_at=args.generated_at)

    bundle = None
    if args.out:
        if diff is None:
            bundle, written = write_report(
                result, args.out, generated_at=args.generated_at)
        else:
            bundle, written = write_report(
                result, args.out, generated_at=args.generated_at, diff=diff)
        sys.stderr.write("报告已导出：{0}\n".format(args.out))
        for path in written:
            sys.stderr.write("  - {0}\n".format(path))
        if bundle.xlsx_hint:
            sys.stderr.write("提示：{0}\n".format(bundle.xlsx_hint))

    # 可选导出（v0.2.0）：写**调用方指定路径**，不进默认报告包（证据链指纹不变）。
    if args.sarif:
        from .. import __version__
        from ..report import write_sarif

        write_sarif(result, args.sarif, generated_at=args.generated_at,
                    tool_version=__version__)
        sys.stderr.write("SARIF 已导出：{0}\n".format(args.sarif))
    if args.html:
        from ..report import write_html

        write_html(result, args.html, diff=diff, generated_at=args.generated_at)
        sys.stderr.write("HTML 报告已导出：{0}\n".format(args.html))

    if args.json:
        payload = result.to_dict()
        if diff is not None:
            payload["diff"] = diff.to_dict()
        sys.stdout.write(canonical_json(payload, indent=2) + "\n")
    else:
        _print_scan_human(result, diff=diff, verbose=args.verbose)

    return EXIT_FINDINGS if result.violations else EXIT_OK


def _load_baseline(path):
    """读上轮 ``ScanResult`` JSON（``scan --json`` 的产物）。"""
    from ..errors import UsageError
    from ..jsonio import load_json
    from ..scan import ScanResult

    payload = load_json(path, error_cls=UsageError)
    if not isinstance(payload, dict) or "items" not in payload:
        raise UsageError(
            "上轮结果不是合法 ScanResult JSON（缺 items）：{0}".format(path))
    return ScanResult.from_dict(payload)


def _print_scan_human(result, diff=None, verbose=False):
    summary = result.summary
    sys.stdout.write("批量扫描完成\n")
    sys.stdout.write("  扫描根      : {0}\n".format(result.root or "(单文件)"))
    sys.stdout.write("  规则库坐标  : {0}\n".format(result.ruleset_coordinate))
    sys.stdout.write("  生效/待核对 : {0}/{1}\n".format(
        result.verified_rule_count, result.pending_rule_count))
    sys.stdout.write("  件数        : {0}（已核验 {1}，失败 {2}）\n".format(
        summary["total"], summary["checked"], summary["failed"]))
    sys.stdout.write("  检出违规    : {0} 件；待人工确认 {1} 件\n".format(
        summary["violations"], summary["reviews"]))
    sys.stdout.write("  载体分布    : {0}\n".format(
        "、".join("{0}={1}".format(k, v) for k, v in sorted(summary["carriers"].items()))))
    sys.stdout.write("  等级分布    : {0}\n".format(
        "、".join("{0}={1}".format(k, v) for k, v in sorted(summary["grades"].items()))))

    if verbose:
        for item in result.items:
            if item.failed:
                sys.stdout.write("    - [failed] {0} {1}: {2}\n".format(
                    item.path, item.code, item.error))
            else:
                sys.stdout.write("    - [{0}] {1} ({2}) 违规 {3} / 待确认 {4}\n".format(
                    item.grade, item.card_id, item.path,
                    "、".join(item.fail_targets) or "-",
                    "、".join(item.review_targets) or "-"))

    if diff is not None:
        dsummary = diff.summary
        sys.stdout.write("  两轮对账    : 新增违规 {0}；已修复 {1}；持续违规 {2}"
                         "（违规项变化 {3}）；内容变动 {4}\n".format(
                             dsummary["added"], dsummary["fixed"], dsummary["persistent"],
                             dsummary["persistent_changed"], dsummary["content_changed"]))
        for entry in diff.added:
            sys.stdout.write("    + 新增违规 {0}（{1}）：{2}\n".format(
                entry.card_id or entry.identity, entry.path,
                "、".join(entry.current_fail_targets) or "-"))
        for entry in diff.fixed:
            sys.stdout.write("    - 已修复   {0}（{1}）\n".format(
                entry.card_id or entry.identity, entry.path))

    if result.failed:
        sys.stderr.write("提示：{0} 件扫描失败（已隔离，未中断整批）；详见报告失败件清单。\n".format(
            len(result.failed)))


def cmd_selfcheck(args):
    from ..errors import EXIT_ENV, EXIT_OK
    from ..jsonio import canonical_json
    from ..mapping import load_mapping_table
    from ..paths import find_data_dir, is_frozen
    from ..rules import effective_ruleset

    try:
        data_dir = find_data_dir(args.data_dir)
        ruleset = effective_ruleset(data_dir)
        table = load_mapping_table(data_dir)
    except Exception as exc:  # noqa: BLE001 - 自检要把任何环境问题转成 exit 3
        sys.stderr.write("自检失败：{0}\n".format(exc))
        return EXIT_ENV

    payload = {
        "data_dir": str(data_dir),
        "frozen": is_frozen(),
        "ruleset_coordinate": ruleset.coordinate,
        "verified_rule_count": ruleset.verified_rule_count,
        "pending_rule_count": ruleset.pending_rule_count,
        "documents": ruleset.doc_versions,
        "mapping_field_count": len(table),
        "mapping_verified_field_count": table.verified_field_count,
        "mapping_pending_field_count": table.pending_field_count,
        "warnings": list(ruleset.warnings),
    }

    if args.json:
        sys.stdout.write(canonical_json(payload, indent=2) + "\n")
    else:
        sys.stdout.write("自检通过\n")
        sys.stdout.write("  数据目录      : {0}\n".format(payload["data_dir"]))
        sys.stdout.write("  冻结态        : {0}\n".format(payload["frozen"]))
        sys.stdout.write("  规则库坐标    : {0}\n".format(payload["ruleset_coordinate"]))
        sys.stdout.write("  生效规则 / 待核对 : {0} / {1}\n".format(
            payload["verified_rule_count"], payload["pending_rule_count"]))
        sys.stdout.write("  映射字段 / 待核对 : {0} / {1}\n".format(
            payload["mapping_verified_field_count"], payload["mapping_pending_field_count"]))
        for warning in payload["warnings"]:
            sys.stdout.write("  提示: {0}\n".format(warning))
        if payload["verified_rule_count"] == 0:
            sys.stdout.write(
                "  注：当前生效规则为 0（规则条目仍在逐条核对中，status=pending）。\n"
                "      未挂原文核对的条目不得进入判定路径。\n"
            )
        elif payload["pending_rule_count"]:
            sys.stdout.write(
                "  注：还有 {0} 条待核对（status=pending）条目未进入判定路径。\n".format(
                    payload["pending_rule_count"])
            )
    return EXIT_OK


def cmd_rules(args):
    """规则库**只读**查询（v0.2.0）：条目 / 字段映射 / 依据坐标。

    **纯查询语义**：不判定、不写盘、不改规则库；退出码恒为 ``0``（读不到规则库
    属环境错误，由 ``effective_ruleset`` 抛 ``RulesetError`` → exit 3）。
    缺省**同时列出 pending**——"哪条还没核对"本身是用户要的信息，隐藏它会让人
    误以为规则库只有生效条目。
    """
    from ..errors import EXIT_OK
    from ..jsonio import canonical_json
    from ..mapping import load_mapping_table
    from ..rules import effective_ruleset

    data_dir = _resolve_data_dir(args)
    ruleset = effective_ruleset(data_dir)

    def matches(rule, effective):
        if args.scope and rule.scope != args.scope:
            return False
        if args.status == "verified" and not effective:
            return False
        if args.status == "pending" and effective:
            return False
        return True

    rows = []
    for effective, group in ((True, ruleset.effective), (False, ruleset.pending)):
        for rule in group:
            if not matches(rule, effective):
                continue
            rows.append({
                "rule_id": rule.rule_id,
                "doc_id": rule.doc_id,
                "version": rule.version,
                "scope": rule.scope,
                "target": rule.target,
                "check_type": rule.check_type,
                "severity": rule.severity,
                "carrier": list(rule.carrier),
                "scenarios": rule.scenarios,
                "status": rule.status,
                "effective": effective,
                "clause": rule.clause.get("article", ""),
                "source_url": rule.source_url,
                "verified_at": rule.verified_at,
            })

    table = load_mapping_table(data_dir) if args.mapping else None
    payload = {
        "data_dir": str(data_dir),
        "ruleset_coordinate": ruleset.coordinate,
        "verified_rule_count": ruleset.verified_rule_count,
        "pending_rule_count": ruleset.pending_rule_count,
        "documents": ruleset.doc_versions,
        "filters": {"scope": args.scope, "status": args.status},
        "rules": rows,
        "warnings": list(ruleset.warnings),
    }
    if table is not None:
        payload["mapping"] = {
            "verified_field_count": table.verified_field_count,
            "pending_field_count": table.pending_field_count,
            "fields": [
                {
                    "national_field": field.national_field,
                    "label": field.label,
                    "aliases": list(field.aliases),
                    "status": field.status,
                    "clause": field.clause.get("article", ""),
                    "source_url": field.source_url,
                }
                for field in table.fields
            ],
        }

    if args.json:
        sys.stdout.write(canonical_json(payload, indent=2) + "\n")
        return EXIT_OK

    sys.stdout.write("规则库坐标: {0}\n".format(payload["ruleset_coordinate"]))
    sys.stdout.write("生效规则 / 待核对: {0} / {1}\n".format(
        payload["verified_rule_count"], payload["pending_rule_count"]))
    for doc in payload["documents"]:
        sys.stdout.write("  依据: {0}（{1}，{2}）version={3} status={4}\n".format(
            doc.get("title") or doc.get("doc_id", ""),
            doc.get("doc_number", ""), doc.get("issuer", ""),
            doc.get("version", ""), doc.get("status", "")))
    sys.stdout.write("条目（{0} 条）：\n".format(len(rows)))
    sys.stdout.write("  {0:<52} {1:<9} {2:<9} {3:<10} {4:<9} {5}\n".format(
        "rule_id", "scope", "status", "check_type", "severity", "clause"))
    for row in rows:
        sys.stdout.write("  {0:<52} {1:<9} {2:<9} {3:<10} {4:<9} {5}\n".format(
            row["rule_id"], row["scope"], row["status"], row["check_type"],
            row["severity"], row["clause"]))
    if table is not None:
        sys.stdout.write("字段映射（生效 {0} / 待核对 {1}）：\n".format(
            table.verified_field_count, table.pending_field_count))
        for field in payload["mapping"]["fields"]:
            sys.stdout.write("  {0:<24} {1:<10} aliases={2}\n".format(
                field["national_field"], field["status"], ", ".join(field["aliases"])))
    return EXIT_OK


def cmd_version(args):
    from .. import __version__
    from ..paths import find_data_dir
    from ..rules import effective_ruleset

    sys.stdout.write("labelcheck {0}\n".format(__version__))
    try:
        data_dir = find_data_dir(args.data_dir, require=False)
    except Exception:  # noqa: BLE001
        data_dir = None
    if data_dir is None:
        sys.stdout.write("规则库坐标: (未定位到数据目录)\n")
        return 0
    try:
        ruleset = effective_ruleset(data_dir)
        sys.stdout.write("规则库坐标: {0}\n".format(ruleset.coordinate))
        sys.stdout.write("生效规则/待核对: {0}/{1}\n".format(
            ruleset.verified_rule_count, ruleset.pending_rule_count))
    except Exception as exc:  # noqa: BLE001
        sys.stdout.write("规则库坐标: (加载失败：{0})\n".format(exc))
    return 0


def cmd_bench(args):
    """运行内置评测基准（FR-11）：三类 runner 一条命令跑全。

    退出码：``0`` 全部达标 / ``1`` 有基准未达标 / ``2`` 用法错误（未知基准名）。
    **零 API 依赖**：纯规则通路，指标可重复（结论进 README 表格）。
    """
    from ..benchmark import parse_only, run_benchmark
    from ..errors import EXIT_FINDINGS, EXIT_OK, UsageError
    from ..jsonio import canonical_json

    data_dir = _resolve_data_dir(args)
    try:
        only = parse_only(args.only)
        report = run_benchmark(data_dir, only=only)
    except ValueError as exc:
        raise UsageError(str(exc))

    if args.json:
        sys.stdout.write(canonical_json(report.to_dict(), indent=2) + "\n")
    else:
        _print_bench_human(report, verbose=args.verbose)

    if not report.passed:
        sys.stderr.write(
            "提示：{0} 类基准未达标（见上方失败明细）；达标口径见 plan/04 §九。\n".format(
                sum(1 for suite in report.suites if not suite.passed)))
    return EXIT_OK if report.passed else EXIT_FINDINGS


def _print_bench_human(report, verbose=False):
    sys.stdout.write("内置基准：{0}\n".format("全部达标" if report.passed else "存在未达标"))
    sys.stdout.write("  数据目录    : {0}\n".format(report.data_dir))
    sys.stdout.write("  规则库坐标  : {0}\n".format(report.coordinate))
    for suite in report.suites:
        sys.stdout.write("  [{0}] {1}（{2}；用例 {3}/{4}）\n".format(
            "达标" if suite.passed else "未达标", suite.name, suite.title,
            suite.cases_passed, suite.cases_total))
        for metric in suite.metrics:
            sys.stdout.write("      {0}: {1}（要求 {2}）{3}\n".format(
                metric.name, metric.display, metric.requirement,
                "" if metric.passed else " ← 未达标"))
            if metric.detail:
                sys.stdout.write("          {0}\n".format(metric.detail))
        for note in suite.notes:
            sys.stdout.write("      说明：{0}\n".format(note))
        if verbose:
            for line in suite.failures:
                sys.stdout.write("      - 失败：{0}\n".format(line))
    if not verbose and report.failures:
        sys.stdout.write("  失败明细（-v 展开）：{0} 项\n".format(len(report.failures)))
    sys.stdout.write(
        "  口径：对账按 expected 声明的非 pass 集合（fail ∪ unknown）比对；"
        "未观测的 scope 不参与比较。\n")


def cmd_gui(args):
    """启动桌面界面（M5，PySide6 可选依赖）。

    **惰性导入纪律**：本模块顶层不得 import GUI（AST 守门测试断言），故 PySide6 与
    ``labelcheck.gui`` 都在**函数体内**导入。缺 GUI extra 时给安装提示并 exit 3
    （环境/依赖错误），不抛裸 ImportError。

    ``--check`` 只做"可加载性自检"（构造 QApplication + 主窗口后立即退出，不进入
    事件循环）——供无显示环境的 CI 冒烟（配合 ``QT_QPA_PLATFORM=offscreen``）。
    """
    from ..errors import EXIT_ENV, EXIT_OK
    from ..paths import find_data_dir, is_frozen

    # 数据目录：优先显式参数，否则自动定位（定位失败不阻断启动——界面允许稍后再选）
    data_dir = find_data_dir(args.data_dir, require=False)

    # 惰性导入**包住整条用到 Qt 的路径**：`from ..gui import main_window` 本身不拖 Qt
    # （main_window 用函数体内 `_qt()` 取符号），真正的 ImportError 在 build_app/main
    # 里才抛——只包导入会漏掉，缺 extra 时抛裸异常而非 exit 3（CI 实测抓出）。
    try:
        from ..gui import main_window
        if args.check:
            app, window = main_window.build_app(argv=[], data_dir=data_dir)
            sys.stdout.write(
                "GUI 自检通过：PySide6 可用，主窗口与 {0} 个页签已装配"
                "（数据目录：{1}）。\n".format(
                    len(window.tab_objects), data_dir or "(未定位)"))
            return EXIT_OK
        return main_window.main(argv=sys.argv, data_dir=data_dir)
    except ImportError as exc:  # 缺 PySide6 → 环境/依赖错误（exit 3），给安装提示
        if is_frozen():
            sys.stderr.write(
                "本控制台版可执行文件不含桌面界面（为保持 CLI 体积与零 GUI 依赖，"
                "PySide6 未内嵌）。请改用发行包中的 labelcheck-gui.exe。\n")
        else:
            sys.stderr.write(
                "无法加载桌面界面：{0}\n"
                "请安装 GUI 依赖：pip install -e \".[gui]\"\n".format(exc))
        return EXIT_ENV


def cmd_not_implemented(args, milestone):
    """未实现子命令的显式桩：打印说明并以用法错误码退出（不静默假装成功）。

    M4 起全部**判定类**子命令均已实现（``bench`` 转实现后本桩无调用点）；M5 又加了
    ``gui``。保留本桩以便后续新增子命令时仍有"显式未实现"的呈现方式，而不是静默成功。
    """
    from ..errors import EXIT_USAGE

    sys.stderr.write(
        "子命令 {0!r} 尚未实现（计划于 {1} 交付）。\n"
        "当前可用：check / parse / scan / bench / gui / rules / selfcheck / version。\n".format(
            args.command, milestone)
    )
    return EXIT_USAGE


# ---------------------------------------------------------------- 辅助
def _resolve_data_dir(args):
    from ..paths import find_data_dir
    return find_data_dir(args.data_dir)


def _print_report_human(report, verbose=False):
    from ..model import GRADE_NOT_ASSESSED

    sys.stdout.write("核查结论：{0}\n".format(report.card_id))
    sys.stdout.write("  载体        : {0}\n".format(report.carrier))
    sys.stdout.write("  场景        : {0}\n".format(report.scenario))
    sys.stdout.write("  来源        : {0}\n".format(report.source))
    sys.stdout.write("  内容指纹    : {0}\n".format(report.content_sha256))
    sys.stdout.write("  规则库坐标  : {0}\n".format(report.ruleset_coordinate))
    sys.stdout.write("  生效/待核对 : {0}/{1}\n".format(
        report.verified_rule_count, report.pending_rule_count))
    sys.stdout.write("  合规等级    : {0}\n".format(report.grade))

    unobserved = report.unobserved_scopes
    if unobserved:
        sys.stdout.write("  未观测作用域: {0}\n".format("、".join(unobserved)))

    if report.missing:
        sys.stdout.write("  缺失项      : {0}\n".format("、".join(report.missing)))
    if report.errors:
        sys.stdout.write("  错误码      : {0}\n".format("、".join(report.errors)))

    if verbose:
        for finding in report.all_findings:
            sys.stdout.write("    - [{0}] {1}:{2} {3}{4}\n".format(
                finding.status, finding.scope, finding.target,
                finding.code,
                (" — " + finding.message) if finding.message else "",
            ))

    if report.grade == GRADE_NOT_ASSESSED:
        sys.stdout.write(
            "  提示        : 未进行评估——当前没有已核对生效的规则（生效 {0} / 待核对 {1}）。\n"
            "                规则条目须逐条挂原文核对后方可进入判定路径（status=verified）。\n".format(
                report.verified_rule_count, report.pending_rule_count)
        )
    elif not report.violations:
        sys.stdout.write("  提示        : 未发现明确不合规项（存在 {0} 项待人工确认）\n".format(
            len(report.reviews)))
    sys.stdout.write("{0}\n".format(report.disclaimer))


def main(argv=None):
    _ensure_utf8_stdio()
    from ..errors import LabelCheckError, EXIT_USAGE

    parser = _build_parser()
    # argv=None → 用 sys.argv；显式传入时便于测试
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EXIT_USAGE

    handlers = {
        "check": cmd_check,
        "parse": cmd_parse,
        "scan": cmd_scan,
        "bench": cmd_bench,
        "gui": cmd_gui,
        "rules": cmd_rules,
        "selfcheck": cmd_selfcheck,
        "version": cmd_version,
    }

    try:
        return handlers[args.command](args)
    except LabelCheckError as exc:
        sys.stderr.write("错误：{0}\n".format(exc))
        return exc.exit_code
    except KeyboardInterrupt:  # pragma: no cover - 交互中断
        sys.stderr.write("已中断\n")
        return EXIT_USAGE
    except BrokenPipeError:  # pragma: no cover - 管道关闭
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
