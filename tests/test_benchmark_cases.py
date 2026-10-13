# -*- coding: utf-8 -*-
"""基准算例与对账口径的测试（FR-11，契约见 plan/04 §九 / plan/05 §三.2）。

锁死四件事：

1. **对账口径**（:func:`observed_nonpass` / :func:`compare_nonpass`）：
   ``fail ∪ unknown`` 同目标算一个；**未观测的 scope 排除在比较之外**（解析通路
   "显式恒未观测"正是这一形态——若把它算进去，解析算例会被误判成"显式缺失"）；
2. **零政策字面量**：算例构造的取值/枚举**全部从规则库/映射表派生**——
   同一份规则库换一套取值，基准照样跑（不硬编码任何规则取值）；
3. **不许改真值凑引擎**：真值库（``data/truth/``）与解析算例（``data/parse/``）的
   声明非 pass 集合与引擎实际输出**完全一致**（与基准共用同一对账函数）；
4. **零时钟/零随机**：同一输入两次构造的算例**逐字节一致**（基准可复现的前提）。
"""

import base64
import json
import sys
from pathlib import Path

import pytest

from labelcheck.benchmark import cases as C
from labelcheck.paths import find_data_dir

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = ROOT / "src"


@pytest.fixture(scope="module")
def data_dir():
    return find_data_dir()


@pytest.fixture(scope="module")
def engine(data_dir):
    return C.load_ruleset_and_mapping(data_dir)


# ------------------------------------------------------------------ 对账口径
def test_observed_nonpass_is_fail_union_unknown():
    """非 pass = fail ∪ unknown（同目标算一个）。"""
    from labelcheck.model import CheckReport, Finding

    report = CheckReport(
        card_id="X", carrier="text",
        explicit=[Finding(scope="explicit", target="e1", status="fail", code="c1")],
        implicit=[
            Finding(scope="implicit", target="i1", status="unknown", code="c2"),
            Finding(scope="implicit", target="i2", status="pass"),
            Finding(scope="implicit", target="i1", status="fail", code="c3"),
        ],
    )
    assert C.observed_nonpass(report, "explicit") == ["e1"]
    assert C.observed_nonpass(report, "implicit") == ["i1"]  # i1 的 unknown 与 fail 合并


def test_observed_nonpass_excludes_unobserved_scope():
    """未观测的 scope 返回 ``None``（"没看到"≠"缺失"，无从比较）。"""
    from labelcheck.model import CheckReport, Finding

    report = CheckReport(
        card_id="X", carrier="image",
        explicit=[Finding(scope="explicit", target="e1", status="unknown", code="not_observed")],
        implicit=[Finding(scope="implicit", target="i1", status="pass")],
        observed={"explicit": False, "implicit": True},
    )
    assert C.observed_nonpass(report, "explicit") is None
    assert C.observed_nonpass(report, "implicit") == []
    # 未观测的 scope 不参与比较（expected 为空也不报错）
    assert C.compare_nonpass(report, {"explicit": [], "implicit": []}) == []


def test_compare_nonpass_reports_mismatch():
    from labelcheck.model import CheckReport, Finding

    report = CheckReport(
        card_id="X", carrier="text",
        implicit=[Finding(scope="implicit", target="i1", status="fail", code="c")],
    )
    lines = C.compare_nonpass(report, {"implicit": ["other"]})
    assert lines and "implicit" in lines[0]


# ------------------------------------------------------------------ 真值库对账（同一口径）
def test_truth_library_reconciles_through_shared_reconciler(data_dir):
    """真值库每例的非 pass 集合与引擎一致（走基准的同一对账函数）。"""
    index = json.loads((DATA / "truth" / "index.json").read_text(encoding="utf-8"))
    mismatches = []
    for case in index["cases"]:
        payload = json.loads((DATA / "truth" / case["file"]).read_text(encoding="utf-8"))
        report = C.check_card_dict(payload["input_card"], data_dir)
        expected = payload["expected"]
        declared = {
            "implicit": expected["also_expect"]["implicit_fail_targets"],
            "explicit": expected["also_expect"]["explicit_fail_targets"],
        }
        for line in C.compare_nonpass(report, declared):
            mismatches.append("{0}: {1}".format(case["case_id"], line))
        if report.grade != expected["grade"]:
            mismatches.append("{0}: grade {1} != {2}".format(
                case["case_id"], report.grade, expected["grade"]))
    assert not mismatches, "\n".join(mismatches)


