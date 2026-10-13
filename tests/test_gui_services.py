"""GUI 服务层测试（**零 Qt**）：唯一引擎调用点，无 PySide6 也能跑。

覆盖：场景归一、单件核验、批量扫描 + 两轮对账、报告导出、基准、规则库概览，
以及"错误转成可预期异常"的分流。这些是界面的**数据面**，与 Qt 控件无关——故用
普通 pytest 全覆盖（无需 ``QApplication``、无需 offscreen）。
"""

import json
from pathlib import Path

import pytest

from labelcheck.errors import EnvironmentError_, LabelCheckError, UsageError
from labelcheck.gui import services

from _support import build_data_dir, make_card, make_mapping_field, make_rule


@pytest.fixture
def verified_data(tmp_path):
    """一条生效隐式 presence 规则（缺字段 → fail）的完整数据目录。"""
    return build_data_dir(
        tmp_path / "data",
        {"doc": {"version": "2025-09-01", "status": "verified",
                 "rules": [make_rule("r", scope="implicit", target="content_property",
                                     check_type="presence", severity="critical",
                                     status="verified")]}},
        mapping_fields=[make_mapping_field("content_property", ["content.property"],
                                           status="verified")],
    )


def _write_card(path, **overrides):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(make_card(**overrides), ensure_ascii=False), encoding="utf-8")
    return path


# ------------------------------------------------------------------ 场景归一
def test_scenario_options_start_with_from_card_sentinel():
    options = services.scenario_options()
    assert options[0][1] == services.SCENARIO_FROM_CARD
    values = [value for _label, value in options[1:]]
    assert values == ["authored", "exported", "propagated"], "场景取值须与引擎枚举一致"


def test_normalize_scenario_maps_sentinel_to_none():
    assert services.normalize_scenario(services.SCENARIO_FROM_CARD) is None
    assert services.normalize_scenario("") is None
    assert services.normalize_scenario(None) is None
    assert services.normalize_scenario("exported") == "exported"


# ------------------------------------------------------------------ 单件核验
def test_check_single_compliant_card(tmp_path, verified_data):
    path = _write_card(tmp_path / "cases" / "ok.json", implicit={"content.property": "AI"})
    result = services.check_single(path, verified_data)
    assert result.has_violation is False
    assert result.parsed_from_container is False
    assert result.card_id == "SYN-TEST-0001"


def test_check_single_violation_card(tmp_path, verified_data):
    path = _write_card(tmp_path / "cases" / "bad.json", implicit={})
    result = services.check_single(path, verified_data)
    assert result.has_violation is True
    assert any(f.status == "fail" for f in result.report.all_findings)


def test_check_single_matches_engine_check_file(tmp_path, verified_data):
    """服务层与 CLI 共用同一分派：结果对象须与直接调引擎逐字段一致。"""
    from labelcheck.engine import check_file

    path = _write_card(tmp_path / "cases" / "ok.json", implicit={"content.property": "AI"})
    via_service = services.check_single(path, verified_data).report
    via_engine, _parse = check_file(path, verified_data)
    assert via_service.to_dict() == via_engine.to_dict(), "服务层不得改写引擎结论"


def test_check_single_missing_file_raises_expected_error(tmp_path, verified_data):
    with pytest.raises(LabelCheckError):
        services.check_single(tmp_path / "nope.json", verified_data)


def test_check_single_rejects_non_card_non_container(tmp_path, verified_data):
    path = tmp_path / "notes.txt"
    path.write_text("既不是 JSON 也不是容器", encoding="utf-8")
    with pytest.raises(UsageError):
        services.check_single(path, verified_data)


# ------------------------------------------------------------------ 批量扫描 + 对账
def test_scan_batch_summary_and_export(tmp_path, verified_data):
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    _write_card(cases / "b.json", implicit={})

    batch = services.scan_batch(cases, verified_data)
    assert batch.summary["total"] == 2
    assert batch.summary["violations"] == 1
    assert batch.diff is None

    out = tmp_path / "out"
    written = services.export_report(batch, out)
    assert any(Path(p).name == "report.md" for p in written)
    assert (out / "report.md").is_file()
    assert (out / "evidence.json").is_file()
    assert batch.out_dir == str(out)


