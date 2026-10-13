# -*- coding: utf-8 -*-
"""规则库生成器：确定性模板 → ``data/rules/<doc>/<ver>.json`` 冻结产物 + ``registry.json`` 指纹回填。

纪律（plan/05 §二/§三.1）：

- **禁手改产物**：``data/rules/**/*.json`` 一律由本脚本重生成；
- **确定性**：无时间戳、LF 落盘、条目顺序 = 模板声明序 → 任意机器重生成**逐字节一致**
  （守门测试 ``tests/test_generators.py``）；
- **指纹**：``registry.json`` 的 ``sha256`` 必须等于 ``labelcheck.rules.loader`` 加载同一文件时
  算出的规范化指纹（``sha256_text(canonical_json(data, indent=None, sort_keys=True))``），
  否则加载器会以 exit 3 拒绝（数据真伪门）。

**条文来源核对（M1 实测，2026-10-13）**：

- 《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号）——中国政府网全文快照，逐条条号已核；
- GB 45438-2025《网络安全技术 人工智能生成合成内容标识方法》——国家标准全文公开系统
  （openstd.samr.gov.cn，hcno=F32EA2A561F1886CD8D606513512D547）在线预览逐页核对，
  含规范性附录 E《文件元数据隐式标识格式》。

**判定路径归属（避免同一 target 跨文档重复判定）**：技术判定规则由 GB 45438-2025 承担
（条款精确、可机器判定）；《标识办法》条目记录法定义务与真实条号，保持 ``pending``
（其判定实现即 GB 规则，启用会造成同 target 双份 Finding）。

用法::

    py -X utf8 tools/gen_rulesets.py            # 就地重生成
    py -X utf8 tools/gen_rulesets.py --check    # 只校验：与已入库产物字节一致？（CI/守门用）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:  # 允许未安装时直接跑生成器
    sys.path.insert(0, str(SRC))

from labelcheck.jsonio import canonical_json, sha256_text, write_json  # noqa: E402

# --------------------------------------------------------------------- 出处坐标
#: 核对日期（确定性的常量，非系统时钟——产物必须无时间戳）
VERIFIED_AT = "2026-10-13"

#: GB 45438-2025 国家标准全文公开系统详情页（在线预览入口）
GB_SOURCE_URL = (
    "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=F32EA2A561F1886CD8D606513512D547"
)
#: 《标识办法》中国政府网全文（国信办通字〔2025〕2 号）
MEASURES_SOURCE_URL = "https://www.gov.cn/zhengce/zhengceku/202503/content_7014286.htm"

GB_DOC = {
    "doc_id": "gb45438-2025",
    "title": "网络安全技术 人工智能生成合成内容标识方法",
    "doc_number": "GB 45438-2025",
    "kind": "mandatory-standard",
    "issuer": "国家市场监督管理总局、国家标准化管理委员会",
    "effective_from": "2025-09-01",
    "status": "verified",
    "source_url": GB_SOURCE_URL,
    "note": "强制性国标；M1 已按在线预览逐页核对（条款 5.1–5.4、6.1、附录 E），条目全部 verified",
}

MEASURES_DOC = {
    "doc_id": "labeling-measures",
    "title": "人工智能生成合成内容标识办法",
    "doc_number": "国信办通字〔2025〕2 号",
    "kind": "measure",
    "issuer": "国家互联网信息办公室、工业和信息化部、公安部、国家广播电视总局",
    "effective_from": "2025-09-01",
    "status": "verified",
    "source_url": MEASURES_SOURCE_URL,
    "note": (
        "条号已按中国政府网全文核对（第四条–第六条）。M2：办法独有义务（第四条第二款导出文件、"
        "第六条传播平台提示）在适用性画像建立后转 verified；与国标同 target 的条目保持 pending，"
        "技术判定由 GB 45438-2025 承担，避免同一目标跨文档重复判定"
    ),
}

VERSION = "2025-09-01"

# M2 建条决策（缓议项的处置结论，完整理由见 plan/06 §一 D22/D23 与 §三 缓议项）：
# - 附录 E 的**预留字段** ReservedCode1/2：标准未定义语义与取值 → **不建规则**
#   （建"必须存在"会凭空发明义务）；
# - §5.x 的**数值量阈值**（字号/时长/语速等）：M1 逐页核对记录未覆盖任何数值量
#   → **不建规则**（在核对记录未覆盖处建条 = 编造标准内容，触碰"绝不编造数值"红线）；
#   日后若核对确认存在此类阈值，须先补核对记录（挂页码）再建条。
# - §6.1 c)「仅保留一份文件元数据隐式标识」：**已建规则**（M2 新增 unique 判定）。


# --------------------------------------------------------------------- GB 规则
def _explicit(rid, carrier, target, article, excerpt, check_type, params, severity):
    return {
        "rule_id": rid,
        "scope": "explicit",
        "carrier": [carrier],
        "target": target,
        "check_type": check_type,
        "params": params,
        "severity": severity,
        "only_if": {"carrier": [carrier]},
        "clause": {"article": article, "excerpt": excerpt},
        "status": "verified",
        "source_url": GB_SOURCE_URL,
        "verified_at": VERIFIED_AT,
    }


def _implicit(rid, target, article, excerpt, check_type, params, severity,
              status="verified", scenarios=None):
    """构造一条隐式规则。

    :param scenarios: ``only_if.scenario`` 的适用场景列表；``None``/空 = 全部场景适用。
        传播要素（§6.1 a) 4) 5)）只对 ``propagated`` 场景成立（办法第六条），
        由 M2 的**载体适用性画像**决定——这正是把这两条从 pending 转 verified 的
        唯一正当路径（先有适用性画像，再核对）。
    """
    only_if = {"scenario": list(scenarios)} if scenarios else {}
    return {
        "rule_id": rid,
        "scope": "implicit",
        "carrier": [],
        "target": target,
        "check_type": check_type,
        "params": params,
        "severity": severity,
        "only_if": only_if,
        "clause": {"article": article, "excerpt": excerpt},
        "status": status,
        "source_url": GB_SOURCE_URL,
        "verified_at": VERIFIED_AT if status == "verified" else None,
    }


#: 显式标识：存在性（FR-1）+ 位置/形式（FR-2）要求（GB 45438-2025 §5.1–5.4）
#: 位置枚举取值可溯：text/audio/video 为「起始/末尾/中间适当位置」（head/tail/middle）；
#: image 为「图片的边或角」（edge/corner，§5.2 c）。
PLACEMENT_EDGE_CORNER = ["edge", "corner"]
PLACEMENT_HEAD_TAIL_MIDDLE = ["head", "tail", "middle"]

_AI_ELEMENT = {"regex": ".*(人工智能|AI).*"}
_GEN_ELEMENT = {"regex": ".*(生成|合成).*"}


def _carrier_explicit_rules(carrier, element, position_article, position_excerpt,
                            position_allowed, presence_article, presence_excerpt,
                            ai_article, gen_article):
    """按载体生成 4 条显式规则（存在性 + 位置 + 人工智能要素 + 生成合成要素）。

    逐载体的条号/要点差异由调用处给出（**每一处都可溯到标准原文**）。
    """
    return [
        _explicit("gb45438:explicit:{0}.notice.presence".format(carrier), carrier, element,
                  presence_article, presence_excerpt, "presence", {}, "major"),
        _explicit("gb45438:explicit:{0}.notice.position".format(carrier), carrier, element,
                  position_article, position_excerpt, "position",
                  {"allowed": position_allowed}, "minor"),
        _explicit("gb45438:explicit:{0}.notice.ai_element".format(carrier), carrier, element,
                  ai_article, "{0}内容显式标识应含人工智能要素：包含“人工智能”或“AI”".format(_CARRIER_CN[carrier]),
                  "pattern", _AI_ELEMENT, "major"),
        _explicit("gb45438:explicit:{0}.notice.gen_element".format(carrier), carrier, element,
                  gen_article, "{0}内容显式标识应含生成合成要素：包含“生成”和/或“合成”".format(_CARRIER_CN[carrier]),
                  "pattern", _GEN_ELEMENT, "major"),
    ]


_CARRIER_CN = {"text": "文本", "image": "图片", "audio": "音频", "video": "视频"}

GB_EXPLICIT_RULES = (
    # ---- 文本（5.1）
    _carrier_explicit_rules(
        "text", "text_explicit_notice",
        "5.1 d)", "文本内容显式标识应位于文本的起始位置、末尾位置或中间适当位置之一或多个",
        PLACEMENT_HEAD_TAIL_MIDDLE,
        "5.1 a)", "文本内容显式标识应采用文字或角标形式并具备标识",
        "5.1 b) 1)", "5.1 b) 2)",
    )
    # ---- 图片（5.2）
    + _carrier_explicit_rules(
        "image", "image_explicit_notice",
        "5.2 c)", "图片内容显式标识应位于图片的边或角",
        PLACEMENT_EDGE_CORNER,
        "5.2 a)", "图片内容显式标识应采用文字提示并具备标识",
        "5.2 b) 1)", "5.2 b) 2)",
    )
    # ---- 音频（5.3）
    + _carrier_explicit_rules(
        "audio", "audio_explicit_notice",
        "5.3 d)", "音频内容显式标识应位于音频的起始位置、末尾位置或中间适当位置之一或多个",
        PLACEMENT_HEAD_TAIL_MIDDLE,
        "5.3 a)", "音频内容显式标识应采用语音标识或音频节奏标识并具备标识",
        "5.3 b) 1)", "5.3 b) 2)",
    )
    # ---- 视频（5.4）
    + _carrier_explicit_rules(
        "video", "video_explicit_notice",
        "5.4 c)", "视频内容显式标识应位于视频起始画面，可位于视频末尾和中间适当位置",
        PLACEMENT_HEAD_TAIL_MIDDLE,
        "5.4 a)", "视频内容显式标识应采用文字提示并具备标识",
        "5.4 b) 1)", "5.4 b) 2)",
    )
)

#: 隐式标识：文件元数据隐式标识要素（GB 45438-2025 §6.1 + 规范性附录 E）
#: 严重度分配依据：属性信息（Label）是"是否为 AI 生成合成"的根本标记 → critical；
#: 服务提供者要素为规章第五条明列的"制作要素" → major；制作编号为可补录要素 → minor。
#:
#: **M2 适用性画像（把 pending 转 verified 的唯一正当路径）**：
#: §6.1 a) 4) 5) 的传播要素只对"内容由传播服务发布/转发"成立（办法第六条），
#: 故以 ``only_if.scenario=[propagated]`` 门控后转 ``verified``——非传播场景下引擎记
#: ``skipped``（不适用），既不漏判也不冤枉。
#:
#: **M2 §6.1 c) 唯一性**：``unique`` 规则依"应仅保留一份文件元数据隐式标识"建条，
#: 覆盖整个隐式标识块（同一要素被多容器键/多份副本重复提供 → fail）。
PROPAGATED_ONLY = ["propagated"]

GB_IMPLICIT_RULES = [
    _implicit("gb45438:implicit:content_property.presence", "content_property",
              "6.1 a) 1)", "文件元数据隐式标识应包括生成合成标签要素：内容的人工智能生成合成属性信息",
              "presence", {}, "critical"),
    _implicit("gb45438:implicit:content_property.enum", "content_property",
              "附录 E c) 1)", "生成合成标签要素（Label）取值：1=属于、2=可能为、3=疑似为人工智能生成合成内容",
              "enum", {"allowed": ["1", "2", "3"]}, "minor"),
    _implicit("gb45438:implicit:content_producer.presence", "content_producer",
              "6.1 a) 2)", "文件元数据隐式标识应包括生成合成服务提供者要素：生成合成服务提供者的名称或编码",
              "presence", {}, "major"),
    _implicit("gb45438:implicit:content_producer.type", "content_producer",
              "附录 E d) 2)", "生成合成服务提供者要素（ContentProducer）类型为字符串",
              "type", {"expect": "string"}, "minor"),
    _implicit("gb45438:implicit:content_id.presence", "content_id",
              "6.1 a) 3)", "文件元数据隐式标识应包括内容制作编号要素：生成合成服务提供者对该内容的唯一编号",
              "presence", {}, "minor"),
    _implicit("gb45438:implicit:content_id.type", "content_id",
              "附录 E e) 2)", "内容制作编号要素（ProduceID）类型为字符串",
              "type", {"expect": "string"}, "minor"),
    # §6.1 c)：仅保留一份文件元数据隐式标识（M2 新增；隐式块上下文判定）
    _implicit("gb45438:implicit:implicit_label.uniqueness", "content_property",
              "6.1 c)", "文件元数据隐式标识应仅保留一份（同一标识要素不得重复提供）",
              "unique", {}, "major"),
    # 传播要素：M2 适用性画像 → 仅 propagated 场景适用，据此转 verified（办法第六条）
    _implicit("gb45438:implicit:content_propagator.presence", "content_propagator",
              "6.1 a) 4)", "文件元数据隐式标识应含内容传播服务提供者的名称或编码（传播场景适用）",
              "presence", {}, "major", scenarios=PROPAGATED_ONLY),
    _implicit("gb45438:implicit:propagate_id.presence", "propagate_id",
              "6.1 a) 5)", "文件元数据隐式标识应含内容传播服务提供者对该内容的唯一编号（传播场景适用）",
              "presence", {}, "minor", scenarios=PROPAGATED_ONLY),
]


# ---------------------------------------------------------------- 《标识办法》规则
def _measure(rid, scope, carrier, target, article, excerpt, check_type, params, severity,
             status="pending", scenarios=None):
    """构造一条《标识办法》规则。

    **判定路径归属**：与 GB 45438-2025 同 target 的条目保持 ``pending``（技术判定由
    国标承担，避免同一目标跨文档双份 Finding）；**办法独有**的义务（第四条第二款导出
    文件、第六条传播平台提示）在 M2 适用性画像建立后转 ``verified``——它们有独立
    target 与明确场景门控，不与国标重复。

    :param status: 默认 ``pending``（同源条目）；办法独有条目置 ``verified``。
    :param scenarios: ``only_if.scenario`` 的适用场景列表（M2 适用性画像）。
    """
    only_if = {}
    if carrier:
        only_if["carrier"] = list(carrier)
    if scenarios:
        only_if["scenario"] = list(scenarios)
    return {
        "rule_id": rid,
        "scope": scope,
        "carrier": list(carrier),
        "target": target,
        "check_type": check_type,
        "params": params,
        "severity": severity,
        "only_if": only_if,
        "clause": {"article": article, "excerpt": excerpt},
        "status": status,
        "source_url": MEASURES_SOURCE_URL,
        "verified_at": VERIFIED_AT if status == "verified" else None,
    }


MEASURES_RULES = [
    # --- 与国标同 target 的条目：记录法定义务与真实条号，判定由国标承担 → pending
    _measure("measures:explicit:text.notice.position", "explicit", ["text"], "text_explicit_notice",
             "第四条（一）", "文本内容：在起始、末尾或者中间适当位置添加文字/通用符号提示等标识，或在交互场景界面、文字周边添加显著提示标识",
             "position", {"allowed": PLACEMENT_HEAD_TAIL_MIDDLE}, "minor"),
    _measure("measures:explicit:image.notice.presence", "explicit", ["image"], "image_explicit_notice",
             "第四条（三）", "图片内容：在图片的适当位置添加显著的提示标识",
             "presence", {}, "major"),
    _measure("measures:explicit:audio.notice.presence", "explicit", ["audio"], "audio_explicit_notice",
             "第四条（二）", "音频内容：在起始、末尾或者中间适当位置添加语音提示或音频节奏提示等标识",
             "presence", {}, "major"),
    _measure("measures:explicit:video.notice.presence", "explicit", ["video"], "video_explicit_notice",
             "第四条（四）", "视频内容：在起始画面和播放周边的适当位置添加显著提示标识，可在末尾和中间适当位置添加",
             "presence", {}, "major"),
    _measure("measures:implicit:content.property.presence", "implicit", [], "content_property",
             "第五条", "应按照《互联网信息服务深度合成管理规定》第十六条在文件元数据中添加隐式标识，包含生成合成内容属性信息、服务提供者名称或者编码、内容编号等制作要素信息",
             "presence", {}, "critical"),
    _measure("measures:implicit:service.provider.presence", "implicit", [], "content_producer",
             "第五条", "制作要素信息之一：服务提供者名称或者编码",
             "presence", {}, "major"),
    _measure("measures:implicit:content.id.presence", "implicit", [], "content_id",
             "第五条", "制作要素信息之一：内容编号",
             "presence", {}, "minor"),
    # --- 办法独有义务：M2 适用性画像建立后转 verified（独立 target + 场景门控）
    #     第四条第二款：下载/复制/导出场景，导出文件须含显式标识 → exported 场景
    _measure("measures:explicit:export.file.label.presence", "explicit", [], "exported_file_explicit_label",
             "第四条第二款", "提供下载、复制、导出等功能时，应确保文件中含有符合本办法第四条要求的显式标识（导出场景适用）",
             "presence", {}, "major", status="verified", scenarios=["exported"]),
    #     第六条：传播平台核验隐式标识并在发布内容周边加显著提示 → propagated 场景
    _measure("measures:propagation:platform.hint.presence", "explicit", [], "propagation_platform_hint",
             "第六条", "提供网络信息内容传播服务的服务提供者应核验隐式标识，并在发布内容周边添加显著的提示标识（传播场景适用）",
             "presence", {}, "major", status="verified", scenarios=["propagated"]),
]


# --------------------------------------------------------------------- 组装产物
def build_ruleset(doc_id):
    """返回指定依据文档的**冻结规则库载荷**（顺序 = 模板声明序，确定性）。"""
    if doc_id == "gb45438-2025":
        rules = list(GB_EXPLICIT_RULES) + list(GB_IMPLICIT_RULES)
        comment = (
            "GB 45438-2025《网络安全技术 人工智能生成合成内容标识方法》核查规则（冻结产物，"
            "由 tools/gen_rulesets.py 生成，禁手改）。条款见 §5.1–5.4（显式）、§6.1 与规范性附录 E（隐式）。"
        )
    elif doc_id == "labeling-measures":
        rules = list(MEASURES_RULES)
        comment = (
            "《人工智能生成合成内容标识办法》（国信办通字〔2025〕2 号）条目（冻结产物，"
            "由 tools/gen_rulesets.py 生成，禁手改）。条号已核对；条目 status=pending——"
            "技术判定路径由 GB 45438-2025 承担，避免同一 target 跨文档重复判定。"
        )
    else:
        raise ValueError("未知 doc_id：{0}".format(doc_id))
    return {
        "schema_version": 1,
        "doc_id": doc_id,
        "version": VERSION,
        "rules": rules,
        "_comment": comment,
    }


def payload_sha256(payload):
    """与 ``labelcheck.rules.loader`` 完全一致的规范化指纹。"""
    return sha256_text(canonical_json(payload, indent=None, sort_keys=True))


def build_registry():
    """返回 ``registry.json`` 载荷（含各版本规则文件的规范化 sha256）。"""
    documents = []
    for doc in (MEASURES_DOC, GB_DOC):
        ruleset = build_ruleset(doc["doc_id"])
        documents.append({
            "doc_id": doc["doc_id"],
            "title": doc["title"],
            "doc_number": doc["doc_number"],
            "kind": doc["kind"],
            "issuer": doc["issuer"],
            "effective_from": doc["effective_from"],
            "status": doc["status"],
            "source_url": doc["source_url"],
            "note": doc["note"],
            "versions": [{
                "version": VERSION,
                "effective_from": VERSION,
                "rules_file": "{0}/{1}.json".format(doc["doc_id"], VERSION),
                "status": doc["status"],
                "sha256": payload_sha256(ruleset),
                "source_url": doc["source_url"],
                "note": doc["note"],
            }],
        })
    return {
        "schema_version": 1,
        "_comment": (
            "依据文件注册表（冻结产物，由 tools/gen_rulesets.py 生成）。"
            "status=verified 的文档+条目才进判定路径；active 声明当前生效版本。"
        ),
        "documents": documents,
        "active": {doc["doc_id"]: VERSION for doc in (MEASURES_DOC, GB_DOC)},
    }


def artifacts():
    """``[(相对路径, 载荷对象), …]`` —— 生成与校验共用同一清单。"""
    items = []
    for doc in (MEASURES_DOC, GB_DOC):
        items.append(("rules/{0}/{1}.json".format(doc["doc_id"], VERSION),
                      build_ruleset(doc["doc_id"])))
    items.append(("rules/registry.json", build_registry()))
    return items


# --------------------------------------------------------------------- CLI
def _render(payload):
    text = canonical_json(payload, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def write_all(data_dir, verbose=True):
    """就地生成全部规则库产物（LF 落盘）。"""
    data_dir = Path(data_dir)
    for rel, payload in artifacts():
        path = data_dir / rel
        write_json(path, payload)
        if verbose:
            print("写入 {0}".format(path))
    return 0


def check_all(data_dir, verbose=True):
    """比对已入库产物与重生成结果；不一致返回非零（守门/CI 用）。"""
    data_dir = Path(data_dir)
    problems = []
    for rel, payload in artifacts():
        path = data_dir / rel
        expected = _render(payload)
        if not path.is_file():
            problems.append("缺失：{0}".format(rel))
            continue
        actual = path.read_bytes()
        if actual != expected:
            problems.append("字节不一致：{0}（已入库 {1} 字节 vs 重生成 {2} 字节）".format(
                rel, len(actual), len(expected)))
        elif verbose:
            print("一致 {0}  sha256={1}".format(rel, payload_sha256(payload)))
    if problems:
        sys.stderr.write("规则库产物与生成器不一致：\n  " + "\n  ".join(problems) + "\n")
        return 1
    if verbose:
        print("规则库产物全部与生成器一致")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir = REPO_ROOT / "data"
    if "--data-dir" in argv:
        data_dir = Path(argv[argv.index("--data-dir") + 1])
        argv = [a for a in argv if a != "--data-dir"]
    if "--check" in argv:
        return check_all(data_dir)
    return write_all(data_dir)


if __name__ == "__main__":
    sys.exit(main())
