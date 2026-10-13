# -*- coding: utf-8 -*-
"""解析通路：可解析容器文件 → 标识卡（plan/02 §二.1 / plan/06 P2 首批载体）。

**通路定位**：这层只负责"从容器里尽量取到隐式（元数据）标识"，产出**同一** UMR
（:class:`labelcheck.model.LabelCard`），交给引擎走与手工录入完全相同的判定路径。

**确定性纪律（plan/05 §三.1）**：

- 纯 stdlib、无时钟、无随机——同字节文件 → 同标识卡 → 同报告（逐字节一致）；
- ``card_id`` 由**内容 sha256 派生**（同内容同 id，不引入路径/时间），前缀 ``PARSED-``；
- 键序 = 发现顺序（list，非 set）。

**降级纪律（硬要求，plan/02 §二.1）**：解析不到就**显式降级**，绝不臆测：

- 容器结构畸形/截断 → ``隐式作用域未观测``；
- 元数据无 AIGC 载荷 → ``隐式作用域未观测``；
- **显式标识作用域恒为未观测**——显式标识是渲染后画面/语音上的文字提示，文件解析器
  看不到，绝不敢据此判"合规"或"缺失"。

两类未观测共同决定：引擎对相应 scope 全部判 ``unknown``。若**两个 scope 都未观测**，
调用方应视为"未评估"（``not_assessed`` 之外的另一条理由），本模块以
``ParseOutcome`` 显式暴露这一事实，不做沉默假设。
"""

from pathlib import Path

from ..jsonio import sha256_bytes
from ..model import LabelCard
from .aigc import extract_aigc_payload
from .containers import (
    CONTAINER_ISO, CONTAINER_JPEG, CONTAINER_PNG, SUFFIX_TO_CONTAINER,
    detect_container, iso_carrier, iter_metadata_blobs,
)

#: 解析产出的 card_id 前缀（与合成样本的 SYN-、手工的 SAMPLE- 区分，来源可辨）
CARD_ID_PREFIX = "PARSED-"

#: 解析不可用的原因码（进 ``LabelCard.notes``，也供 CLI 提示；不参与判定）
REASON_UNKNOWN_CONTAINER = "unsupported_container"
REASON_STRUCTURE_BROKEN = "structure_broken"
REASON_NO_AIGC_PAYLOAD = "no_aigc_payload"
REASON_NO_PAYLOAD_WRAPPER = "no_payload_wrapper_configured"


class ParseOutcome(object):
    """一次解析的结果：标识卡 + 可观测性事实 + 人类可读说明。"""

    __slots__ = ("card", "container", "implicit_observed", "explicit_observed",
                 "reasons", "aigc_field_count", "payload_count")

    def __init__(self, card, container, implicit_observed, explicit_observed,
                 reasons=None, aigc_field_count=0, payload_count=0):
        self.card = card
        self.container = container
        self.implicit_observed = implicit_observed
        self.explicit_observed = explicit_observed
        self.reasons = list(reasons) if reasons else []
        self.aigc_field_count = aigc_field_count
        self.payload_count = payload_count

    @property
    def fully_unobserved(self):
        """两个作用域都没观测到 → 无从判定（调用方须如实说"未评估"）。"""
        return not self.implicit_observed and not self.explicit_observed

    def summary(self):
        return (
            "container={0} implicit_observed={1} explicit_observed={2} "
            "aigc_fields={3} payloads={4} reasons={5}".format(
                self.container, self.implicit_observed, self.explicit_observed,
                self.aigc_field_count, self.payload_count,
                ",".join(self.reasons) or "-",
            )
        )


def container_for_path(path):
    """按后缀取容器类型（; 无匹配返回 None）。"""
    return SUFFIX_TO_CONTAINER.get(Path(path).suffix.lower())


