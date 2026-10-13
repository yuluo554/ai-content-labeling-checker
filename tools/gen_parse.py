# -*- coding: utf-8 -*-
"""解析通路算例生成器：确定性构造**真实容器字节** + 植入解析/核验真值（冻结产物）。

产物：``data/parse/fixtures.json``——每例含

- ``fixture_id`` / ``container`` / ``carrier``：算例坐标；
- ``bytes_b64``：容器文件字节的 base64（**真容器字节**，非 JSON 描述）；
- ``expected``：解析与核验的主期望（见下）。

**为什么用 base64 而不是二进制文件入仓**（数据纪律，plan/05 §三.4）：

- ``data/**`` 为**冻结文本资产**，全仓 EOL 门（``test_guard_data.py``）要求零 CR；
  PNG/JPEG/MP4 的二进制里天然可能含 ``0x0D`` 字节，直接入仓会误触该门；
- base64 仍是**真实容器字节**（解码后逐字节喂给 ``labelcheck.parse``），
  解析通路被完整执行——"真实容器文件 → 解析 → 核验 → 对账"的链路不打折；
- 与"样本仅留结构与指纹"的口径一致（二进制不入仓，只留可复现的编码形态）。

**真值语义**：``expected`` 声明

- ``implicit_observed`` / ``explicit_observed``：解析器**据实**报告的可观测性；
- ``grade``：期望合规等级；
- ``implicit_fail_targets`` / ``explicit_fail_targets``：期望的非 ``pass`` 目标集；
- ``reasons``：期望出现的解析降级原因码（子集断言，顺序无关）。

**确定性纪律（plan/05 §三.1）**：纯 stdlib、无 RNG/时钟；容器字节由固定常量构造 →
重生成逐字节一致（``--check`` 守门）。

用法::

    py -X utf8 tools/gen_parse.py            # 就地重生成
    py -X utf8 tools/gen_parse.py --check    # 校验与已入库产物字节一致
"""

from __future__ import annotations

