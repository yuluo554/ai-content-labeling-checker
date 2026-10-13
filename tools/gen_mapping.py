# -*- coding: utf-8 -*-
"""字段映射表生成器：GB 45438-2025 原文核对后的确定性产物。

产物 ``data/mapping/national-fields.json``（冻结，禁手改；确定性 = 无时间戳、LF、
字段/别名顺序 = 模板声明序 → 任意机器重生成逐字节一致）。

**M1 字段口径修正（重要）**：M0 骨架把隐式字段拆成 ``service_provider_name`` +
``service_provider_code`` 两个字段——**与标准原文不符**。GB 45438-2025 §6.1 a) 2) 与
规范性附录 E d) 定义为**单一要素**「生成合成服务提供者要素（ContentProducer）：名称
**或**编码」，故 M1 合并为 ``content_producer``。

**原文依据**：GB 45438-2025 §6.1（隐式标识要素清单）与规范性附录 E（文件元数据隐式
标识格式——AIGC 字段及其内部键名）。附录 E 规定的容器键名为 ``Label`` /
``ContentProducer`` / ``ProduceID`` / ``Propagator`` / ``PropagatorID``；标准同时要求
"字段名称或关键词中应包含 AIGC"，故别名同时给出带 ``AIGC`` 前缀的形式。

用法::

    py -X utf8 tools/gen_mapping.py           # 就地重生成
    py -X utf8 tools/gen_mapping.py --check   # 校验与已入库产物字节一致
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from labelcheck.jsonio import canonical_json, write_json  # noqa: E402

VERIFIED_AT = "2026-10-13"
SOURCE_URL = (
    "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=F32EA2A561F1886CD8D606513512D547"
)

#: 国标字段定义（顺序 = 声明序，决定归一命中优先级；别名顺序敏感，见 plan/04 §五.2）
#: aliases 排列纪律：先 "AIGC:Key"（含 AIGC 关键词，§E a) 要求），再点号形式，最后裸键名。
FIELDS = [
    {
        "national_field": "content_property",
        "label": "生成合成标签要素（内容的人工智能生成合成属性信息）",
        "aliases": ["AIGC:Label", "AIGC.Label", "aigc.label", "Label"],
        "status": "verified",
        "source_url": SOURCE_URL,
        "clause": {
            "article": "6.1 a) 1) / 附录 E c)",
            "excerpt": "生成合成标签要素由 Label 表示，取值 1=属于、2=可能为、3=疑似为人工智能生成合成内容，类型为字符串",
        },
    },
    {
        "national_field": "content_producer",
        "label": "生成合成服务提供者要素（名称或编码）",
        "aliases": [
            "AIGC:ContentProducer", "AIGC.ContentProducer",
            "aigc.contentproducer", "ContentProducer",
        ],
        "status": "verified",
        "source_url": SOURCE_URL,
        "clause": {
            "article": "6.1 a) 2) / 附录 E d)",
            "excerpt": "生成合成服务提供者要素由 ContentProducer 表示，存储服务提供者的名称或编码，类型为字符串",
        },
    },
    {
        "national_field": "content_id",
        "label": "内容制作编号要素",
        "aliases": [
            "AIGC:ProduceID", "AIGC.ProduceID", "aigc.produceid", "ProduceID",
        ],
        "status": "verified",
        "source_url": SOURCE_URL,
        "clause": {
            "article": "6.1 a) 3) / 附录 E e)",
            "excerpt": "内容制作编号要素由 ProduceID 表示，存储生成合成服务提供者对该内容的唯一编号，类型为字符串",
        },
    },
    {
        "national_field": "content_propagator",
        "label": "内容传播服务提供者要素（名称或编码）",
        # 附录 E（规范性）写作 ContentPropagator；附录 F（资料性）示例写作 Propagator。
        # 标准自身两处写法不一致，本项目两套键名同时登记，不擅自"二选一"。
        "aliases": [
            "AIGC:ContentPropagator", "AIGC.ContentPropagator",
            "aigc.contentpropagator", "ContentPropagator",
            "AIGC:Propagator", "AIGC.Propagator", "aigc.propagator", "Propagator",
        ],
        "status": "verified",
        "source_url": SOURCE_URL,
        "clause": {
            "article": "6.1 a) 4) / 附录 E g)",
            "excerpt": "内容传播服务提供者要素由 ContentPropagator（附录 F 示例作 Propagator）表示，存储内容传播服务提供者的名称或编码，类型为字符串",
        },
    },
    {
        "national_field": "propagate_id",
        "label": "内容传播编号要素",
        # 同上：附录 E 作 PropagateID，附录 F 示例作 PropagatorID，两套并登记。
        "aliases": [
            "AIGC:PropagateID", "AIGC.PropagateID", "aigc.propagateid", "PropagateID",
            "AIGC:PropagatorID", "AIGC.PropagatorID", "aigc.propagatorid", "PropagatorID",
        ],
        "status": "verified",
        "source_url": SOURCE_URL,
        "clause": {
            "article": "6.1 a) 5) / 附录 E h)",
            "excerpt": "内容传播编号要素由 PropagateID（附录 F 示例作 PropagatorID）表示，存储内容传播服务提供者对该内容的唯一编号，类型为字符串",
        },
    },
]

#: 容器画像（可选）：AIGC 扩展字段所在的元数据域
PROFILES = {
    "generic_metadata": [
        "AIGC:Label",
        "AIGC:ContentProducer",
        "AIGC:ProduceID",
        "AIGC:Propagator",
        "AIGC:PropagatorID",
    ],
}

#: 解析画像（M2）：文件元数据隐式标识 JSON 载荷的**外层包裹键**
#: （GB 45438-2025 附录 E b)：值为 JSON 串 ``{"AIGC":{"Label":...}}``）。
#: 放进数据文件而非代码常量——解析逻辑据此读数据，不在源码里硬编码政策键名。
PARSE_PROFILE = {
    "payload_wrapper": "AIGC",
    "source_clause": "附录 E b)",
}


def build_payload():
    """返回映射表载荷（顺序固定，确定性）。"""
    return {
        "schema_version": 1,
        "_comment": (
            "元数据字段映射表（冻结产物，由 tools/gen_mapping.py 生成，禁手改）。"
            "字段名/别名/类型以 GB 45438-2025 §6.1 与规范性附录 E 原文为准；"
            "aliases 顺序敏感（归一取声明序最先命中者）。核对日 2026-10-13。"
        ),
        "source_url": SOURCE_URL,
        "verified_at": VERIFIED_AT,
        "profiles": PROFILES,
        "parse_profile": PARSE_PROFILE,
        "fields": FIELDS,
    }


def _render(payload):
    text = canonical_json(payload, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def write_all(data_dir, verbose=True):
    path = Path(data_dir) / "mapping" / "national-fields.json"
    write_json(path, build_payload())
    if verbose:
        print("写入 {0}".format(path))
    return 0


def check_all(data_dir, verbose=True):
    path = Path(data_dir) / "mapping" / "national-fields.json"
    if not path.is_file():
        sys.stderr.write("缺失：{0}\n".format(path))
        return 1
    expected = _render(build_payload())
    actual = path.read_bytes()
    if actual != expected:
        sys.stderr.write(
            "映射表与生成器不一致：{0}（已入库 {1} 字节 vs 重生成 {2} 字节）\n".format(
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
