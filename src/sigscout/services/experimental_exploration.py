from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from sigscout.core.coercion import truthy
from sigscout.services.similarity import signal_peptide_identity


CHANNEL_POSITIVE = "正向锚点邻域"
CHANNEL_GENERIC = "通用预测强"
CHANNEL_DIVERSITY = "多样性保留"
CHANNEL_CONTROL = "低表现邻域对照"


def build_experiment_guided_exploration(
    candidate_rows: pd.DataFrame | Iterable[dict[str, object]],
    *,
    panel_size: int = 40,
) -> pd.DataFrame:
    frame = candidate_rows.copy() if isinstance(candidate_rows, pd.DataFrame) else pd.DataFrame(list(candidate_rows))
    if frame.empty:
        return frame
    measured = frame[
        frame["experimental_status"].astype(str).eq("measured")
        & frame["experimental_unit_type"].astype(str).eq("signal_peptide")
    ].copy()
    untested = frame[frame["experimental_status"].astype(str).eq("untested")].copy()
    if measured.empty or untested.empty:
        return pd.DataFrame()

    measured["_relative"] = pd.to_numeric(measured["experimental_relative_median"], errors="coerce")
    positive = measured[measured["_relative"].ge(0.80)]
    medium = measured[measured["_relative"].ge(0.50) & measured["_relative"].lt(0.80)]
    low = measured[measured["_relative"].lt(0.50)]
    anchors = {
        "positive": _anchor_records(positive),
        "medium": _anchor_records(medium),
        "low": _anchor_records(low),
    }

    scored = []
    for row in untested.to_dict(orient="records"):
        sequence = str(row.get("signal_peptide_sequence", ""))
        positive_identity, positive_anchor = _nearest_anchor(sequence, anchors["positive"])
        medium_identity, medium_anchor = _nearest_anchor(sequence, anchors["medium"])
        low_identity, low_anchor = _nearest_anchor(sequence, anchors["low"])
        rules = _number(row.get("rules_score")) / 100.0
        consensus = 1.0 if truthy(row.get("consensus_pass")) else 0.0
        uspnet = 1.0 if truthy(row.get("uspnet_pass")) or str(row.get("uspnet_prediction", "")).upper() == "SP" else 0.0
        source = 1.0 if str(row.get("source_protein_route", "")) in {"分泌/胞外倾向", "分泌通路腔室倾向"} else 0.0
        generic = min(1.0, max(0.0, rules * 0.60 + consensus * 0.20 + uspnet * 0.10 + source * 0.10))
        guided = min(
            1.0,
            max(0.0, positive_identity * 0.45 + medium_identity * 0.15 + generic * 0.30 - low_identity * 0.15),
        )
        scored.append({
            **row,
            "exploration_positive_identity": positive_identity,
            "exploration_positive_anchor": positive_anchor,
            "exploration_medium_identity": medium_identity,
            "exploration_medium_anchor": medium_anchor,
            "exploration_low_identity": low_identity,
            "exploration_low_anchor": low_anchor,
            "exploration_generic_support": generic,
            "exploration_guided_score": guided,
        })
    scored_frame = pd.DataFrame(scored)
    panel_size = max(1, min(int(panel_size), len(scored_frame)))
    quotas = _channel_quotas(panel_size)
    selected: list[dict[str, object]] = []
    used: set[str] = set()

    _take(
        scored_frame.sort_values(
            ["exploration_positive_identity", "exploration_guided_score", "candidate_id"],
            ascending=[False, False, True],
        ),
        quotas[CHANNEL_POSITIVE],
        CHANNEL_POSITIVE,
        selected,
        used,
        lambda row: (
            f"与正向锚点 {row['exploration_positive_anchor'] or '无'} 的精确序列相似度 "
            f"{row['exploration_positive_identity']:.3f}"
        ),
    )
    _take(
        scored_frame.sort_values(
            ["exploration_generic_support", "exploration_guided_score", "candidate_id"],
            ascending=[False, False, True],
        ),
        quotas[CHANNEL_GENERIC],
        CHANNEL_GENERIC,
        selected,
        used,
        lambda row: f"规则、USPNet、一致性和来源证据支持 {row['exploration_generic_support']:.3f}",
    )
    _take_diverse(scored_frame, quotas[CHANNEL_DIVERSITY], selected, used)
    _take(
        scored_frame.sort_values(
            ["exploration_low_identity", "exploration_generic_support", "candidate_id"],
            ascending=[False, False, True],
        ),
        quotas[CHANNEL_CONTROL],
        CHANNEL_CONTROL,
        selected,
        used,
        lambda row: (
            f"与低表现锚点 {row['exploration_low_anchor'] or '无'} 相似度 "
            f"{row['exploration_low_identity']:.3f}，用于机制对照而非优先候选"
        ),
    )
    if len(selected) < panel_size:
        _take(
            scored_frame.sort_values(
                ["exploration_guided_score", "candidate_id"], ascending=[False, True]
            ),
            panel_size - len(selected),
            CHANNEL_GENERIC,
            selected,
            used,
            lambda row: f"实验引导综合证据 {row['exploration_guided_score']:.3f}",
        )
    return pd.DataFrame(selected[:panel_size])


