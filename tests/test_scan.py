# -*- coding: utf-8 -*-
"""批量扫描测试（FR-6 / NFR-8，契约见 plan/04 §七）。

锁死四件事：

1. **输入形态**：目录递归（含容器文件，不只 JSON）、清单文件、单文件；
2. **失败隔离**：坏 JSON / 非法卡 / 不可解析文件 / 超大容器 → 记 ``scan_error`` 后**继续**，
   整批不中断（NFR-8），失败件进 ``failed`` 清单；
3. **确定性**：相同输入两次扫描 ``to_dict`` 逐字节一致（件序 = 发现序，无时钟）；
4. **进度**：每 N 件一行到 **stderr**（``--quiet`` 关闭；stdout 不被污染）。
"""

import base64
import json
import sys
from pathlib import Path

import pytest

from labelcheck.errors import UsageError
from labelcheck.scan import (
    CODE_CONTAINER_TOO_LARGE, CODE_SCAN_ERROR, KIND_CARD, KIND_CONTAINER, KIND_FAILED,
    ScanResult, iter_input_paths, scan_paths, scan_target,
)

from _support import build_data_dir, make_card, make_mapping_field, make_rule

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


# ------------------------------------------------------------------ 夹具
@pytest.fixture
def cases(tmp_path):
    """扫描输入目录（与数据目录分开，避免把规则库 JSON 也扫进来）。"""
    path = tmp_path / "cases"
    path.mkdir()
    return path


@pytest.fixture
def data_dir(tmp_path):
    """一条生效隐式 presence 规则（缺字段 → fail），供扫描用例产生确定的违规件。"""
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


def _container_bytes():
    """取一条真实 PNG 容器字节（与解析通路回归同源，不新造一套）。"""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from gen_parse import aigc_json, png_bytes
    return png_bytes([("tEXt", "XML:com.adobe.xmp", aigc_json())])


# ------------------------------------------------------------------ 输入发现
def test_iter_input_paths_collects_json_and_containers(cases):
    _write_card(cases / "a.json")
    (cases / "img.png").write_bytes(_container_bytes())
    (cases / "note.md").write_text("not an input", encoding="utf-8")

    found = [p.name for p in iter_input_paths(cases)]
    assert "a.json" in found
    assert "img.png" in found, "目录扫描必须纳入容器文件（解析通路已成）"
    assert "note.md" not in found, "非输入后缀不得纳入"


def test_iter_input_paths_is_sorted_and_deterministic(cases):
    for name in ("c.json", "a.json", "b.json"):
        _write_card(cases / name)
    first = [p.name for p in iter_input_paths(cases)]
    second = [p.name for p in iter_input_paths(cases)]
    assert first == sorted(first) == ["a.json", "b.json", "c.json"]
    assert first == second


def test_iter_input_paths_reads_manifest(cases):
    _write_card(cases / "a.json")
    _write_card(cases / "b.json")
    manifest = cases / "list.txt"
    manifest.write_text("# comment\n\na.json\nb.json\n", encoding="utf-8")
    found = [p.name for p in iter_input_paths(manifest)]
    assert found == ["a.json", "b.json"]


def test_iter_input_paths_rejects_missing_target(tmp_path):
    with pytest.raises(UsageError):
        iter_input_paths(tmp_path / "nope")


# ------------------------------------------------------------------ 扫描主流程
def test_scan_directory_mixes_cards_and_containers(cases, data_dir):
    _write_card(cases / "good.json", implicit={"content.property": "AI"})
    _write_card(cases / "bad.json", implicit={})
    (cases / "img.png").write_bytes(_container_bytes())

    result = scan_target(cases, data_dir)
    assert len(result.items) == 3
    kinds = sorted(item.kind for item in result.items)
    assert KIND_CARD in kinds and KIND_CONTAINER in kinds
    assert result.summary["checked"] == 3
    assert result.summary["failed"] == 0


def test_scan_detects_violation_and_counts_summary(cases, data_dir):
    _write_card(cases / "good.json", implicit={"content.property": "AI"})
    _write_card(cases / "bad.json", implicit={})
    result = scan_target(cases, data_dir)
    assert result.summary["violations"] == 1
    assert len(result.violations) == 1
    assert result.violations[0].card_id == "SYN-TEST-0001"  # make_card 默认 id
    assert result.summary["grades"]["compliant"] == 1
    assert result.summary["grades"]["non_compliant"] == 1


# ------------------------------------------------------------------ 失败隔离（NFR-8）
def test_scan_isolates_failures_and_continues(cases, data_dir):
    """坏 JSON / 不可解析文件不得中断整批：该件记 scan_error，其余照常核验。

    用**清单**投喂（目录递归只收已知输入后缀——见 :data:`INPUT_SUFFIXES`）：
    清单可显式列出任意路径，正好覆盖"用户点名了一个坏件"这一形态。
    """
    _write_card(cases / "ok.json", implicit={"content.property": "AI"})
    (cases / "broken.json").write_text("{not json", encoding="utf-8")
    (cases / "unknown.bin").write_bytes(b"\x00\x01\x02not-a-container")
    (cases / "notes.txt").write_text("plain text", encoding="utf-8")
    manifest = cases / "list.lst"
    manifest.write_text("ok.json\nbroken.json\nunknown.bin\nnotes.txt\n", encoding="utf-8")

    result = scan_target(manifest, data_dir)
    # 4 件全部出现在结果里（一件不丢）
    assert len(result.items) == 4
    assert result.summary["checked"] == 1
    assert result.summary["failed"] == 3
    assert len(result.failed) == 3
    for item in result.failed:
        assert item.kind == KIND_FAILED
        assert item.code == CODE_SCAN_ERROR
        assert item.error
    # 成功件仍在（失败隔离未污染其余件）
    assert result.summary["grades"]["compliant"] == 1


