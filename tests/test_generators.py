# -*- coding: utf-8 -*-
"""生成器守门测试（plan/05 §三.1 硬要求）。

断言三件事（每件都是"否则数据不可复现"级别的纪律）：

1. **再生成位级一致**：``tools/gen_rulesets.py --check`` / ``gen_mapping.py --check`` /
   ``gen_samples.py --check`` 全部通过（产物 = 模板，禁手改）；
2. **产物无 CR**（跨平台字节一致前提；与 ``test_guard_data.py`` 的 EOL 门互补，
   此处专测生成器产物）；
3. **真值库与引擎对账**：``data/truth/`` 每例的 ``expected`` 非 pass 集合与引擎
   实际输出的非 pass 集合**完全一致**（plan/05 §三.2 对账语义；不许改真值凑引擎）。

生成器通过 ``subprocess`` 以 ``--check`` 方式跑：既验证脚本可执行，又验证产物一致。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TOOLS = ROOT / "tools"
SRC = ROOT / "src"

GENERATORS = ("gen_rulesets.py", "gen_mapping.py", "gen_samples.py", "gen_parse.py")


def _run_tool(script, *args):
    """以子进程跑生成器（与用户手动跑完全同路径），返回 CompletedProcess。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(TOOLS / script)] + list(args),
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )


@pytest.mark.parametrize("script", GENERATORS)
def test_generator_regeneration_is_byte_identical(script):
    """``--check`` 必须通过：已入库产物与重生成**逐字节一致**（禁手改的机器化）。"""
    result = _run_tool(script, "--check")
    assert result.returncode == 0, (
        "{0} --check 失败（产物与生成器不一致，或脚本报错）：\n"
        "stdout:\n{1}\nstderr:\n{2}".format(script, result.stdout, result.stderr))


def test_generator_without_check_flag_would_write_same_bytes(tmp_path):
    """把生成器输出写到临时目录，与已入库产物逐字节比对（不依赖 --check 实现）。"""
    out = tmp_path / "data"
    result = _run_tool("gen_rulesets.py", "--data-dir", str(out))
    assert result.returncode == 0, result.stderr

    for rel in sorted((DATA / "rules").rglob("*.json")):
        shipped = rel.read_bytes()
        regenerated = (out / "rules" / rel.relative_to(DATA / "rules")).read_bytes()
        assert shipped == regenerated, "规则库产物与重生成不一致：{0}".format(rel)

    result2 = _run_tool("gen_mapping.py", "--data-dir", str(out))
    assert result2.returncode == 0, result2.stderr
    assert (DATA / "mapping" / "national-fields.json").read_bytes() == (
        out / "mapping" / "national-fields.json").read_bytes()


def test_generated_data_files_have_no_cr():
    """生成器产物（rules/mapping/truth/samples/knowledge/parse）不得含 CR。"""
    offenders = []
    for sub in ("rules", "mapping", "truth", "samples", "knowledge", "parse"):
        for path in sorted((DATA / sub).rglob("*")):
            if path.is_file() and b"\r" in path.read_bytes():
                offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, "生成器产物出现 CR（跨平台复现会被打挂）：\n" + "\n".join(offenders)