import base64
import json
import struct
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
TOOLS = REPO_ROOT / "tools"
for _path in (str(SRC), str(TOOLS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from labelcheck.jsonio import canonical_json, write_json  # noqa: E402
from gen_mapping import PARSE_PROFILE, SOURCE_URL  # noqa: E402

#: 外层包裹键（附录 E b)）——从映射表生成器取，**单一事实源**（不在此处另写一份）
WRAPPER = PARSE_PROFILE["payload_wrapper"]

VERIFIED_AT = "2026-10-13"

#: 虚构服务提供者/编号（数据红线：全部虚构，禁真实平台）
PRODUCER_OK = "SYN-0001"
CONTENT_ID_OK = "SYN-C120797"


# ------------------------------------------------------------------ 容器字节构造
def _png_chunk(chunk_type, payload):
    crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def png_bytes(text_chunks):
    """构造最小合法 PNG（1×1 灰度）；``text_chunks`` 为 ``[(kind, keyword, text)]``。"""
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    out += _png_chunk(b"IHDR", ihdr)
    for kind, keyword, text in text_chunks:
        key = keyword.encode("utf-8")
        body = text.encode("utf-8")
        if kind == "tEXt":
            out += _png_chunk(b"tEXt", key + b"\x00" + body)
        elif kind == "zTXt":
            out += _png_chunk(b"zTXt", key + b"\x00" + b"\x00" + zlib.compress(body))
        elif kind == "iTXt":
            payload = key + b"\x00" + b"\x00" + b"\x00" + b"\x00" + b"\x00" + body
            out += _png_chunk(b"iTXt", payload)
        else:
            raise ValueError("未知 PNG 文本块：{0}".format(kind))
    out += _png_chunk(b"IEND", b"")
    return bytes(out)


def jpeg_bytes(segment_texts, marker=0xE1):
    """构造最小合法 JPEG（SOI + 若干 APP 段 + SOS + EOI）。"""
    out = bytearray(b"\xff\xd8")
    for text in segment_texts:
        payload = text.encode("utf-8")
        out += bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload
    out += b"\xff\xda" + struct.pack(">H", 2)  # SOS（最短合法段）
    out += b"\xff\xd9"  # EOI
    return bytes(out)


def _iso_box(box_type, payload):
    return struct.pack(">I", len(payload) + 8) + box_type + payload


def mp4_bytes(moov_payloads, brand=b"isom"):
    """构造最小 ISO BMFF：ftyp + moov（payload 内嵌文本，供解析器扫描）。"""
    out = bytearray()
    out += _iso_box(b"ftyp", brand + struct.pack(">I", 0) + brand)
    for payload in moov_payloads:
        out += _iso_box(b"moov", payload.encode("utf-8"))
    return bytes(out)


# ------------------------------------------------------------------ 载荷构造
def aigc_json(label="1", producer=PRODUCER_OK, content_id=CONTENT_ID_OK,
              reserved=None, propagator=None, propagate_id=None, extra=None):
    """构造 AIGC JSON 载荷（附录 E b) 的两层结构；``None`` = 该要素缺省。"""
    block = {}
    for key, value in (
        ("Label", label),
        ("ContentProducer", producer),
        ("ProduceID", content_id),
        ("ReservedCode1", reserved),
        ("ContentPropagator", propagator),
        ("PropagateID", propagate_id),
    ):
        if value is not None:
            block[key] = value
    if extra:
        for key, value in extra:
            block[key] = value
    return json.dumps({WRAPPER: block}, ensure_ascii=False, separators=(",", ":"))


#: PNG tEXt 的常见关键词形态（解析器不看关键词，只看块内 JSON；此处模拟真实写法）
PNG_KEYWORD = "XML:com.adobe.xmp"


def _png_with(payload, keyword=PNG_KEYWORD, kind="tEXt"):
    return png_bytes([(kind, keyword, payload)])


# ------------------------------------------------------------------ 算例清单
def cases():
    """返回解析通路算例列表（顺序 = 声明序，确定性）。"""
    items = []

    # 1) 图片元数据齐备 → 隐式全 pass；显式未观测 → 该 scope 无 fail
    items.append({
        "fixture_id": "PARSE-PNG-0001",
        "container": "png",
        "carrier": "image",
        "bytes": _png_with(aigc_json()),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "partial",           # 无 fail，但显式作用域未知 → 待人工确认
            "implicit_fail_targets": [],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "correct", "field": None},
        "notes": "PNG 元数据含完整 AIGC 载荷；显式标识解析器不可见（渲染后画面）→ 显式 unknown",
    })

    # 2) JPEG（APP1 段）齐备 → 同上
    items.append({
        "fixture_id": "PARSE-JPEG-0002",
        "container": "jpeg",
        "carrier": "image",
        "bytes": jpeg_bytes([aigc_json()]),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "partial",
            "implicit_fail_targets": [],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "correct", "field": None},
        "notes": "JPEG APP1 段含完整 AIGC 载荷；显式作用域未观测",
    })

    # 3) 缺生成合成标签要素 → non_compliant（critical 缺失）
    items.append({
        "fixture_id": "PARSE-PNG-0003",
        "container": "png",
        "carrier": "image",
        "bytes": _png_with(aigc_json(label=None)),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "non_compliant",
            "implicit_fail_targets": ["content_property"],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "missing_field", "field": "content_property"},
        "notes": "缺 Label（生成合成标签要素），critical 级缺失 → non_compliant",
    })

    # 4) 标签取值越界（应为 1/2/3）→ partial（minor 枚举）
    items.append({
        "fixture_id": "PARSE-PNG-0004",
        "container": "png",
        "carrier": "image",
        "bytes": _png_with(aigc_json(label="9")),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "partial",
            "implicit_fail_targets": ["content_property"],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "wrong_value", "field": "content_property"},
        "notes": "Label 取值 9（附录 E 允许 1/2/3），minor 级枚举 fail → partial",
    })

    # 5) 服务提供者要素类型不符（数值而非字符串）→ partial（minor 类型）
    items.append({
        "fixture_id": "PARSE-JPEG-0005",
        "container": "jpeg",
        "carrier": "image",
        "bytes": jpeg_bytes([aigc_json(producer=12345)]),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "partial",
            "implicit_fail_targets": ["content_producer"],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "bad_format", "field": "content_producer"},
        "notes": "服务提供者要素写成整数（附录 E 要求字符串）→ minor 类型 fail → partial",
    })

    # 6) 同一要素经两个容器键同时提供 → 隐式标识重复保留（§6.1 c)）→ non_compliant
    duplicate = json.dumps({
        WRAPPER: {
            "Label": "1",
            "AIGC.Label": "1",       # 同一要素的第二个别名键 → 重复提供
            "ContentProducer": PRODUCER_OK,
            "ProduceID": CONTENT_ID_OK,
        },
    }, ensure_ascii=False, separators=(",", ":"))
    items.append({
        "fixture_id": "PARSE-PNG-0006",
        "container": "png",
        "carrier": "image",
        "bytes": _png_with(duplicate),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "non_compliant",
            "implicit_fail_targets": ["content_property"],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "duplicate_label", "field": "content_property"},
        "notes": "同一要素经 Label 与 AIGC.Label 两个键提供 → §6.1 c) 唯一性 major fail → non_compliant",
    })

    # 7) 元数据整体剥离（结构完整但无 AIGC 载荷）→ 隐式已观测、字段全缺
    items.append({
        "fixture_id": "PARSE-PNG-0007",
        "container": "png",
        "carrier": "image",
        "bytes": png_bytes([("tEXt", "Comment", "no aigc payload here")]),
        "expected": {
            "implicit_observed": True,     # 元数据区**已被检查**，只是确实没有 AIGC 载荷
            "explicit_observed": False,
            "grade": "non_compliant",      # critical 要素确实缺失
            "implicit_fail_targets": ["content_property", "content_producer", "content_id"],
            "explicit_fail_targets": [],
            "reasons": ["no_aigc_payload"],
        },
        "injected": {"defect": "metadata_stripped", "field": None},
        "notes": "结构完整但无 AIGC 载荷：隐式标识确实缺失（不是'没检查'）→ 字段全 fail",
    })

    # 8) 容器结构截断 → 隐式作用域**未观测** → 全 unknown（不臆测）→ partial（待人工确认）
    truncated = _png_with(aigc_json())[:-12]  # 砍掉 IEND 尾巴 → 结构不完整
    items.append({
        "fixture_id": "PARSE-PNG-0008",
        "container": "png",
        "carrier": "image",
        "bytes": truncated,
        "expected": {
            "implicit_observed": False,
            "explicit_observed": False,
            # 两 scope 皆未观测 → 全部 unknown：无明确违规、也无任何"查过"的结论 → partial
            "grade": "partial",
            "implicit_fail_targets": [],
            "explicit_fail_targets": [],
            "reasons": ["structure_broken"],
        },
        "injected": {"defect": "structure_broken", "field": None},
        "notes": "PNG 截断：结构不可信 → 隐式未观测 → 全部 unknown、等级 partial（待人工确认）",
    })

    # 9) MP4 视频元数据（moov 内嵌载荷）齐备 → 同例 1
    items.append({
        "fixture_id": "PARSE-MP4-0009",
        "container": "iso-bmff",
        "carrier": "video",
        "bytes": mp4_bytes([aigc_json()]),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "partial",
            "implicit_fail_targets": [],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "correct", "field": None},
        "notes": "MP4（ISO BMFF）moov 内含完整 AIGC 载荷；显式作用域未观测",
    })

    # 10) M4A 音频（主品牌 M4A）→ 载体识别为 audio
    items.append({
        "fixture_id": "PARSE-M4A-0010",
        "container": "iso-bmff",
        "carrier": "audio",
        "bytes": mp4_bytes([aigc_json()], brand=b"M4A "),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "partial",
            "implicit_fail_targets": [],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "correct", "field": None},
        "notes": "M4A 主品牌 → 载体 audio；载荷齐备",
    })

    # 11) 载荷保留两份（两个 tEXt 块各含一份）→ §6.1 c) 重复 → non_compliant
    items.append({
        "fixture_id": "PARSE-PNG-0011",
        "container": "png",
        "carrier": "image",
        "bytes": png_bytes([
            ("tEXt", PNG_KEYWORD, aigc_json()),
            ("tEXt", "AIGC", aigc_json()),
        ]),
        "expected": {
            "implicit_observed": True,
            "explicit_observed": False,
            "grade": "non_compliant",
            "implicit_fail_targets": ["content_property"],
            "explicit_fail_targets": [],
            "reasons": [],
        },
        "injected": {"defect": "duplicate_label", "field": "content_property"},
        "notes": "两个元数据块各含一份 AIGC 载荷 → 隐式标识重复保留 → §6.1 c) major fail",
    })

    return items


