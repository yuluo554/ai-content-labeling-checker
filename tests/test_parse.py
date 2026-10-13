# -*- coding: utf-8 -*-
"""解析通路测试（容器结构解析 + AIGC 载荷抽取 + 显式降级）。

**为什么用真实容器字节**：解析器要处理的是字节结构（PNG 块 / JPEG 段 / ISO BMFF
box），用 JSON 描述"假装是图片"测不到结构缺陷（截断、CRC 错位、块类型误判）。
故本文件用 ``tools/gen_parse.py`` 的同一套构造器**现造字节**（不读磁盘仓库数据，
保证用例自足），既测正向也测**降级路径**。

**降级纪律（plan/02 §二.1 硬要求）**：解析不到/结构坏 → 显式降级为"未观测"，
引擎判 ``unknown``；绝不臆测成合规或违规。本文件逐条锁死这些路径。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from gen_parse import (  # noqa: E402
    PNG_KEYWORD, aigc_json, jpeg_bytes, mp4_bytes, png_bytes,
)

from labelcheck.parse import parse_bytes  # noqa: E402

WRAPPER = "AIGC"


# ------------------------------------------------------------------ 容器识别
def test_detect_png_jpeg_iso():
    from labelcheck.parse.containers import (
        CONTAINER_ISO, CONTAINER_JPEG, CONTAINER_PNG, detect_container,
    )
    assert detect_container(png_bytes([])) == CONTAINER_PNG
    assert detect_container(jpeg_bytes([])) == CONTAINER_JPEG
    assert detect_container(mp4_bytes([])) == CONTAINER_ISO
    assert detect_container(b"not a container") is None
    assert detect_container(b"") is None


def test_suffix_mapping_covers_declared_carriers():
    from labelcheck.parse import container_for_path
    assert container_for_path("a.png") == "png"
    assert container_for_path("a.JPG") == "jpeg"
    assert container_for_path("a.mp4") == "iso-bmff"
    assert container_for_path("a.m4a") == "iso-bmff"
    assert container_for_path("a.txt") is None


def test_iso_carrier_audio_vs_video():
    from labelcheck.parse.containers import iso_carrier
    assert iso_carrier(mp4_bytes([], brand=b"M4A ")) == "audio"
    assert iso_carrier(mp4_bytes([], brand=b"M4B ")) == "audio"
    assert iso_carrier(mp4_bytes([], brand=b"isom")) == "video"


# ------------------------------------------------------------------ 载荷抽取
def test_png_text_extracts_aigc_fields():
    data = png_bytes([("tEXt", PNG_KEYWORD, aigc_json())])
    out = parse_bytes(data, "png", WRAPPER)
    assert out.implicit_observed
    assert out.card.implicit["Label"] == "1"
    assert out.card.implicit["ContentProducer"] == "SYN-0001"
    assert out.aigc_field_count == 3
    assert out.payload_count == 1


def test_png_ztxt_compressed_payload():
    data = png_bytes([("zTXt", PNG_KEYWORD, aigc_json())])
    out = parse_bytes(data, "png", WRAPPER)
    assert out.implicit_observed
    assert out.card.implicit["ProduceID"]


def test_png_itxt_payload():
    data = png_bytes([("iTXt", PNG_KEYWORD, aigc_json())])
    out = parse_bytes(data, "png", WRAPPER)
    assert out.implicit_observed
    assert out.card.implicit["Label"] == "1"


def test_jpeg_app1_payload():
    data = jpeg_bytes([aigc_json()])
    out = parse_bytes(data, "jpeg", WRAPPER)
    assert out.implicit_observed
    assert out.card.carrier == "image"
    assert out.card.implicit["ContentProducer"] == "SYN-0001"


def test_mp4_moov_payload_and_carrier():
    data = mp4_bytes([aigc_json()])
    out = parse_bytes(data, "iso-bmff", WRAPPER)
    assert out.implicit_observed
    assert out.card.carrier == "video"
    assert out.card.implicit["ProduceID"]


def test_payload_with_prefix_and_suffix_text():
    """元数据块里 JSON 前后有其它文本（真实元数据常态）也要能取到。"""
    blob = "prefix noise {\"Other\":1} " + aigc_json() + " trailing"
    data = png_bytes([("tEXt", PNG_KEYWORD, blob)])
    out = parse_bytes(data, "png", WRAPPER)
    assert out.implicit_observed
    assert out.card.implicit["Label"] == "1"


# ------------------------------------------------------------------ 显式降级
def test_no_aigc_payload_is_observed_but_empty():
    """结构完整但无 AIGC 载荷 → 隐式**已观测**（确实没有），字段全缺。"""
    data = png_bytes([("tEXt", "Comment", "nothing to see")])
    out = parse_bytes(data, "png", WRAPPER)
    assert out.implicit_observed, "元数据区已被检查，应记为已观测"
    assert out.card.implicit == {}
    assert "no_aigc_payload" in out.reasons


def test_truncated_png_is_unobserved():
    """结构截断 → 未观测（不臆测"没有标识"）。"""
    data = png_bytes([("tEXt", PNG_KEYWORD, aigc_json())])[:-12]
    out = parse_bytes(data, "png", WRAPPER)
    assert not out.implicit_observed
    assert "structure_broken" in out.reasons


def test_truncated_jpeg_is_unobserved():
    """段内截断（元数据段没读完）→ 未观测。

    注意：截到 SOS 之后**不算**结构坏——所有 APPn 段都在 SOS 之前，读到 SOS 即证明
    元数据区已完整覆盖（尾部压缩数据被截不影响"标识是否存在"的结论）。
    """
    data = jpeg_bytes([aigc_json()])[:6]  # 砍进 APP1 段内
    out = parse_bytes(data, "jpeg", WRAPPER)
    assert not out.implicit_observed
    assert "structure_broken" in out.reasons


def test_jpeg_reaching_sos_is_observed_even_if_tail_cut():
    """读到 SOS 即视为元数据区已覆盖（APPn 全在 SOS 之前）。"""
    data = jpeg_bytes([aigc_json()])[:-4]  # 尾部（压缩数据/EOI）被截
    out = parse_bytes(data, "jpeg", WRAPPER)
    assert out.implicit_observed
    assert out.card.implicit["Label"] == "1"


def test_truncated_mp4_is_unobserved():
    data = mp4_bytes([aigc_json()])[:-4]
    out = parse_bytes(data, "iso-bmff", WRAPPER)
    assert not out.implicit_observed
    assert "structure_broken" in out.reasons


def test_explicit_scope_always_unobserved():
    """显式标识是渲染后画面/语音上的文字——文件解析器永远看不到。"""
    out = parse_bytes(png_bytes([("tEXt", PNG_KEYWORD, aigc_json())]), "png", WRAPPER)
    assert out.explicit_observed is False
    assert out.card.observed["explicit"] is False
    assert out.card.explicit == []


def test_missing_wrapper_config_is_unobserved():
    """映射表未配置解析画像 → 无法识别载荷形态 → 未观测（不猜）。"""
    out = parse_bytes(png_bytes([("tEXt", PNG_KEYWORD, aigc_json())]), "png", "")
    assert not out.implicit_observed
    assert "no_payload_wrapper_configured" in out.reasons


def test_unsupported_container_via_file(tmp_path):
    from labelcheck.parse import REASON_UNKNOWN_CONTAINER, parse_file
    path = tmp_path / "notes.txt"
    path.write_bytes(b"just plain text")
    out = parse_file(path, WRAPPER)
    assert not out.implicit_observed
    assert not out.explicit_observed
    assert out.fully_unobserved
    assert REASON_UNKNOWN_CONTAINER in out.reasons


def test_parse_file_missing_raises():
    from labelcheck.errors import EnvironmentError_
    from labelcheck.parse import parse_file
    with pytest.raises(EnvironmentError_):
        parse_file("definitely-not-here.png", WRAPPER)


# ------------------------------------------------------------------ 确定性
def test_parse_is_deterministic_and_hash_derived_id():
    data = png_bytes([("tEXt", PNG_KEYWORD, aigc_json())])
    a = parse_bytes(data, "png", WRAPPER)
    b = parse_bytes(data, "png", WRAPPER)
    assert a.card.card_id == b.card.card_id
    assert a.card.card_id.startswith("PARSED-")
    assert a.card.content_sha256 == b.card.content_sha256
    # 不同字节 → 不同 id
    other = parse_bytes(png_bytes([("tEXt", PNG_KEYWORD, aigc_json(label="2"))]), "png", WRAPPER)
    assert other.card.card_id != a.card.card_id


def test_parse_does_not_use_clock_or_random():
    """确定性纪律：解析产物的 card_id/指纹只依赖字节内容。"""
    data = png_bytes([("tEXt", PNG_KEYWORD, aigc_json())])
    first = parse_bytes(data, "png", WRAPPER).card.to_dict()
    second = parse_bytes(data, "png", WRAPPER).card.to_dict()
    assert first == second


# ------------------------------------------------------------------ 重复保留（§6.1 c)）
def test_two_payloads_mark_duplicate_keys():
    data = png_bytes([
        ("tEXt", PNG_KEYWORD, aigc_json()),
        ("tEXt", "AIGC", aigc_json()),
    ])
    out = parse_bytes(data, "png", WRAPPER)
    assert out.payload_count == 2
    assert out.card.implicit_duplicate_keys, "两份载荷应登记重复键"