def test_scan_batch_two_round_diff_detects_fixed(tmp_path, verified_data):
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={})

    first = services.scan_batch(cases, verified_data)
    assert first.summary["violations"] == 1

    # 修复：补齐字段 → 第二轮无违规
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    second = services.scan_batch(cases, verified_data, baseline=first.result)
    assert second.diff is not None
    assert second.diff.summary["fixed"] == 1
    assert second.diff.summary["added"] == 0


def test_load_baseline_roundtrips_scan_result_json(tmp_path, verified_data):
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    first = services.scan_batch(cases, verified_data)

    baseline_path = tmp_path / "round1.json"
    baseline_path.write_text(
        json.dumps(first.result.to_dict(), ensure_ascii=False), encoding="utf-8")

    restored = services.load_baseline(baseline_path)
    assert restored.summary["total"] == 1
    second = services.scan_batch(cases, verified_data, baseline=restored)
    assert second.diff.summary["persistent"] == 0
    assert second.diff.summary["stable"] == 1


def test_load_baseline_rejects_non_scan_result(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    with pytest.raises(UsageError):
        services.load_baseline(bad)


# ------------------------------------------------------------------ 基准 / 规则库
def test_run_bench_against_repo_data(repo_root):
    """服务层跑基准（只调 benchmark.run_benchmark）→ 仓库数据下必须全达标。"""
    report = services.run_bench(repo_root / "data")
    assert report.passed, [s.name for s in report.suites if not s.passed]
    assert [s.name for s in report.suites] == ["fields", "constructed", "diff"]


def test_run_bench_only_subset(repo_root):
    report = services.run_bench(repo_root / "data", only=["diff"])
    assert [s.name for s in report.suites] == ["diff"]


def test_rules_overview_on_repo_data(repo_root):
    overview = services.rules_overview(repo_root / "data")
    assert overview.ruleset.verified_rule_count > 0
    assert len(overview.mapping_table) >= 5
    assert overview.data_dir == str(repo_root / "data")


def test_resolve_data_dir_explicit_wins(repo_root):
    assert services.resolve_data_dir(repo_root / "data") == (repo_root / "data").resolve()


def test_require_data_dir_missing_raises(tmp_path, verified_data):
    """未注入数据目录时，页签基类应抛可预期错误（界面转提示，不崩）。"""
    from labelcheck.gui.tabs import _TabBase

    tab = _TabBase()
    with pytest.raises(EnvironmentError_):
        tab._require_data_dir()
    tab.set_data_dir(verified_data)
    assert tab._require_data_dir() == Path(verified_data)


def test_is_labelcheck_error_classifies():
    assert services.is_labelcheck_error(UsageError("x")) is True
    assert services.is_labelcheck_error(ValueError("x")) is False


def test_diff_files_reads_two_scan_result_json(tmp_path, verified_data):
    """独立对账入口：两份 ScanResult JSON → DiffResult（与 scan_batch 的 baseline 同源）。"""
    cases = tmp_path / "cases"
    _write_card(cases / "a.json", implicit={})
    first = services.scan_batch(cases, verified_data)

    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    second = services.scan_batch(cases, verified_data)

    prev = tmp_path / "r1.json"
    cur = tmp_path / "r2.json"
    prev.write_text(json.dumps(first.result.to_dict(), ensure_ascii=False), encoding="utf-8")
    cur.write_text(json.dumps(second.result.to_dict(), ensure_ascii=False), encoding="utf-8")

    diff = services.diff_files(prev, cur)
    assert diff.summary["fixed"] == 1
    assert diff.summary["added"] == 0


def test_diff_files_rejects_non_scan_result(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    with pytest.raises(UsageError):
        services.diff_files(bad, bad)