def test_directory_scan_only_takes_known_suffixes(cases, data_dir):
    """目录递归只纳入已知输入后缀；未点名的不明文件不静默当成件。"""
    _write_card(cases / "ok.json", implicit={"content.property": "AI"})
    (cases / "notes.txt").write_text("plain text", encoding="utf-8")
    (cases / "unknown.bin").write_bytes(b"\x00\x01\x02")
    result = scan_target(cases, data_dir)
    assert len(result.items) == 1
    assert result.items[0].card_id == "SYN-TEST-0001"


def test_scan_isolates_invalid_card_fields(cases, data_dir):
    """非法标识卡（carrier 越界）也是单件失败，不中断整批。"""
    _write_card(cases / "bad-card.json", carrier="hologram")
    _write_card(cases / "ok.json", implicit={"content.property": "AI"})
    result = scan_target(cases, data_dir)
    assert result.summary["failed"] == 1
    assert result.summary["checked"] == 1


def test_scan_failed_item_is_unknown_not_fail(cases, data_dir):
    """失败件不得被当成"违规"——它是 unknown（不臆测）。"""
    (cases / "broken.json").write_text("{not json", encoding="utf-8")
    result = scan_target(cases, data_dir)
    item = result.items[0]
    assert item.failed
    assert not item.has_violation
    assert item.fail_targets == []
    assert result.summary["violations"] == 0


def test_scan_skips_oversized_container(cases, data_dir):
    """超大容器按安全阀跳过（container_too_large），不整体读入、不中断整批。"""
    (cases / "huge.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4096)
    result = scan_paths(
        [cases / "huge.png"], data_dir, root=str(cases),
        max_container_bytes=1024)
    item = result.items[0]
    assert item.failed
    assert item.code == CODE_CONTAINER_TOO_LARGE
    assert "上限" in item.error


# ------------------------------------------------------------------ 确定性
def test_scan_output_is_deterministic(cases, data_dir):
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    _write_card(cases / "b.json", implicit={})
    (cases / "img.png").write_bytes(_container_bytes())

    first = scan_target(cases, data_dir).to_dict()
    second = scan_target(cases, data_dir).to_dict()
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
        json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_scan_result_roundtrips_through_json(cases, data_dir):
    """ScanResult → JSON → from_dict → to_dict 稳定（两轮对账读上轮结果的通路）。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    result = scan_target(cases, data_dir)
    payload = result.to_dict()
    restored = ScanResult.from_dict(json.loads(json.dumps(payload)))
    assert restored.to_dict() == payload


# ------------------------------------------------------------------ 进度
def test_scan_progress_goes_to_stderr_not_stdout(cases, data_dir, capsys):
    for index in range(4):
        _write_card(cases / "c{0}.json".format(index),
                    implicit={"content.property": "AI"})
    paths = iter_input_paths(cases)
    scan_paths(paths, data_dir, progress_every=2, root=str(cases))
    captured = capsys.readouterr()
    assert captured.out == "", "进度不得污染 stdout（管道消费）"
    assert "扫描进度" in captured.err


def test_scan_quiet_suppresses_progress(cases, data_dir, capsys):
    for index in range(3):
        _write_card(cases / "c{0}.json".format(index),
                    implicit={"content.property": "AI"})
    scan_paths(iter_input_paths(cases), data_dir, progress_every=1,
               quiet=True, root=str(cases))
    captured = capsys.readouterr()
    assert "扫描进度" not in captured.err


# ------------------------------------------------------------------ 身份键（对账主键）
def test_card_identity_uses_card_id_not_path(cases, data_dir):
    """标识卡件身份 = ``card:<card_id>``（与文件名无关 → 改名不误判新增）。"""
    _write_card(cases / "one.json", card_id="CARD-A",
                implicit={"content.property": "AI"})
    result = scan_target(cases, data_dir)
    assert result.items[0].identity == "card:CARD-A"


def test_container_identity_uses_relative_path(cases, data_dir):
    """容器件身份 = ``file:<相对路径>``（解析件 card_id 由内容派生，不稳定）。"""
    (cases / "img.png").write_bytes(_container_bytes())
    result = scan_target(cases, data_dir)
    assert result.items[0].identity == "file:img.png"


def test_duplicate_card_ids_do_not_drop_items(cases, data_dir):
    """同一 card_id 出现两次：两件都保留（身份按发现序加序号，不丢件）。"""
    _write_card(cases / "a.json", card_id="SAME", implicit={"content.property": "AI"})
    _write_card(cases / "b.json", card_id="SAME", implicit={})
    result = scan_target(cases, data_dir)
    assert len(result.items) == 2
    identities = [item.identity for item in result.items]
    assert identities == ["card:SAME", "card:SAME#2"]


def test_scan_does_not_write_any_files(cases, data_dir):
    """扫描本身只产出内存结果（导出是 report 层的职责）。"""
    _write_card(cases / "a.json", implicit={"content.property": "AI"})
    before = set(p.name for p in cases.iterdir())
    scan_target(cases, data_dir)
    after = set(p.name for p in cases.iterdir())
    assert before == after