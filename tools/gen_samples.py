# -*- coding: utf-8 -*-
"""合成样本与真值库生成器（确定性，冻结产物）。

产物：

- ``data/truth/index.json``      —— 算例索引（固定 seed + 算例声明序）
- ``data/truth/case-<id>.json``  —— 每例 ``{input_card, expected}``
- ``data/samples/card-*.json``   —— 演示用示例标识卡（README 快速开始；同样由本脚本刷新，
  避免手工编辑引入 CR）

**确定性纪律（plan/05 §三.1，硬要求）**：

- 禁 stdlib ``random`` → 使用 :class:`labelcheck.rng.SplitMix64`；
- 禁 set 迭代序（一律 list + 显式顺序）；
- 禁系统时钟进产物（时间字段一律由参数传入或省略）；
- LF 落盘（``open(..., newline="\\n")``）→ 任意机器重生成**逐字节一致**
  （守门测试 ``tests/test_generators.py``）。

**真值语义（plan/05 §三.2）**：每例输出 ``expected``，声明主期望 ``grade`` 与
``also_expect``（同一注入隐含的其余结论目标集）。评测按 **``expected`` 声明的非 pass 集合**
与引擎输出的非 pass 集合比对；**不许改真值凑引擎**。

**数据纪律（红线，plan/05 §三.4）**：样本全部虚构——服务提供者编码用 ``SYN-*``、
内容编号用 ``SYN-C*``，禁止真实平台/真实用户/真实商业内容。

用法::

    py -X utf8 tools/gen_samples.py            # 就地重生成
    py -X utf8 tools/gen_samples.py --check    # 校验与已入库产物字节一致
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from labelcheck.jsonio import canonical_json, sha256_text, write_json  # noqa: E402
from labelcheck.rng import SplitMix64, derive_seed  # noqa: E402

#: 主种子（固定常量 → 产物可复现；改它 = 换一批样本，须同步重跑基准）
MASTER_SEED = 45438

#: 显式标识要素：文本/图片/音频/视频各一（目标 id 与规则库 target 一致）
ELEMENT_BY_CARRIER = {
    "text": "text_explicit_notice",
    "image": "image_explicit_notice",
    "audio": "audio_explicit_notice",
    "video": "video_explicit_notice",
}

#: 合规的显式提示文案（含"人工智能"与"生成/合成"两要素，满足 §5.x b)）
NOTICE_TEXT_OK = "本内容由人工智能生成合成"
#: 缺"人工智能/AI"要素的文案（触发人工智能要素 pattern 规则 fail）
NOTICE_TEXT_NO_AI = "本内容为合成作品"

#: 位置取值（与规则库 position 规则 allowed 对齐；越界值用于注入 wrong_position）
POSITION_OK = {"text": "head", "image": "corner", "audio": "head", "video": "head"}
POSITION_BAD = "middle-of-nowhere"
#: 图片位置越界值（图片 allowed 仅 edge/corner）
POSITION_BAD_IMAGE = "middle"

#: 容器键（GB 45438-2025 §6.1 + 附录 E 规定的键名；用带 AIGC 前缀形式）
KEY_PROPERTY = "AIGC:Label"
KEY_PRODUCER = "AIGC:ContentProducer"
KEY_CONTENT_ID = "AIGC:ProduceID"

#: 虚构服务提供者编码池（明显虚构，禁真实平台）——由种子确定性选取
PROVIDER_POOL = ("SYN-0001", "SYN-0002", "SYN-0003", "SYN-0004")


# --------------------------------------------------------------------- 工具
def _content_sha256(case_id):
    """由算例 id 确定性地派生内容指纹（64 位小写 hex）。"""
    return sha256_text("synthetic-content::{0}".format(case_id))


def _provider_code(master_seed, case_id):
    """由种子确定性选取虚构服务提供者编码。"""
    rng = SplitMix64(derive_seed(master_seed, "provider", case_id))
    return PROVIDER_POOL[rng.randbelow(len(PROVIDER_POOL))]


def _content_id(master_seed, case_id):
    """由种子确定性派生内容制作编号（SNY 前缀 + 6 位序号）。"""
    rng = SplitMix64(derive_seed(master_seed, "content-id", case_id))
    return "SYN-C{0:06d}".format(rng.randbelow(1000000))


def _explicit(carrier, present=True, position=None, value=None, element=None):
    item = {"element": element or ELEMENT_BY_CARRIER[carrier], "present": present}
    if present and position is not None:
        item["position"] = position
    if present and value is not None:
        item["value"] = value
    return item


def _implicit(property_value=None, producer=None, content_id=None):
    """按给定取值组装隐式字段字典（None = 该字段缺失）。"""
    data = {}
    if property_value is not None:
        data[KEY_PROPERTY] = property_value
    if producer is not None:
        data[KEY_PRODUCER] = producer
    if content_id is not None:
        data[KEY_CONTENT_ID] = content_id
    return data


def _card(case_id, carrier, explicit, implicit, notes, source="synthetic"):
    return {
        "card_id": case_id,
        "carrier": carrier,
        "source": source,
        "content_sha256": _content_sha256(case_id),
        "explicit": explicit,
        "implicit": implicit,
        "notes": notes,
    }


# --------------------------------------------------------------------- 算例
def _cases(master_seed):
    """返回算例列表（顺序 = 声明序，确定性）。

    每例：``(case_id, carrier, explicit, implicit, expected, injected, notes)``
    缺陷枚举覆盖 plan/05 §三.3 全部 7 类，另加图片位置越界一例。
    """
    provider = _provider_code(master_seed, "base")
    cid = _content_id(master_seed, "base")
    cases = []

    # ---- 1) correct：显式 + 隐式全部合规 → compliant
    cases.append((
        "SYN-TEXT-0001", "text",
        [_explicit("text", True, POSITION_OK["text"], NOTICE_TEXT_OK)],
        _implicit("1", provider, cid),
        {"grade": "compliant",
         "also_expect": {"implicit_fail_targets": [], "explicit_fail_targets": []}},
        {"defect": "correct", "field": None},
        "全要素齐备：文本显式标识位于起始位置，隐式标识三要素完整（内容完全虚构）",
    ))

    # ---- 2) missing_field：缺隐式属性信息（critical）→ non_compliant
    cases.append((
        "SYN-TEXT-0002", "text",
        [_explicit("text", True, POSITION_OK["text"], NOTICE_TEXT_OK)],
        _implicit(None, provider, cid),
        {"grade": "non_compliant",
         "also_expect": {"implicit_fail_targets": ["content_property"], "explicit_fail_targets": []}},
        {"defect": "missing_field", "field": "content_property"},
        "注入：隐式标识缺“生成合成标签要素”（属性信息），critical 级缺失（内容完全虚构）",
    ))

    # ---- 3) wrong_position：显式要素位置不在允许集 → partial
    cases.append((
        "SYN-TEXT-0003", "text",
        [_explicit("text", True, POSITION_BAD, NOTICE_TEXT_OK)],
        _implicit("1", provider, cid),
        {"grade": "partial",
         "also_expect": {"implicit_fail_targets": [], "explicit_fail_targets": ["text_explicit_notice"]}},
        {"defect": "wrong_position", "field": "text_explicit_notice"},
        "注入：文本显式标识位置越界（仅 minor 级位置规则 fail）（内容完全虚构）",
    ))

    # ---- 4) wrong_value：隐式取值不在枚举 → partial
    cases.append((
        "SYN-TEXT-0004", "text",
        [_explicit("text", True, POSITION_OK["text"], NOTICE_TEXT_OK)],
        _implicit("9", provider, cid),
        {"grade": "partial",
         "also_expect": {"implicit_fail_targets": ["content_property"], "explicit_fail_targets": []}},
        {"defect": "wrong_value", "field": "content_property"},
        "注入：生成合成标签取值 9（附录 E 允许 1/2/3），minor 级枚举规则 fail（内容完全虚构）",
    ))

    # ---- 5) bad_format：隐式字段类型不符 → partial
    cases.append((
        "SYN-TEXT-0005", "text",
        [_explicit("text", True, POSITION_OK["text"], NOTICE_TEXT_OK)],
        _implicit("1", 12345, cid),
        {"grade": "partial",
         "also_expect": {"implicit_fail_targets": ["content_producer"], "explicit_fail_targets": []}},
        {"defect": "bad_format", "field": "content_producer"},
        "注入：服务提供者要素写成整数（附录 E 要求字符串），minor 级类型规则 fail（内容完全虚构）",
    ))

    # ---- 6) metadata_stripped：元数据被剥离、显式齐全（01 §三.3 边界情形）→ non_compliant
    cases.append((
        "SYN-IMAGE-0006", "image",
        [_explicit("image", True, POSITION_OK["image"], NOTICE_TEXT_OK)],
        _implicit(None, None, None),
        {"grade": "non_compliant",
         "also_expect": {
             "implicit_fail_targets": ["content_property", "content_producer", "content_id"],
             "explicit_fail_targets": []}},
        {"defect": "metadata_stripped", "field": None},
        "边界情形：元数据被整体剥离但显式标识齐备——隐式含 critical 缺失 → non_compliant；显式仍全 pass（内容完全虚构）",
    ))

    # ---- 7) explicit_only：显式齐全、隐式仅缺一项 minor 要素 → partial
    cases.append((
        "SYN-TEXT-0007", "text",
        [_explicit("text", True, POSITION_OK["text"], NOTICE_TEXT_OK)],
        _implicit("1", provider, None),
        {"grade": "partial",
         "also_expect": {"implicit_fail_targets": ["content_id"], "explicit_fail_targets": []}},
        {"defect": "explicit_only", "field": "content_id"},
        "注入：显式齐全，隐式仅缺“内容制作编号”（minor）→ partial（内容完全虚构）",
    ))

    # ---- 8) 追加：图片位置越界（图片 allowed = edge/corner）→ partial
    cases.append((
        "SYN-IMAGE-0008", "image",
        [_explicit("image", True, POSITION_BAD_IMAGE, NOTICE_TEXT_OK)],
        _implicit("1", provider, cid),
        {"grade": "partial",
         "also_expect": {"implicit_fail_targets": [], "explicit_fail_targets": ["image_explicit_notice"]}},
        {"defect": "wrong_position", "field": "image_explicit_notice"},
        "注入：图片显式标识位置为“中间”（allowed 仅 edge/corner）→ partial（内容完全虚构）",
    ))

    return cases


def build_truth(master_seed=MASTER_SEED):
    """返回 ``[(case_id, 载荷 dict), …]``（顺序 = 算例声明序）。"""
    out = []
    for case_id, carrier, explicit, implicit, expected, injected, notes in _cases(master_seed):
        card = _card(case_id, carrier, explicit, implicit, notes)
        expected = dict(expected)
        expected["injected"] = dict(injected)
        out.append((case_id, {"input_card": card, "expected": expected}))
    return out


def build_index(master_seed=MASTER_SEED):
    """算例索引（含 seed，便于复现）。"""
    cases = []
    for case_id, payload in build_truth(master_seed):
        cases.append({
            "case_id": case_id,
            "carrier": payload["input_card"]["carrier"],
            "file": "case-{0}.json".format(case_id.lower()),
            "injected": dict(payload["expected"]["injected"]),
            "expected_grade": payload["expected"]["grade"],
        })
    return {
        "schema_version": 1,
        "_comment": (
            "合成样本算例索引（冻结产物，由 tools/gen_samples.py 生成，禁手改）。"
            "内容全部虚构；seed 固定 → 重生成逐字节一致。"
        ),
        "seed": master_seed,
        "cases": cases,
    }


def build_demo_cards(master_seed=MASTER_SEED):
    """README 快速开始用的两张演示标识卡（同样由种子确定性构造）。"""
    provider = _provider_code(master_seed, "base")
    cid = _content_id(master_seed, "base")

    text_card = _card(
        "SAMPLE-TEXT-0001", "text",
        [_explicit("text", True, POSITION_OK["text"], NOTICE_TEXT_OK)],
        _implicit("1", provider, cid),
        "全要素齐备的示例件：用于演示 check 通路与 README 快速开始（内容完全虚构）",
        source="manual",
    )
    image_card = _card(
        "SAMPLE-IMAGE-METADATA-STRIPPED-0002", "image",
        [_explicit("image", True, POSITION_OK["image"], NOTICE_TEXT_OK)],
        _implicit(None, None, None),
        "边界情形示例：元数据被剥离但显式标识在（plan/01 §三.3、plan/04 §六）。内容完全虚构",
    )
    return [
        ("samples/card-text-basic.json", text_card),
        ("samples/card-image-metadata-stripped.json", image_card),
    ]


# --------------------------------------------------------------------- 落盘
def artifacts(master_seed=MASTER_SEED):
    """``[(相对路径, 载荷), …]``（相对 ``data/``；生成与校验共用）。"""
    items = [("truth/index.json", build_index(master_seed))]
    for case_id, payload in build_truth(master_seed):
        items.append(("truth/case-{0}.json".format(case_id.lower()), payload))
    items.extend(build_demo_cards(master_seed))
    return items


def _render(payload):
    text = canonical_json(payload, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def write_all(data_dir, verbose=True):
    data_dir = Path(data_dir)
    for rel, payload in artifacts():
        path = data_dir / rel
        write_json(path, payload)
        if verbose:
            print("写入 {0}".format(path))
    return 0


def check_all(data_dir, verbose=True):
    data_dir = Path(data_dir)
    problems = []
    for rel, payload in artifacts():
        path = data_dir / rel
        if not path.is_file():
            problems.append("缺失：{0}".format(rel))
            continue
        if path.read_bytes() != _render(payload):
            problems.append("字节不一致：{0}".format(rel))
        elif verbose:
            print("一致 {0}".format(rel))
    if problems:
        sys.stderr.write("合成样本与生成器不一致：\n  " + "\n  ".join(problems) + "\n")
        return 1
    if verbose:
        print("合成样本全部与生成器一致")
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