def build_payload(seed_unused=None):
    """返回 ``data/parse/fixtures.json`` 载荷（顺序 = 算例声明序，确定性）。"""
    fixtures = []
    for item in cases():
        fixtures.append({
            "fixture_id": item["fixture_id"],
            "container": item["container"],
            "carrier": item["carrier"],
            "bytes_b64": base64.b64encode(item["bytes"]).decode("ascii"),
            "expected": item["expected"],
            "injected": item["injected"],
            "notes": item["notes"],
        })
    return {
        "schema_version": 1,
        "_comment": (
            "解析通路算例（冻结产物，由 tools/gen_parse.py 生成，禁手改）。"
            "bytes_b64 为**真实容器字节**（base64 编码以保持 data/** 为无 CR 文本资产）；"
            "内容全部虚构。"
        ),
        "source_url": SOURCE_URL,
        "verified_at": VERIFIED_AT,
        "wrapper": WRAPPER,
        "fixtures": fixtures,
    }


# --------------------------------------------------------------------- 落盘
def _rel_path():
    return "parse/fixtures.json"


def _render(payload):
    text = canonical_json(payload, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def write_all(data_dir, verbose=True):
    path = Path(data_dir) / _rel_path()
    write_json(path, build_payload())
    if verbose:
        print("写入 {0}".format(path))
    return 0


def check_all(data_dir, verbose=True):
    path = Path(data_dir) / _rel_path()
    if not path.is_file():
        sys.stderr.write("缺失：{0}\n".format(path))
        return 1
    expected = _render(build_payload())
    actual = path.read_bytes()
    if actual != expected:
        sys.stderr.write(
            "解析算例与生成器不一致：{0}（已入库 {1} 字节 vs 重生成 {2} 字节）\n".format(
                path, len(actual), len(expected)))
        return 1
    if verbose:
        print("一致 {0}".format(path))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir = REPO_ROOT / "data"
    if "--data-dir" in argv:
        data_dir = Path(argv[argv.index("--data-dir") + 1])
    if "--check" in argv:
        return check_all(data_dir)
    return write_all(data_dir)


if __name__ == "__main__":
    sys.exit(main())
