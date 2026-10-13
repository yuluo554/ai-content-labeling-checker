"""端到端编排（**单一事实源**）：CLI 与未来 GUI 共用同一编排，不各起一套行为。

契约见 plan/03 §一 / plan/04 §一。GUI 只渲染本模块返回的 :class:`CheckReport`。

**文件级入口**（:func:`check_file`，M3）：把"输入文件 → 报告"的分派逻辑收在这里，
``check``（单件）与 ``scan``（批量）共用同一条路径——**两条通路不得各写一套分派**，
否则批量与单件对同一文件会给出不同结论（最隐蔽的口径漂移）。
"""

from ..mapping import load_mapping_table
from ..model import CheckReport, LabelCard
from ..rules import effective_ruleset
from .explicit import check_explicit
from .implicit import check_implicit
from .integrity import grade_findings


def check_card(card, data_dir, generated_at=""):
    """对单件标识卡做全链路核验，返回 :class:`CheckReport`。

    :param card: :class:`LabelCard`（已通过 ``from_dict`` 校验）
    :param data_dir: 数据目录（规则库 + 映射表所在）
    :param generated_at: 报告时间戳，**由调用方传入**（基准/测试传固定值 →
        相同输入两次导出逐字节一致）

    场景（``card.scenario``）与观测作用域（``card.observed``）**随卡进入编排**：
    场景决定哪些规则适用（不适用记 ``skipped``），观测作用域决定该 scope 是否
    只能是 ``unknown``（解析通路看不到显式标识）。
    """
    ruleset = effective_ruleset(data_dir)
    mapping_table = load_mapping_table(data_dir)

    explicit_findings = check_explicit(card, ruleset)
    implicit_findings = check_implicit(card, ruleset, mapping_table)

    findings = explicit_findings + implicit_findings
    grade, missing, errors = grade_findings(findings)

    return CheckReport(
        card_id=card.card_id,
        carrier=card.carrier,
        ruleset_coordinate=ruleset.coordinate,
        documents=ruleset.doc_versions,
        verified_rule_count=ruleset.verified_rule_count,
        pending_rule_count=ruleset.pending_rule_count,
        explicit=explicit_findings,
        implicit=implicit_findings,
        grade=grade,
        missing=missing,
        errors=errors,
        content_sha256=card.content_sha256,
        generated_at=generated_at,
        scenario=card.scenario,
        source=card.source,
        observed=dict(card.observed),
    )


def check_card_dict(card_data, data_dir, generated_at=""):
    """从 dict 校验并核验（CLI 主通路）。"""
    card = LabelCard.from_dict(card_data)
    return check_card(card, data_dir, generated_at=generated_at)


def check_file(path, data_dir, generated_at="", scenario=None):
    """核验**单个文件**：标识卡 JSON **或**可解析容器 → :class:`CheckReport`。

    ``check`` 单件与 ``scan`` 批量共用本函数——分派规则只此一份：

    1. 读字节；JSON 解析成功 → 按 :class:`LabelCard` 校验并核验；
    2. 不是 JSON → 按容器魔数走解析通路（PNG/JPEG/ISO BMFF）；
    3. 两者皆不是 → :class:`UsageError`（**不静默给假结论**）。

    :param path: 输入文件路径（str 或 Path）
    :param data_dir: 数据目录
    :param generated_at: 报告时间戳（**由调用方传入**，保证可复现）
    :param scenario: 覆盖卡内场景（``None`` = 用卡内声明/默认）
    :returns: ``(report, parse_outcome)``——``parse_outcome`` 仅容器通路非 None，
        供 CLI 输出 ``parse`` 块与解析提示（标识卡通路为 ``None``）。
    """
    from pathlib import Path

    from ..errors import UsageError
    from ..jsonio import load_json_str
    from ..parse import parse_bytes
    from ..parse.containers import detect_container

    path = Path(path)
    if not path.is_file():
        raise UsageError("文件不存在：{0}".format(path))
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UsageError("无法读取文件：{0}（{1}）".format(path, exc))

    card_data = None
    try:
        card_data = load_json_str(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        card_data = None

    parse_outcome = None
    if card_data is not None:
        card = LabelCard.from_dict(card_data)
    else:
        container = detect_container(raw)
        if container is None:
            raise UsageError(
                "输入既不是合法标识卡 JSON，也不是可解析容器（PNG/JPEG/MP4/M4A）：{0}".format(path))
        table = load_mapping_table(data_dir)
        parse_outcome = parse_bytes(raw, container, table.payload_wrapper)
        card = parse_outcome.card

    if scenario:
        card = with_scenario(card, scenario)

    report = check_card(card, data_dir, generated_at=generated_at)
    return report, parse_outcome


def with_scenario(card, scenario):
    """按场景覆盖卡内声明（不改动其余字段）；``scenario`` 合法性由模型层把关。"""
    return LabelCard(
        card_id=card.card_id,
        carrier=card.carrier,
        content_sha256=card.content_sha256,
        explicit=card.explicit,
        implicit=card.implicit,
        source=card.source,
        notes=card.notes,
        scenario=scenario,
        observed=card.observed,
        implicit_duplicate_keys=card.implicit_duplicate_keys,
    )


__all__ = ["check_card", "check_card_dict", "check_file", "with_scenario"]
