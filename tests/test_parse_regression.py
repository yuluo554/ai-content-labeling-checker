# -*- coding: utf-8 -*-
"""解析通路算例回归（M2 的"算例回归 100%"出口条件）。

**回归链路**：``data/parse/fixtures.json`` 的**真实容器字节** → base64 解码 →
``labelcheck.parse.parse_bytes`` 解析 → ``labelcheck.engine.check_card`` 核验 →
与夹具声明的 ``expected`` 对账。

与 ``test_generators.py`` 的"引擎对账"互补：那里比对的是**手工标识卡**，
这里比对的是**容器文件解析出的标识卡**——多了一段真实字节解析路径。

**对账语义**（plan/05 §三.2 的同一口径）：比对 ``grade``、两个 scope 的 fail 目标集、
可观测性声明与降级原因码。**不许改真值凑引擎**——真值由 ``tools/gen_parse.py``
与夹具同源生成。

**守门**：夹具须覆盖解析通路的全部关键形态（含结构截断/无载荷/重复保留），
且生成器 ``--check`` 位级一致。
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = ROOT / "src"
TOOLS = ROOT / "tools"

FIXTURES = DATA / "parse" / "fixtures.json"


@pytest.fixture(scope="module")
def fixtures():
    assert FIXTURES.is_file(), "解析算例夹具缺失（跑 tools/gen_parse.py 生成）"
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def engine():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from labelcheck.engine import check_card
    from labelcheck.mapping import load_mapping_table
    from labelcheck.paths import find_data_dir
    from labelcheck.parse import parse_bytes

    data_dir = find_data_dir()
    table = load_mapping_table(data_dir)
    return check_card, parse_bytes, data_dir, table.payload_wrapper


def test_fixtures_have_real_container_bytes(fixtures):
    """夹具必须内含**真实容器字节**（能被识别为 PNG/JPEG/ISO BMFF）。"""
    for item in fixtures["fixtures"]:
        raw = base64.b64decode(item["bytes_b64"])
        assert raw, "{0}: 字节为空".format(item["fixture_id"])
        from labelcheck.parse import detect_container
        assert detect_container(raw) == item["container"], (
            "{0}: 字节魔数与声明的容器不一致".format(item["fixture_id"]))


def test_parse_regression_all_cases_reconcile(fixtures, engine):
    """**核心对账**：逐例跑 解析 → 核验 → 与真值比对，全部一致。"""
    check_card, parse_bytes, data_dir, wrapper = engine
    mismatches = []

    for item in fixtures["fixtures"]:
        fixture_id = item["fixture_id"]
        raw = base64.b64decode(item["bytes_b64"])
        outcome = parse_bytes(raw, item["container"], wrapper)
        report = check_card(outcome.card, data_dir)
        expected = item["expected"]

        if outcome.implicit_observed != expected["implicit_observed"]:
            mismatches.append("{0}: implicit_observed {1} != 期望 {2}".format(
                fixture_id, outcome.implicit_observed, expected["implicit_observed"]))
        if outcome.explicit_observed != expected["explicit_observed"]:
            mismatches.append("{0}: explicit_observed {1} != 期望 {2}".format(
                fixture_id, outcome.explicit_observed, expected["explicit_observed"]))
        if report.grade != expected["grade"]:
            mismatches.append("{0}: grade {1} != 期望 {2}".format(
                fixture_id, report.grade, expected["grade"]))

        actual_imp = sorted(set(f.target for f in report.implicit if f.status == "fail"))
        want_imp = sorted(expected["implicit_fail_targets"])
        if actual_imp != want_imp:
            mismatches.append("{0}: 隐式 fail {1} != 期望 {2}".format(
                fixture_id, actual_imp, want_imp))

        actual_exp = sorted(set(f.target for f in report.explicit if f.status == "fail"))
        want_exp = sorted(expected["explicit_fail_targets"])
        if actual_exp != want_exp:
            mismatches.append("{0}: 显式 fail {1} != 期望 {2}".format(
                fixture_id, actual_exp, want_exp))

        missing_reasons = set(expected.get("reasons", [])) - set(outcome.reasons)
        if missing_reasons:
            mismatches.append("{0}: 缺降级原因 {1}（实际 {2}）".format(
                fixture_id, sorted(missing_reasons), outcome.reasons))

    assert not mismatches, (
        "解析算例与真值不一致（改引擎口径须同步改生成器，不许凑）：\n" + "\n".join(mismatches))


def test_parse_regression_covers_required_forms(fixtures):
    """夹具须覆盖解析通路的关键形态（防"只测 happy path"）。"""
    defects = set(item["injected"]["defect"] for item in fixtures["fixtures"])
    required = {"correct", "missing_field", "wrong_value", "bad_format",
                "metadata_stripped", "duplicate_label", "structure_broken"}
    missing = required - defects
    assert not missing, "解析算例缺关键形态：{0}".format(sorted(missing))

    containers = set(item["container"] for item in fixtures["fixtures"])
    assert {"png", "jpeg", "iso-bmff"} <= containers, "须覆盖三种容器"

    carriers = set(item["carrier"] for item in fixtures["fixtures"])
    assert {"image", "video", "audio"} <= carriers, "须覆盖图片/视频/音频载体"


def test_parse_regression_includes_unobserved_degradation(fixtures):
    """必须含"未观测 → 不给假结论"的算例（截断/无载荷）。"""
    has_unobserved = any(
        not item["expected"]["implicit_observed"] for item in fixtures["fixtures"])
    assert has_unobserved, "缺少结构不可用（未观测）算例——降级路径未进回归"
    has_observed_empty = any(
        item["expected"]["implicit_observed"]
        and item["expected"]["implicit_fail_targets"]
        for item in fixtures["fixtures"])
    assert has_observed_empty, "缺少'已观测但确实缺失标识'算例——与'未观测'未区分"


def test_parse_fixtures_regeneration_is_byte_identical():
    """``tools/gen_parse.py --check`` 必须通过（禁手改，位级一致）。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(TOOLS / "gen_parse.py"), "--check"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "gen_parse.py --check 失败（夹具与生成器不一致）：\n"
        "stdout:\n{0}\nstderr:\n{1}".format(result.stdout, result.stderr))


def test_parse_fixtures_have_no_cr():
    """夹具为冻结文本资产：不得含 CR（跨平台字节一致前提）。"""
    assert b"\r" not in FIXTURES.read_bytes(), "解析夹具出现 CR"


def test_parse_fixtures_are_fictional():
    """数据红线：解析算例的**载荷内容**不得含真实平台/联系方式痕迹。

    （``source_url`` 为官方依据出处，属正当引用，不在此列——故只扫载荷字段。）
    """
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    offenders = []
    for item in payload["fixtures"]:
        haystack = json.dumps(
            {"expected": item["expected"], "notes": item["notes"],
             "bytes_b64": item["bytes_b64"]},
            ensure_ascii=False)
        for token in ("微博", "微信", "抖音", "字节跳动", "腾讯", "百度",
                      "阿里巴巴", "@"):
            if token in haystack:
                offenders.append("{0} 含 {1!r}".format(item["fixture_id"], token))
    assert not offenders, "解析算例出现疑似真实来源痕迹：\n" + "\n".join(offenders)
