from __future__ import annotations

from hashlib import sha1
from typing import Iterable

import pandas as pd


MEASURED = "measured"
RESULT_MISSING = "result_missing"
EVIDENCE_COLUMNS = (
    "experimental_unit_type",
    "experimental_match_type",
    "experimental_status",
    "experimental_relative_median",
    "experimental_relative_min",
    "experimental_relative_max",
    "experimental_record_count",
    "experimental_batch_count",
    "experimental_nucleotide_variant_count",
    "experimental_note",
)


def build_target_experimental_candidates(
    feedback_rows: pd.DataFrame | Iterable[dict[str, object]], target_key: str
) -> pd.DataFrame:
    """Build target-only candidates without mutating the shared library."""
    rows = _target_rows(_as_frame(feedback_rows), target_key)
    if rows.empty or "signal_peptide_sequence" not in rows.columns:
        return pd.DataFrame()
    rows["_experimental_sequence"] = rows["signal_peptide_sequence"].map(_clean_aa)
    rows = rows.loc[rows["_experimental_sequence"].ne("")]
    candidates = []
    for sequence, group in rows.groupby("_experimental_sequence", sort=False):
        source_ids = sorted({str(value).strip() for value in group["signal_peptide_id"] if str(value).strip()})
        candidates.append({
            "candidate_id": f"{target_key.upper()}_EXP_{sha1(sequence.encode('ascii')).hexdigest()[:10].upper()}",
            "leader_sequence": sequence,
            "signal_peptide_sequence": sequence,
            "category": "target_experimental_candidate",
            "category_label": f"{target_key.upper()} 实验候选",
            "library_stage": "目标专属实验候选",
            "source_type": "experimental_feedback",
            "source_note": ", ".join(source_ids),
            "rationale": "该氨基酸序列曾进入目标蛋白实验；仅用于目标专属浏览。",
            "caution": "实验结果不写入通用候选评分，也不向相似序列传播。",
            "source_protein_route": "实验构建",
            "source_protein_evidence_level": "目标专属实验",
            "source_protein_route_basis": f"{target_key.upper()} 实验报告中的精确氨基酸序列",
            "rules_score": float("nan"),
            "uspnet_prediction_label": "未对实验 leader 重新运行",
            **_aggregate(group, target_key),
        })
    return pd.DataFrame(candidates)


def annotate_candidate_experimental_evidence(
    candidate_rows: pd.DataFrame | Iterable[dict[str, object]],
    feedback_rows: pd.DataFrame | Iterable[dict[str, object]],
    target_key: str,
) -> pd.DataFrame:
    candidates = _as_frame(candidate_rows)
    experimental = build_target_experimental_candidates(feedback_rows, target_key)
    by_sequence = {
        _clean_aa(row.get("signal_peptide_sequence")): row
        for row in experimental.to_dict(orient="records")
    }
    annotated = []
    for row in candidates.to_dict(orient="records"):
        sequence = _clean_aa(row.get("signal_peptide_sequence") or row.get("leader_sequence"))
        evidence = by_sequence.get(sequence)
        updated = dict(row)
        if evidence:
            updated.update({column: evidence.get(column, "") for column in EVIDENCE_COLUMNS})
            updated["experimental_match_type"] = "a_sequence_only"
        else:
            updated.update(_empty("none"))
        annotated.append(updated)
    return pd.DataFrame(annotated)


