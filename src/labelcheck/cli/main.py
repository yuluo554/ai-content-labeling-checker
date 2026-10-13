"""CLI 入口（argparse，零第三方依赖）。

**纪律**：本模块**顶层不得 import GUI/PySide6**——由 ``tests/test_cli_ast_gate.py``
的 AST 静态断言锁死（CI 的 ``.[dev]`` 通路无 GUI 依赖也必须能跑 CLI 与全量测试）。
"""

import argparse
import sys


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

    p_check = sub.add_parser("check", help="单件标识卡核验")
    p_check.add_argument("card", metavar="CARD.json", help="标识卡 JSON 文件路径")
    p_check.add_argument("--json", action="store_true", help="以 JSON 输出报告（供程序消费）")
    p_check.add_argument(
        "--generated-at", default="", metavar="TS",
        help="报告时间戳（默认空字符串，保证相同输入两次导出逐字节一致）",
    )
    p_check.add_argument("-v", "--verbose", action="store_true", help="逐条输出判定明细")

    p_selfcheck = sub.add_parser("selfcheck", help="自检：数据定位 + 规则库加载 + 门控计数")
    p_selfcheck.add_argument("--json", action="store_true", help="以 JSON 输出自检结果")

    sub.add_parser("version", help="打印版本与规则库坐标")

    p_scan = sub.add_parser("scan", help="批量扫描（M3 实现）")
    p_scan.add_argument("target", nargs="?", help="待扫描目录")

    sub.add_parser("bench", help="运行内置基准（M4 实现）")

    return parser


# ---------------------------------------------------------------- 子命令实现
def cmd_check(args):
    from ..engine import check_card_dict
    from ..errors import EXIT_FINDINGS, EXIT_OK
    from ..jsonio import canonical_json, load_json
    from ..model import GRADE_NOT_ASSESSED

    data_dir = _resolve_data_dir(args)
    card_data = load_json(args.card)
    report = check_card_dict(card_data, data_dir, generated_at=args.generated_at)

    if args.json:
        sys.stdout.write(canonical_json(report.to_dict(), indent=2) + "\n")
    else:
        _print_report_human(report, verbose=args.verbose)

    if report.grade == GRADE_NOT_ASSESSED:
        # 未评估 ≠ 合规：不改变退出码（无违规即 0），但在 stderr 明确提示"没检查"。
        sys.stderr.write(
            "提示：本次未进行评估（生效规则为 0）。规则条目仍在逐条核对中，"
            "核对完成后重新运行可得到实际判定。\n"
        )

    return EXIT_FINDINGS if report.has_violation else EXIT_OK


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
                "      M0/M1 阶段的预期状态：未挂原文核对的条目不得进入判定路径。\n"
            )
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


def cmd_not_implemented(args, milestone):
    """未实现子命令的显式桩：打印说明并以用法错误码退出（不静默假装成功）。"""
    from ..errors import EXIT_USAGE

    sys.stderr.write(
        "子命令 {0!r} 尚未实现（计划于 {1} 交付）。\n"
        "当前可用：check / selfcheck / version。\n".format(args.command, milestone)
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
    sys.stdout.write("  内容指纹    : {0}\n".format(report.content_sha256))
    sys.stdout.write("  规则库坐标  : {0}\n".format(report.ruleset_coordinate))
    sys.stdout.write("  生效/待核对 : {0}/{1}\n".format(
        report.verified_rule_count, report.pending_rule_count))
    sys.stdout.write("  合规等级    : {0}\n".format(report.grade))

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
        "selfcheck": cmd_selfcheck,
        "version": cmd_version,
    }
    if args.command == "scan":
        return cmd_not_implemented(args, "M3")
    if args.command == "bench":
        return cmd_not_implemented(args, "M4")

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