def test_parse_fixtures_reconcile_through_shared_reconciler(data_dir, engine):
    """解析算例每例的非 pass 集合与引擎一致；**显式恒未观测 → 不参与比较**。

    这条正是"未观测排除"的现实检验：11 例解析算例的显式作用域全部未观测，
    若把它算进比较，每例都会报"显式非 pass 集合 [] != 期望 []"之类的假失败。
    """
    _ruleset, table = engine
    from labelcheck.parse import parse_bytes

    fixtures = json.loads((DATA / "parse" / "fixtures.json").read_text(encoding="utf-8"))
    mismatches = []
    for item in fixtures["fixtures"]:
        raw = base64.b64decode(item["bytes_b64"])
        outcome = parse_bytes(raw, item["container"], table.payload_wrapper)
        assert outcome.explicit_observed is False, (
            "{0}: 解析通路显式作用域应恒为未观测".format(item["fixture_id"]))
        report = C.check_card_dict(outcome.card.to_dict(), data_dir)
        declared = {
            "implicit": item["expected"]["implicit_fail_targets"],
            "explicit": item["expected"]["explicit_fail_targets"],
        }
        for line in C.compare_nonpass(report, declared):
            mismatches.append("{0}: {1}".format(item["fixture_id"], line))
    assert not mismatches, "\n".join(mismatches)


# ------------------------------------------------------------------ 期望值来自规则库（零硬编码）
def test_expected_values_are_derived_from_ruleset(data_dir, engine):
    """合规取值/位置由规则库派生——改规则库取值，构造的合规件仍应判 compliant。"""
    ruleset, mapping = engine
    fields = C.implicit_targets_for(ruleset, "text", "authored")
    assert fields, "仓库规则库应有隐式字段"
    enum_field = None
    for field in fields:
        allowed = C.allowed_values(ruleset, "implicit", field, "enum", "text", "authored")
        if allowed:
            enum_field = (field, allowed)
            break
    assert enum_field is not None, "仓库规则库应有 enum 规则（用于派生合规取值）"
    field, allowed = enum_field
    assert C.valid_implicit_value(ruleset, field, "text", "authored") == allowed[0]

    element = C.explicit_targets_for(ruleset, "text", "authored")[0]
    positions = C.allowed_values(ruleset, "explicit", element, "position", "text", "authored")
    built = C.explicit_element(ruleset, element, "text", "authored")
    assert built["position"] == positions[0]
    assert C.valid_card(ruleset, "X", "text")["implicit"][field] == allowed[0]


def test_case_construction_is_deterministic(data_dir, engine):
    """同一输入两次构造的算例逐字节一致（零时钟/零随机）。"""
    ruleset, mapping = engine
    first = json.dumps(C.field_cases(ruleset, mapping), ensure_ascii=False, sort_keys=True)
    second = json.dumps(C.field_cases(ruleset, mapping), ensure_ascii=False, sort_keys=True)
    assert first == second

    first_diff = [(s[0], s[2].to_dict(), s[3].to_dict(), s[4])
                  for s in C.diff_scenarios(ruleset, data_dir)]
    second_diff = [(s[0], s[2].to_dict(), s[3].to_dict(), s[4])
                   for s in C.diff_scenarios(ruleset, data_dir)]
    assert json.dumps(first_diff, ensure_ascii=False, sort_keys=True) == \
        json.dumps(second_diff, ensure_ascii=False, sort_keys=True)


def test_case_ids_are_unique(data_dir, engine):
    """算例 id 不得重复（防"改一条忘改 id"导致报告里两例同名）。"""
    ruleset, mapping = engine
    ids = [case["case_id"] for case in C.field_cases(ruleset, mapping)]
    assert len(ids) == len(set(ids)), "fields 算例 id 重复"

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        synthetic = C.build_synthetic_data_dirs(tmp)
        cons = [case["case_id"] for case in C.constructed_cases(
            ruleset, mapping, synthetic, data_dir=data_dir)]
    assert len(cons) == len(set(cons)), "constructed 算例 id 重复"


# ------------------------------------------------------------------ 算例构成
def test_field_cases_cover_every_available_check_type(data_dir, engine):
    """fields 基准须覆盖规则库里**实际存在**的每个 check_type（含边界/畸形输入）。"""
    ruleset, mapping = engine
    present = set(rule.check_type for rule in ruleset.effective)
    covered = set(case["check_type"] for case in C.field_cases(ruleset, mapping))
    assert present <= covered, "未覆盖的 check_type：{0}".format(sorted(present - covered))
    # range 在仓库规则库中不存在（建条决策 D27）→ 如实记入说明，不假装覆盖
    assert C.missing_check_types(ruleset) == ["range"]


def test_field_cases_include_malformed_inputs(data_dir, engine):
    """必须含畸形输入用例（present 非布尔/取值非字符串/类型不符），防"只测 happy path"。"""
    ruleset, mapping = engine
    ids = set(case["case_id"] for case in C.field_cases(ruleset, mapping))
    for required in ("FIELD-PRESENCE-ELEMENT-UNKNOWN-PRESENCE",
                     "FIELD-PATTERN-NON-STRING",
                     "FIELD-TYPE-MISMATCH-INT",
                     "FIELD-TYPE-MISMATCH-LIST",
                     "FIELD-POSITION-MISSING"):
        assert required in ids, "缺畸形输入用例：{0}".format(required)