def annotate_construct_experimental_evidence(
    construct_rows: pd.DataFrame | Iterable[dict[str, object]],
    feedback_rows: pd.DataFrame | Iterable[dict[str, object]],
    target_key: str,
) -> pd.DataFrame:
    constructs = _as_frame(construct_rows)
    if constructs.empty:
        return _with_empty(constructs, "none")
    feedback = _target_rows(_as_frame(feedback_rows), target_key)
    if feedback.empty:
        return _with_empty(constructs, "none")
    feedback["_experimental_sequence"] = feedback["signal_peptide_sequence"].map(_clean_aa)
    by_a = {sequence: group for sequence, group in feedback.groupby("_experimental_sequence") if sequence}
    annotated = []
    for source in constructs.to_dict(orient="records"):
        updated = dict(source)
        a_sequence = _clean_aa(source.get("a_signal_peptide") or source.get("signal_peptide_sequence"))
        group = by_a.get(a_sequence)
        if group is None:
            updated.update(_empty("none"))
            annotated.append(updated)
            continue
        evidence = _aggregate(group, target_key)
        construct_sequence = _clean_aa(source.get("construct_sequence"))
        exact = False
        if str(source.get("construct_type", "")).upper() == "AC":
            exact = any(
                _clean_aa(row.get("target_protein_sequence"))
                and construct_sequence == a_sequence + _clean_aa(row.get("target_protein_sequence"))
                for _, row in group.iterrows()
            )
        match_type = "exact_construct" if exact else "a_sequence_only"
        if evidence["experimental_status"] == RESULT_MISSING:
            match_type = "result_missing"
        updated.update(evidence)
        updated["experimental_match_type"] = match_type
        updated["experimental_note"] = _construct_note(match_type, target_key)
        annotated.append(updated)
    return pd.DataFrame(annotated)


def _aggregate(group: pd.DataFrame, target_key: str) -> dict[str, object]:
    measured = group.loc[group["measurement_status"].astype(str).eq(MEASURED)]
    relative = pd.to_numeric(
        measured.get("batch_relative_to_best", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    nucleotide_variants = {
        str(value).strip().upper()
        for value in group.get("signal_peptide_nucleotide_sequence", pd.Series(dtype=str))
        if str(value).strip()
    }
    return {
        "experimental_unit_type": _unit_type(group),
        "experimental_match_type": "a_sequence_only",
        "experimental_status": MEASURED if not measured.empty else RESULT_MISSING,
        "experimental_relative_median": float(relative.median()) if not relative.empty else float("nan"),
        "experimental_relative_min": float(relative.min()) if not relative.empty else float("nan"),
        "experimental_relative_max": float(relative.max()) if not relative.empty else float("nan"),
        "experimental_record_count": int(len(group)),
        "experimental_batch_count": int(group["batch_id"].nunique()),
        "experimental_nucleotide_variant_count": len(nucleotide_variants),
        "experimental_note": f"仅表示该精确 A/leader 序列在 {target_key.upper()} 实验中出现；不改变通用预测分。",
    }


def _unit_type(group: pd.DataFrame) -> str:
    ids = " ".join(group["signal_peptide_id"].astype(str)).lower()
    variants = {str(value).strip().lower() for value in group["construct_variant"]}
    if "alpha-factor" not in ids:
        return "signal_peptide"
    if variants - {"", "wild_type", "codon_optimized"}:
        return "leader_variant"
    return "full_leader"


def _construct_note(match_type: str, target_key: str) -> str:
    label = target_key.upper()
    if match_type == "exact_construct":
        return f"完整 AC 氨基酸构建与 {label} 实验精确一致，可作为构建级证据。"
    if match_type == "result_missing":
        return "实验报告提及该 A/leader，但没有可用于排序的产量结果。"
    return f"仅 A/leader 序列与 {label} 实验一致；当前完整构建未被该实验验证。"


def _empty(match_type: str) -> dict[str, object]:
    return {
        "experimental_unit_type": "",
        "experimental_match_type": match_type,
        "experimental_status": "untested",
        "experimental_relative_median": float("nan"),
        "experimental_relative_min": float("nan"),
        "experimental_relative_max": float("nan"),
        "experimental_record_count": 0,
        "experimental_batch_count": 0,
        "experimental_nucleotide_variant_count": 0,
        "experimental_note": "暂无该目标的精确实验序列证据。",
    }


def _with_empty(frame: pd.DataFrame, match_type: str) -> pd.DataFrame:
    updated = frame.copy()
    for column, value in _empty(match_type).items():
        updated[column] = value
    return updated


def _as_frame(rows: pd.DataFrame | Iterable[dict[str, object]]) -> pd.DataFrame:
    return rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))


def _target_rows(rows: pd.DataFrame, target_key: str) -> pd.DataFrame:
    if rows.empty or "target_key" not in rows.columns:
        return rows.iloc[0:0].copy()
    return rows.loc[rows["target_key"].astype(str).str.lower() == target_key.strip().lower()].copy()


def _clean_aa(value: object) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalpha())