def test_generated_json_has_no_timestamp_fields():
    """产物不得含时间戳字段（时间须由调用方传入 → 两次导出逐字节一致）。"""
    suspicious = ("generated_at", "timestamp", "created_at", "updated_at")
    offenders = []
    for sub in ("rules", "mapping", "truth"):
        for path in sorted((DATA / sub).rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            for token in suspicious:
                if token in text:
                    offenders.append("{0} 含 {1}".format(path.relative_to(ROOT).as_posix(), token))
    assert not offenders, "产物含时间戳字段：\n" + "\n".join(offenders)


# ------------------------------------------------------------------ 真值对账
def _engine():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from labelcheck.engine import check_card_dict
    from labelcheck.paths import find_data_dir
    return check_card_dict, find_data_dir()


def test_truth_library_reconciles_with_engine():
    """真值库声明的非 pass 集合必须与引擎实际输出完全一致（单一对账口径）。

    **对账口径的唯一实现**在 ``labelcheck.benchmark.cases``（:func:`compare_nonpass` /
    :func:`observed_fail`）——本测试与内置基准 ``bench`` 共用同一套函数，
    故"基准说达标、测试说不过"的双口径不可能出现（HANDOFF-M4 §三.3 的同源要求）。
    """
    check_card_dict, data_dir = _engine()
    from labelcheck.benchmark.cases import compare_nonpass, observed_fail, SCOPE_ORDER

    index = json.loads((DATA / "truth" / "index.json").read_text(encoding="utf-8"))
    assert index["cases"], "真值库不得为空"

    mismatches = []
    for case in index["cases"]:
        payload = json.loads(
            (DATA / "truth" / case["file"]).read_text(encoding="utf-8"))
        report = check_card_dict(payload["input_card"], data_dir)
        expected = payload["expected"]

        # 非 pass 集合（fail ∪ unknown，未观测 scope 排除）——与基准同一函数
        expected_nonpass = {
            "implicit": expected["also_expect"]["implicit_fail_targets"],
            "explicit": expected["also_expect"]["explicit_fail_targets"],
        }
        for line in compare_nonpass(report, expected_nonpass):
            mismatches.append("{0}: {1}".format(case["case_id"], line))

        # fail 集合逐 scope 精确核对（比非 pass 更严：确认没有"该 pass 却 unknown"的漂移）
        for scope in SCOPE_ORDER:
            declared = sorted(set(expected["also_expect"].get(
                "{0}_fail_targets".format(scope), [])))
            actual = observed_fail(report, scope)
            if actual is not None and actual != declared:
                mismatches.append("{0}: {1} fail {2} != 期望 {3}".format(
                    case["case_id"], scope, actual, declared))

        if report.grade != expected["grade"]:
            mismatches.append("{0}: grade {1} != 期望 {2}".format(
                case["case_id"], report.grade, expected["grade"]))

    assert not mismatches, "真值与引擎不一致（改引擎口径须同步改真值，不许凑）：\n" + "\n".join(mismatches)


def test_truth_index_lists_every_case_file():
    """索引与算例文件必须一一对应（防"加了文件忘了登记"的静默漏跑）。"""
    index = json.loads((DATA / "truth" / "index.json").read_text(encoding="utf-8"))
    listed = set(case["file"] for case in index["cases"])
    on_disk = set(p.name for p in (DATA / "truth").glob("case-*.json"))
    assert listed == on_disk, (
        "索引与算例文件不一致：仅索引 {0}；仅磁盘 {1}".format(
            sorted(listed - on_disk), sorted(on_disk - listed)))


def test_truth_covers_required_defect_enum():
    """真值库须覆盖 plan/05 §三.3 的全部缺陷注入类型（含边界情形）。"""
    index = json.loads((DATA / "truth" / "index.json").read_text(encoding="utf-8"))
    defects = set(case["injected"]["defect"] for case in index["cases"])
    required = {
        "correct", "missing_field", "wrong_position", "wrong_value",
        "bad_format", "metadata_stripped", "explicit_only",
    }
    missing = required - defects
    assert not missing, "真值库缺少缺陷类型：{0}".format(sorted(missing))


def test_samples_are_fully_fictional():
    """数据红线：合成样本不得出现真实平台/联系方式（只留结构与虚构指纹）。

    注意用**平台标识性 token**而非"字节/腾讯"等易与常用词撞车的短词：
    "字节"会命中正文的"逐字节一致"（假阳性），故用 "字节跳动" 这类完整标识。
    """
    forbidden = ("http://", "https://", "@", "微博", "微信", "抖音",
                 "字节跳动", "腾讯", "百度", "阿里巴巴")
    offenders = []
    for path in sorted((DATA / "samples").glob("*.json")) + sorted((DATA / "truth").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append("{0} 含 {1!r}".format(path.relative_to(ROOT).as_posix(), token))
    assert not offenders, "合成样本出现疑似真实来源痕迹：\n" + "\n".join(offenders)


# ------------------------------------------------------------------ 依据快照
#: 依据快照的最低完整性要求（文件 → 必须出现的锚点串）
SNAPSHOT_ANCHORS = {
    "labeling-measures/2025-09-01-fulltext.txt": (
        "第四条", "第五条", "第六条", "本办法自2025年9月1日起施行。"),
    "related-regulations/deep-synthesis-provisions.txt": (
        "第十六条", "第十七条", "本规定自2023年1月10日起施行。"),
    "related-regulations/generative-ai-interim-measures.txt": (
        "第十二条", "本办法自2023年8月15日起施行。"),
}


def test_knowledge_snapshots_exist_and_are_self_consistent():
    """依据快照必须存在、含关键条号，且带出处头（防止"截半页也算入库"）。"""
    root = DATA / "knowledge" / "raw"
    problems = []
    for rel, anchors in SNAPSHOT_ANCHORS.items():
        path = root / rel
        if not path.is_file():
            problems.append("缺失：{0}".format(rel))
            continue
        text = path.read_text(encoding="utf-8")
        if "来源：" not in text or "抓取日期：" not in text:
            problems.append("{0} 缺出处头（来源/抓取日期）".format(rel))
        for anchor in anchors:
            if anchor not in text:
                problems.append("{0} 缺锚点串 {1!r}".format(rel, anchor))
    assert not problems, "依据快照不完整：\n" + "\n".join(problems)


def test_gb_verification_record_has_metadata_and_no_full_text():
    """国标核对记录：须含书目元数据与逐页记录；**不得转载标准全文**（版权口径）。

    判定方式：记录文件中不得出现标准正文的长段落特征——此处以"不得出现正文连续长句"
    的强特征锚点近似（如"5.1 文本内容显式标识方法如下"这类正文小节句）。
    """
    path = (DATA / "knowledge" / "raw" / "gb45438-2025" / "2025-09-01-verification.md")
    assert path.is_file(), "国标核对记录缺失"
    text = path.read_text(encoding="utf-8")
    # 书目元数据必须在
    for anchor in ("GB 45438-2025", "2025-02-28", "2025-09-01",
                   "F32EA2A561F1886CD8D606513512D547", "附录 E"):
        assert anchor in text, "国标核对记录缺元数据/记录项：{0}".format(anchor)
    # 不得出现标准正文小节原句（防"顺手把全文贴进来"）
    for forbidden in ("文本内容显式标识方法如下", "文件元数据隐式标识方法如下",
                      "音频内容显式标识方法如下"):
        assert forbidden not in text, (
            "国标核对记录疑似转载标准正文（版权口径禁止）：{0}".format(forbidden))