def parse_bytes(data, container, wrapper, card_id=None):
    """把容器字节解析为 :class:`ParseOutcome`（纯函数，便于测试与基准）。

    :param data: 容器文件的全部字节
    :param container: 容器类型（``png``/``jpeg``/``iso-bmff``）
    :param wrapper: 载荷外层包裹键（来自映射表解析画像）
    :param card_id: 显式指定 card_id；缺省由内容 sha256 派生（确定性）

    **"隐式作用域是否已观测"的口径**（关键语义，见模块 docstring）：

    - 容器结构完整 **且** 配置了解析画像 → 元数据区**已被检查**，无论是否找到 AIGC 载荷
      都算已观测：没找到就是"该文件确实没有隐式标识"，由 ``presence`` 规则判 ``fail``；
    - 容器结构畸形/截断、或容器类型不可识别 → **未观测** → 全部判 ``unknown``（不臆测）。
    """
    reasons = []
    blobs, structure_ok = iter_metadata_blobs(data, container)
    if not structure_ok:
        reasons.append(REASON_STRUCTURE_BROKEN)

    fields, found = ({}, False)
    wrapper_ok = bool(wrapper)
    payload_count = 0
    if wrapper_ok:
        fields, payload_count = extract_aigc_payload(blobs, wrapper)
        found = bool(fields)
    else:
        reasons.append(REASON_NO_PAYLOAD_WRAPPER)
    if wrapper_ok and not found and structure_ok:
        reasons.append(REASON_NO_AIGC_PAYLOAD)

    # 元数据区"已被检查"的条件：结构完整 + 有解析画像（能识别载荷形态）
    implicit_observed = structure_ok and wrapper_ok

    digest = sha256_bytes(data)
    if card_id is None:
        card_id = "{0}{1}".format(CARD_ID_PREFIX, digest[:16])

    carrier = _carrier_for(container, data)

    # 同一容器键在多份载荷里重复出现 → 据实登记（§6.1 c) 唯一性判定的输入之一）。
    # 载荷块 >1 份本身就构成"重复保留"，此时把全部已发现键登记为重复键。
    duplicate_keys = []
    if payload_count > 1:
        duplicate_keys = sorted(fields.keys())

    # 显式标识恒未观测：文件解析器读不到渲染后的画面/语音文字
    card = LabelCard(
        card_id=card_id,
        carrier=carrier,
        content_sha256=digest,
        explicit=[],
        implicit=fields,
        source="parsed",
        notes="；".join(reasons) if reasons else "解析得到 AIGC 元数据",
        observed={"explicit": False, "implicit": implicit_observed},
        implicit_duplicate_keys=duplicate_keys,
    )
    return ParseOutcome(
        card=card,
        container=container,
        implicit_observed=implicit_observed,
        explicit_observed=False,
        reasons=reasons,
        aigc_field_count=len(fields),
        payload_count=payload_count,
    )


def _carrier_for(container, data):
    """容器类型 → 载体（PNG/JPEG = 图片；ISO BMFF 按主品牌分音频/视频）。"""
    if container == CONTAINER_ISO:
        return iso_carrier(data)
    if container in (CONTAINER_PNG, CONTAINER_JPEG):
        return "image"
    return "video"


def parse_file(path, wrapper, card_id=None):
    """读取容器文件并解析（:func:`parse_bytes` 的文件版）。

    :raises EnvironmentError_: 文件不存在/不可读（→ exit 3，环境问题）
    """
    from ..errors import EnvironmentError_

    path = Path(path)
    if not path.is_file():
        raise EnvironmentError_("待解析文件不存在：{0}".format(path))
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EnvironmentError_("无法读取待解析文件：{0}（{1}）".format(path, exc))

    container = detect_container(data) or container_for_path(path)
    if container is None:
        return _unsupported_outcome(data, card_id)

    return parse_bytes(data, container, wrapper, card_id=card_id)


def _unsupported_outcome(data, card_id):
    """无法识别的容器：显式降级（不猜载体、不编元数据）。"""
    digest = sha256_bytes(data)
    if card_id is None:
        card_id = "{0}{1}".format(CARD_ID_PREFIX, digest[:16])
    card = LabelCard(
        card_id=card_id,
        carrier="video",  # 载体不可知时的占位；observed 两者皆 False，不会产生判定
        content_sha256=digest,
        explicit=[],
        implicit={},
        source="parsed",
        notes=REASON_UNKNOWN_CONTAINER,
        observed={"explicit": False, "implicit": False},
    )
    return ParseOutcome(
        card=card,
        container=None,
        implicit_observed=False,
        explicit_observed=False,
        reasons=[REASON_UNKNOWN_CONTAINER],
        aigc_field_count=0,
        payload_count=0,
    )


__all__ = [
    "parse_file", "parse_bytes", "container_for_path", "ParseOutcome",
    "CARD_ID_PREFIX",
    "REASON_UNKNOWN_CONTAINER", "REASON_STRUCTURE_BROKEN",
    "REASON_NO_AIGC_PAYLOAD", "REASON_NO_PAYLOAD_WRAPPER",
]