def _channel_quotas(panel_size: int) -> dict[str, int]:
    positive = round(panel_size * 0.40)
    generic = round(panel_size * 0.30)
    diversity = round(panel_size * 0.20)
    control = panel_size - positive - generic - diversity
    return {
        CHANNEL_POSITIVE: positive,
        CHANNEL_GENERIC: generic,
        CHANNEL_DIVERSITY: diversity,
        CHANNEL_CONTROL: control,
    }


def _anchor_records(frame: pd.DataFrame) -> list[tuple[str, str]]:
    return [
        (str(row.get("signal_peptide_sequence", "")), str(row.get("source_note") or row.get("candidate_id", "")))
        for row in frame.to_dict(orient="records")
        if str(row.get("signal_peptide_sequence", ""))
    ]


def _nearest_anchor(sequence: str, anchors: list[tuple[str, str]]) -> tuple[float, str]:
    if not anchors:
        return 0.0, ""
    scored = [(signal_peptide_identity(sequence, anchor_sequence), name) for anchor_sequence, name in anchors]
    return max(scored, key=lambda item: (item[0], item[1]))


def _take(
    frame: pd.DataFrame,
    count: int,
    channel: str,
    selected: list[dict[str, object]],
    used: set[str],
    reason,
) -> None:
    if count <= 0:
        return
    added = 0
    for row in frame.to_dict(orient="records"):
        candidate_id = str(row.get("candidate_id", ""))
        if not candidate_id or candidate_id in used:
            continue
        updated = dict(row)
        updated["exploration_channel"] = channel
        updated["exploration_reason"] = reason(row)
        selected.append(updated)
        used.add(candidate_id)
        added += 1
        if added >= count:
            break


def _take_diverse(
    frame: pd.DataFrame,
    count: int,
    selected: list[dict[str, object]],
    used: set[str],
) -> None:
    if count <= 0:
        return
    candidates = [
        row for row in frame.to_dict(orient="records")
        if str(row.get("candidate_id", "")) not in used
    ]
    added = 0
    while candidates and added < count:
        selected_sequences = [str(row.get("signal_peptide_sequence", "")) for row in selected]
        for row in candidates:
            sequence = str(row.get("signal_peptide_sequence", ""))
            row["_max_selected_identity"] = max(
                (signal_peptide_identity(sequence, chosen) for chosen in selected_sequences),
                default=0.0,
            )
        candidates.sort(
            key=lambda row: (
                row["_max_selected_identity"],
                -float(row.get("exploration_generic_support", 0)),
                str(row.get("candidate_id", "")),
            )
        )
        row = candidates.pop(0)
        row["exploration_channel"] = CHANNEL_DIVERSITY
        row["exploration_reason"] = (
            f"与当前面板最大相似度 {row.pop('_max_selected_identity'):.3f}，保留不同序列结构"
        )
        selected.append(row)
        used.add(str(row.get("candidate_id", "")))
        added += 1


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


