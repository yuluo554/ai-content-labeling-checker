"""CLI 测试：**退出码语义逐码锁死** + 主通路 + 失败路径（这是脚本化使用的契约）。"""

import json

import pytest

from labelcheck.cli.main import main
from labelcheck.errors import EXIT_ENV, EXIT_FINDINGS, EXIT_OK, EXIT_USAGE

from _support import build_data_dir, make_card, make_mapping_field, make_rule


@pytest.fixture
def card_file(tmp_path):
    def _write(**overrides):
        path = tmp_path / "card.json"
        path.write_text(json.dumps(make_card(**overrides), ensure_ascii=False), encoding="utf-8")
        return str(path)
    return _write


@pytest.fixture
def verified_data(tmp_path):
    """含 1 条生效隐式规则的完整数据目录。"""
    def _build(rules=None, mapping_fields=None):
        return build_data_dir(
            tmp_path / "data",
            {"doc": {"version": "2025-09-01", "status": "verified",
                     "rules": rules if rules is not None else []}},
            mapping_fields=mapping_fields,
        )
    return _build


# ------------------------------------------------------------------ 退出码 0
def test_check_exit_0_when_no_violation(card_file, verified_data, capsys):
    data = verified_data(
        rules=[make_rule("r", scope="implicit", target="content_property",
                         check_type="presence", status="verified")],
        mapping_fields=[make_mapping_field("content_property", ["content.property"], status="verified")],
    )
    code = main(["--data-dir", str(data), "check", card_file(implicit={"content.property": "AI_GENERATED"})])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "compliant" in captured.out


# ------------------------------------------------------------------ 退出码 1（检出不合规）
def test_check_exit_1_when_violation_found(card_file, verified_data, capsys):
    data = verified_data(
        rules=[make_rule("r", scope="implicit", target="content_property",
                         check_type="presence", severity="major", status="verified")],
        mapping_fields=[make_mapping_field("content_property", ["content.property"], status="verified")],
    )
    code = main(["--data-dir", str(data), "check", card_file(implicit={})])
    captured = capsys.readouterr()
    assert code == EXIT_FINDINGS, "检出不合规必须以 1 退出，便于 CI/脚本分流"
    assert "non_compliant" in captured.out


# ------------------------------------------------------------------ 退出码 2（用法/输入）
def test_exit_2_on_missing_card_file(verified_data, tmp_path):
    data = verified_data()
    code = main(["--data-dir", str(data), "check", str(tmp_path / "nope.json")])
    assert code == EXIT_USAGE


def test_exit_2_on_bad_json(verified_data, tmp_path):
    data = verified_data()
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    code = main(["--data-dir", str(data), "check", str(bad)])
    assert code == EXIT_USAGE


def test_exit_2_on_invalid_card_fields(verified_data, card_file):
    data = verified_data()
    code = main(["--data-dir", str(data), "check", card_file(carrier="hologram")])
    assert code == EXIT_USAGE


def test_exit_2_when_no_command(capsys):
    code = main([])
    assert code == EXIT_USAGE