def test_constructed_cases_cover_required_groups(data_dir, engine):
    """constructed 基准须覆盖 plan/05 §三.3 的全部缺陷注入类型（含边界情形）。"""
    ruleset, mapping = engine
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        synthetic = C.build_synthetic_data_dirs(tmp)
        groups = set(case["group"] for case in C.constructed_cases(
            ruleset, mapping, synthetic, data_dir=data_dir))
    required = {
        "correct", "missing_field", "wrong_position", "wrong_value", "bad_format",
        "metadata_stripped", "explicit_only", "explicit_absent", "duplicate_implicit",
        "unobserved", "engine_branch", "truth_library",
    }
    missing = required - groups
    assert not missing, "constructed 基准缺注入类型：{0}".format(sorted(missing))


def test_constructed_cases_consume_shipped_truth_library(data_dir, engine):
    """基准须**直接消费** ``data/truth/`` 的随附算例（HANDOFF-M4 §三.3：不另造一套）。

    每例的期望值取自真值库 ``expected``（非抄引擎输出）；``correct`` 例进误报率分母。
    """
    ruleset, mapping = engine
    index = json.loads((DATA / "truth" / "index.json").read_text(encoding="utf-8"))
    cases = C.truth_library_cases(data_dir)
    assert [case["case_id"] for case in cases] == [entry["case_id"] for entry in index["cases"]]

    by_id = {case["case_id"]: case for case in cases}
    for entry in index["cases"]:
        case = by_id[entry["case_id"]]
        payload = json.loads((DATA / "truth" / entry["file"]).read_text(encoding="utf-8"))
        assert case["expect_grade"] == payload["expected"]["grade"]
        assert case["expect_nonpass"]["implicit"] == sorted(
            payload["expected"]["also_expect"]["implicit_fail_targets"])
        assert case["clean"] == (payload["expected"]["injected"]["defect"] == "correct")

    # 与程序化构造例合并后，truth_library 组仍完整存在
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        synthetic = C.build_synthetic_data_dirs(tmp)
        merged = C.constructed_cases(ruleset, mapping, synthetic, data_dir=data_dir)
    assert sum(1 for case in merged if case["group"] == "truth_library") == len(index["cases"])


def test_truth_library_cases_absent_without_data_dir(engine):
    """未给 ``data_dir`` 时不并入随附真值（避免隐式依赖调用点）。"""
    ruleset, mapping = engine
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        synthetic = C.build_synthetic_data_dirs(tmp)
        cases = C.constructed_cases(ruleset, mapping, synthetic, data_dir=None)
    assert not any(case["group"] == "truth_library" for case in cases)


def test_constructed_cases_have_both_denominators(data_dir, engine):
    """检出率与误报率都须有非空分母（否则指标是空验）。"""
    ruleset, mapping = engine
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        synthetic = C.build_synthetic_data_dirs(tmp)
        cases = C.constructed_cases(ruleset, mapping, synthetic, data_dir=data_dir)
    assert any(case["detection"] for case in cases), "缺检出率分母"
    assert any(case["clean"] for case in cases), "缺误报率分母"


def test_engine_branch_cases_require_synthetic_dirs(data_dir, engine):
    """未提供合成数据目录时，引擎分支用例不生成（并须在说明里体现）。"""
    ruleset, mapping = engine
    without = C.constructed_cases(ruleset, mapping, synthetic_dirs=None)
    assert not any(case["group"] == "engine_branch" for case in without)


def test_synthetic_data_dirs_are_isolated(data_dir, engine, tmp_path):
    """合成数据目录在临时目录里自造（不污染仓库规则库）。"""
    synthetic = C.build_synthetic_data_dirs(tmp_path)
    for name, path in synthetic.items():
        assert (Path(path) / "rules" / "registry.json").is_file(), name
    assert str(tmp_path) in str(synthetic["unmapped"])


def test_diff_scenarios_cover_every_collection(data_dir, engine):
    """diff 基准须覆盖全部对账集合（三类主集合 + 辅助集合）。"""
    ruleset, _mapping = engine
    scenarios = C.diff_scenarios(ruleset, data_dir)
    assert scenarios, "未生成对账场景"
    covered = set()
    for scenario in scenarios:
        for name in C.DIFF_COLLECTIONS:
            if scenario[4].get(name):
                covered.add(name)
    missing = set(C.DIFF_COLLECTIONS) - covered
    assert not missing, "对账场景未覆盖集合：{0}".format(sorted(missing))