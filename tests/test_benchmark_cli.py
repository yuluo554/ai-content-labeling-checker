# -*- coding: utf-8 -*-
"""``bench`` 子命令测试（FR-11，契约见 plan/04 §二.1 / §九）。

锁死：

1. **桩已转实现**：``bench`` 不再是 exit 2 的未实现桩；三类基准一条命令跑全；
2. **退出码**：``0`` 全部达标 / ``1`` 有基准未达标 / ``2`` 用法错误（未知基准名）；
3. **输出纪律**：人类可读到 stdout；``--json`` 只有 JSON（供管道消费）；
4. **零 API 依赖**：bench 通路不触网（与 NFR-1 一致）。
"""

import json

from labelcheck.cli.main import main
from labelcheck.errors import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE


def test_bench_exit_0_and_lists_three_suites(capsys):
    code = main(["bench"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "全部达标" in captured.out
    for name in ("fields", "constructed", "diff"):
        assert name in captured.out


def test_bench_json_only_json_on_stdout(capsys):
    code = main(["bench", "--json"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(captured.out)  # 整份 stdout 必须是合法 JSON
    assert payload["passed"] is True
    assert payload["ruleset_coordinate"]
    assert len(payload["suites"]) == 3


def test_bench_json_is_deterministic(capsys):
    main(["bench", "--json"])
    first = capsys.readouterr().out
    main(["bench", "--json"])
    second = capsys.readouterr().out
    assert first == second, "相同输入两次 bench 输出必须逐字节一致"


def test_bench_only_subset(capsys):
    code = main(["bench", "--only", "fields,diff"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "fields" in captured.out and "diff" in captured.out
    assert "[达标] constructed" not in captured.out


def test_bench_unknown_name_exits_2(capsys):
    code = main(["bench", "--only", "nope"])
    captured = capsys.readouterr()
    assert code == EXIT_USAGE
    assert "未知基准名" in captured.err


def test_bench_verbose_shows_metric_details(capsys):
    code = main(["bench", "-v"])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert "判定准确率" in captured.out
    assert "检出率" in captured.out
    assert "误报率" in captured.out


def test_bench_reports_failure_with_exit_1(capsys, monkeypatch):
    """有基准未达标 → exit 1（与 ``check``/``scan`` 的 1 = 检出问题语义一致）。"""
    from labelcheck.benchmark import runner_fields
    from labelcheck.cli.main import main

    monkeypatch.setattr(runner_fields, "check_field_case",
                        lambda case, d: ["注入的模拟不一致"])
    code = main(["bench"])
    captured = capsys.readouterr()
    assert code == EXIT_FINDINGS
    assert "未达标" in captured.out
    assert "未达标" in captured.err