def test_bench_runs_three_suites_and_exits_0(capsys):
    """M4：``bench`` 桩转实现——三类基准一条命令跑全，全达标 exit 0。

    用**仓库真实数据目录**（内置基准的达标口径就是针对仓库规则库声明的），
    故不传 ``--data-dir``。
    """
    code = main(["bench"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    for name in ("fields", "constructed", "diff"):
        assert name in captured.out
    assert "全部达标" in captured.out
    assert captured.err == "", "达标时不得往 stderr 写失败提示"


def test_bench_json_output_is_parseable(capsys):
    code = main(["bench", "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["passed"] is True
    assert [suite["name"] for suite in payload["suites"]] == ["fields", "constructed", "diff"]
    for suite in payload["suites"]:
        for metric in suite["metrics"]:
            assert metric["passed"] is True


def test_bench_only_selects_subset(capsys):
    code = main(["bench", "--only", "diff"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "[达标] diff" in captured.out
    assert "constructed" not in captured.out


def test_bench_unknown_name_is_usage_error(capsys):
    code = main(["bench", "--only", "nope"])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "未知基准名" in captured.err


# ------------------------------------------------------------------ 退出码 3（环境）
def test_exit_3_when_data_dir_missing(card_file, tmp_path):
    code = main(["--data-dir", str(tmp_path / "nope"), "check", card_file()])
    assert code == EXIT_ENV


def test_exit_3_when_registry_corrupt(card_file, tmp_path):
    data = build_data_dir(tmp_path / "data", {"doc": {"status": "pending", "rules": []}})
    (data / "rules" / "registry.json").write_text("{broken", encoding="utf-8")
    code = main(["--data-dir", str(data), "check", card_file()])
    assert code == EXIT_ENV


def test_selfcheck_exit_3_on_bad_data_dir(tmp_path, capsys):
    code = main(["--data-dir", str(tmp_path / "nope"), "selfcheck"])
    captured = capsys.readouterr()
    assert code == EXIT_ENV
    assert "自检失败" in captured.err


# ------------------------------------------------------------------ json 输出契约
def test_check_json_output_is_parseable(card_file, verified_data, capsys):
    data = verified_data()
    code = main(["--data-dir", str(data), "check", card_file(), "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["card_id"] == "SYN-TEST-0001"
    assert "ruleset" in payload and "coordinate" in payload["ruleset"]
    assert payload["disclaimer"]


def test_check_json_is_deterministic(card_file, verified_data, capsys):
    """相同输入两次运行 → stdout 逐字节一致（产物无时间戳）。"""
    data = verified_data()
    main(["--data-dir", str(data), "check", card_file(), "--json"])
    first = capsys.readouterr().out
    main(["--data-dir", str(data), "check", card_file(), "--json"])
    second = capsys.readouterr().out
    assert first == second


def test_check_json_only_json_on_stdout(card_file, verified_data, capsys):
    """--json 模式 stdout 只能有 JSON（供上游程序消费）。"""
    data = verified_data()
    main(["--data-dir", str(data), "check", card_file(), "--json"])
    captured = capsys.readouterr()
    json.loads(captured.out)  # 解析失败即说明混入了非 JSON 内容


# ------------------------------------------------------------------ 未评估提示
def test_not_assessed_warns_on_stderr(tmp_path, card_file, capsys):
    data = build_data_dir(tmp_path / "data", {
        "doc": {"version": "2025-09-01", "status": "pending",
                "rules": [make_rule("r", scope="implicit", target="content_property")]},
    })
    code = main(["--data-dir", str(data), "check", card_file()])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "not_assessed" in captured.out
    assert "未进行评估" in captured.err


# ------------------------------------------------------------------ version / selfcheck
def test_version_subcommand(capsys):
    code = main(["version"])
    captured = capsys.readouterr()
    assert code == 0
    assert "labelcheck" in captured.out


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    captured = capsys.readouterr()
    assert excinfo.value.code == 0
    assert "labelcheck" in captured.out


def test_selfcheck_on_repo_data(capsys):
    """仓库随附数据：selfcheck 应报出已核对生效的规则数（M1 后非空）。"""
    code = main(["selfcheck", "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["verified_rule_count"] > 0, "M1 后应有已核对生效的规则"
    assert payload["pending_rule_count"] >= 0
    assert payload["ruleset_coordinate"].startswith("labeling-measures@")
    assert payload["mapping_verified_field_count"] >= 5


def test_selfcheck_human_output_mentions_gating(capsys):
    main(["selfcheck"])
    captured = capsys.readouterr()
    assert "生效规则" in captured.out
    assert "待核对" in captured.out


# ------------------------------------------------------------------ M2：解析通路
@pytest.fixture
def container_file(tmp_path):
    """把夹具里的真实容器字节落到磁盘（测 check/parse 的容器分派）。"""
    import base64
    import sys
    from pathlib import Path

    tools = Path(__file__).resolve().parent.parent / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from gen_parse import aigc_json, png_bytes

    def _write(name="img.png", payload=None):
        data = payload if payload is not None else png_bytes([("tEXt", "XML:com.adobe.xmp", aigc_json())])
        path = tmp_path / name
        path.write_bytes(data)
        return str(path)

    return _write


def test_check_accepts_container_file(container_file, capsys):
    """check 直接吃容器文件：解析通路 → 核验，显式作用域 unknown 而非 fail。"""
    code = main(["check", container_file()])
    captured = capsys.readouterr()
    assert code == EXIT_OK, "隐式齐备、显式未观测 → 无 fail，退出码 0"
    assert "partial" in captured.out
    assert "explicit" in captured.out  # 未观测作用域在报告里如实出现
    assert "未被观测" in captured.err


def test_check_container_json_has_parse_block(container_file, capsys):
    code = main(["check", container_file(), "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["source"] == "parsed"
    assert payload["parse"]["container"] == "png"
    assert payload["parse"]["explicit_observed"] is False


def test_check_rejects_non_container_non_json(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("plain text, not json, not a container", encoding="utf-8")
    assert main(["check", str(bad)]) == EXIT_USAGE


def test_parse_subcommand_json(container_file, capsys):
    code = main(["parse", container_file(), "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    card = json.loads(captured.out)
    assert card["source"] == "parsed"
    assert card["observed"]["explicit"] is False
    assert card["implicit"]


def test_parse_subcommand_writes_card_to_file(container_file, tmp_path, capsys):
    out = tmp_path / "card.json"
    code = main(["parse", container_file(), "--out", str(out)])
    assert code == EXIT_OK
    card = json.loads(out.read_text(encoding="utf-8"))
    assert card["source"] == "parsed"
    # 写出的卡再喂 check 必须可核验（两通路产出同一 UMR）
    assert main(["check", str(out)]) == EXIT_OK


def test_parse_subcommand_rejects_non_container(tmp_path):
    """parse 只吃容器：非容器属用法/输入错误（exit 2），不静默给空卡。"""
    bad = tmp_path / "notes.txt"
    bad.write_text("plain text", encoding="utf-8")
    assert main(["parse", str(bad)]) == EXIT_USAGE


def test_parse_subcommand_rejects_missing_file(tmp_path):
    assert main(["parse", str(tmp_path / "nope.png")]) == EXIT_USAGE


# ------------------------------------------------------------------ M2：场景
def test_check_scenario_flag_overrides_card(container_file, capsys):
    code = main(["check", container_file(), "--scenario", "propagated", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["scenario"] == "propagated"
    # 传播场景下传播要素（缺失）应生效并计入 missing
    assert "content_propagator" in payload["missing"] or code == EXIT_FINDINGS


def test_check_rejects_unknown_scenario(card_file):
    with pytest.raises(SystemExit):
        main(["check", card_file(), "--scenario", "telepathy"])


# ------------------------------------------------------------------ M3：批量扫描
@pytest.fixture
def scan_cases(tmp_path):
    """扫描输入目录（与数据目录分开，避免把规则库 JSON 也扫进来）。"""
    path = tmp_path / "cases"
    path.mkdir()
    return path


def _write_card(path, **overrides):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(make_card(**overrides), ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def scan_data(tmp_path):
    """一条生效隐式 presence 规则（缺字段 → fail）。"""
    return build_data_dir(
        tmp_path / "scan-data",
        {"doc": {"version": "2025-09-01", "status": "verified",
                 "rules": [make_rule("r", scope="implicit", target="content_property",
                                     check_type="presence", severity="critical",
                                     status="verified")]}},
        mapping_fields=[make_mapping_field("content_property", ["content.property"],
                                           status="verified")],
    )


def test_scan_exit_0_when_no_violation(scan_cases, scan_data, capsys):
    _write_card(scan_cases / "a.json", implicit={"content.property": "AI"})
    code = main(["--data-dir", str(scan_data), "scan", str(scan_cases), "--quiet"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "批量扫描完成" in captured.out


def test_scan_exit_1_when_violation_found(scan_cases, scan_data, capsys):
    _write_card(scan_cases / "a.json", implicit={})
    code = main(["--data-dir", str(scan_data), "scan", str(scan_cases), "--quiet"])
    captured = capsys.readouterr()
    assert code == EXIT_FINDINGS, "批量检出违规以 1 退出（与单件一致）"
    assert "检出违规" in captured.out


def test_scan_exit_2_on_missing_target(scan_data, tmp_path):
    code = main(["--data-dir", str(scan_data), "scan", str(tmp_path / "nope")])
    assert code == EXIT_USAGE


def test_scan_exit_3_when_data_dir_missing(scan_cases, tmp_path):
    _write_card(scan_cases / "a.json", implicit={"content.property": "AI"})
    code = main(["--data-dir", str(tmp_path / "nope"), "scan", str(scan_cases)])
    assert code == EXIT_ENV


def test_scan_json_is_parseable_and_only_json(scan_cases, scan_data, capsys):
    _write_card(scan_cases / "a.json", implicit={"content.property": "AI"})
    code = main(["--data-dir", str(scan_data), "scan", str(scan_cases), "--json", "--quiet"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["summary"]["total"] == 1
    assert payload["items"][0]["card_id"] == "SYN-TEST-0001"


def test_scan_json_is_deterministic(scan_cases, scan_data, capsys):
    _write_card(scan_cases / "a.json", implicit={})
    main(["--data-dir", str(scan_data), "scan", str(scan_cases), "--json", "--quiet"])
    first = capsys.readouterr().out
    main(["--data-dir", str(scan_data), "scan", str(scan_cases), "--json", "--quiet"])
    second = capsys.readouterr().out
    assert first == second


def test_scan_out_exports_report_files(scan_cases, scan_data, tmp_path, capsys):
    _write_card(scan_cases / "a.json", implicit={"content.property": "AI"})
    out = tmp_path / "report-out"
    code = main(["--data-dir", str(scan_data), "scan", str(scan_cases),
                 "--out", str(out), "--quiet"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert (out / "report.md").is_file()
    assert (out / "summary.csv").is_file()
    assert (out / "detail.csv").is_file()
    assert (out / "evidence.json").is_file()
    assert "报告已导出" in captured.err


def test_scan_baseline_reconciliation(scan_cases, scan_data, tmp_path, capsys):
    """``--baseline`` 读上轮 ScanResult → 输出两轮对账（新增/已修复/持续）。"""
    _write_card(scan_cases / "a.json", card_id="A", implicit={})
    baseline = tmp_path / "baseline.json"
    main(["--data-dir", str(scan_data), "scan", str(scan_cases),
          "--json", "--quiet", "--out", str(tmp_path / "r1")])
    capsys.readouterr()
    # 把上轮 JSON 落盘（模拟上一轮存档）
    main(["--data-dir", str(scan_data), "scan", str(scan_cases), "--json", "--quiet"])
    baseline.write_text(capsys.readouterr().out, encoding="utf-8")

    _write_card(scan_cases / "a.json", card_id="A", implicit={"content.property": "AI"})
    code = main(["--data-dir", str(scan_data), "scan", str(scan_cases),
                 "--baseline", str(baseline), "--json", "--quiet"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == EXIT_OK
    assert payload["diff"]["summary"]["fixed"] == 1


def test_scan_baseline_rejects_bad_json(scan_cases, scan_data, tmp_path):
    _write_card(scan_cases / "a.json", implicit={"content.property": "AI"})
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    code = main(["--data-dir", str(scan_data), "scan", str(scan_cases),
                 "--baseline", str(bad), "--quiet"])
    assert code == EXIT_USAGE


def test_scan_isolates_failures_without_aborting(scan_cases, scan_data, capsys):
    """坏件隔离：整批不中断，stderr 给出失败提示。"""
    _write_card(scan_cases / "ok.json", implicit={"content.property": "AI"})
    (scan_cases / "broken.json").write_text("{not json", encoding="utf-8")
    manifest = scan_cases / "list.lst"
    manifest.write_text("ok.json\nbroken.json\n", encoding="utf-8")
    code = main(["--data-dir", str(scan_data), "scan", str(manifest), "--quiet"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "扫描失败" in captured.err


# ------------------------------------------------------------------ M5：gui 子命令
def test_gui_subcommand_check_mode_exits_ok(capsys):
    """``gui --check``：可加载性自检（无显示环境用 offscreen），exit 0。

    无 PySide6 的环境应 exit 3（环境/依赖错误）——两种结果都合法，但不得抛裸异常。
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        import PySide6  # noqa: F401
    except ImportError:
        code = main(["gui", "--check"])
        assert code == EXIT_ENV, "缺 GUI 依赖应为环境错误（exit 3），而非裸异常"
        return
    code = main(["gui", "--check"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "GUI 自检通过" in captured.out
    assert "6 个页签" in captured.out


def test_gui_subcommand_is_registered_in_help(capsys):
    """``gui`` 必须出现在帮助里（子命令已注册）。"""
    with pytest.raises(SystemExit):
        main(["--help"])
    captured = capsys.readouterr()
    assert "gui" in captured.out
