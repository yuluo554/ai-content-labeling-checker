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


def test_exit_2_for_unimplemented_scan(verified_data, capsys):
    """未实现子命令必须显式报错，不能静默假装成功。"""
    data = verified_data()
    code = main(["--data-dir", str(data), "scan", "."])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "尚未实现" in captured.err


def test_exit_2_for_unimplemented_bench(verified_data, capsys):
    data = verified_data()
    code = main(["--data-dir", str(data), "bench"])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "尚未实现" in captured.err


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
    """仓库随附数据：selfcheck 应通过并报 0 生效规则（pending 门控可观测）。"""
    code = main(["selfcheck", "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["verified_rule_count"] == 0
    assert payload["pending_rule_count"] > 0
    assert payload["ruleset_coordinate"].startswith("labeling-measures@")


def test_selfcheck_human_output_mentions_gating(capsys):
    main(["selfcheck"])
    captured = capsys.readouterr()
    assert "生效规则" in captured.out
    assert "pending" in captured.out
