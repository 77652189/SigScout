from __future__ import annotations

from sigscout.core.coercion import safe_float, safe_int_from_float, truthy


DEEPLOC_THRESHOLDS = {
    "extracellular": 0.6173,
    "cell_membrane": 0.5646,
    "endoplasmic_reticulum": 0.6090,
    "lysosome_vacuole": 0.5848,
    "golgi_apparatus": 0.6494,
    "peripheral": 0.60,
    "transmembrane": 0.51,
    "lipid_anchor": 0.82,
    "soluble": 0.50,
}


def summarize_localization(row: dict[str, object]) -> dict[str, object]:
    localization_text = " ".join(
        str(row.get(key, "")) for key in ("deeploc_localization", "busca_localization")
    ).lower()
    membrane_type_text = " ".join(
        str(row.get(key, "")) for key in ("deeploc_membrane_types", "busca_membrane_types")
    ).lower()
    extracellular_score = max(safe_float(row.get("deeploc_extracellular")), safe_float(row.get("busca_extracellular")))
    er_golgi_score = max(
        safe_float(row.get("deeploc_endoplasmic_reticulum")),
        safe_float(row.get("deeploc_golgi_apparatus")),
        safe_float(row.get("busca_endoplasmic_reticulum")),
        safe_float(row.get("busca_golgi_apparatus")),
    )
    membrane_score = max(
        safe_float(row.get("deeploc_cell_membrane")),
        safe_float(row.get("deeploc_transmembrane")),
        safe_float(row.get("deeploc_lipid_anchor")),
        safe_float(row.get("busca_cell_membrane")),
        safe_float(row.get("busca_transmembrane")),
        safe_float(row.get("busca_lipid_anchor")),
    )
    vacuole_score = max(safe_float(row.get("deeploc_lysosome_vacuole")), safe_float(row.get("busca_lysosome_vacuole")))
    soluble_score = max(safe_float(row.get("deeploc_soluble")), safe_float(row.get("busca_soluble")))
    return {
        "external_secreted_signal": _contains_any(localization_text, ("extracellular", "secreted", "outside"))
        or extracellular_score >= DEEPLOC_THRESHOLDS["extracellular"],
        "external_er_golgi_signal": _contains_any(localization_text, ("endoplasmic reticulum", "golgi", "secretory pathway"))
        or safe_float(row.get("deeploc_endoplasmic_reticulum")) >= DEEPLOC_THRESHOLDS["endoplasmic_reticulum"]
        or safe_float(row.get("deeploc_golgi_apparatus")) >= DEEPLOC_THRESHOLDS["golgi_apparatus"],
        "external_membrane_risk": _contains_any(localization_text, ("plasma membrane", "cell membrane"))
        or _contains_any(membrane_type_text, ("transmembrane", "lipid anchor", "lipid-anchored"))
        or safe_float(row.get("deeploc_cell_membrane")) >= DEEPLOC_THRESHOLDS["cell_membrane"]
        or safe_float(row.get("deeploc_transmembrane")) >= DEEPLOC_THRESHOLDS["transmembrane"]
        or safe_float(row.get("deeploc_lipid_anchor")) >= DEEPLOC_THRESHOLDS["lipid_anchor"],
        "external_vacuole_risk": _contains_any(localization_text, ("vacuole", "lysosome", "lysosomal"))
        or vacuole_score >= DEEPLOC_THRESHOLDS["lysosome_vacuole"],
        "external_extracellular_probability": round(extracellular_score, 4),
        "external_soluble_probability": round(soluble_score, 4),
        "external_er_golgi_probability": round(er_golgi_score, 4),
        "external_membrane_probability": round(membrane_score, 4),
        "external_vacuole_probability": round(vacuole_score, 4),
    }


def score_construct(row: dict[str, object]) -> dict[str, object]:
    localization = summarize_localization(row)
    construct_type = str(row.get("construct_type", ""))
    signal_score = safe_int_from_float(row.get("rules_score"))
    if construct_type in {"C_ONLY", "BC"}:
        signal_score = 0
    elif construct_type == "POSITIVE_CONTROL_C" and not signal_score:
        signal_score = 75

    processing_score = _processing_score(row)
    localization_score = 0
    if localization["external_secreted_signal"]:
        localization_score += 55
    if localization["external_er_golgi_signal"]:
        localization_score += 30

    risk_score = _risk_score(row, localization)
    overall = round(max(0, min(100, signal_score * 0.35 + processing_score * 0.30 + localization_score * 0.25 - risk_score)))
    localization_detail_score = _localization_probability_score(row, localization)
    signal_detail_score = _signal_detail_score(row)
    source_context_score = _source_context_score(row)
    fine_score = _fine_priority_score(row, localization, overall, risk_score)
    has_external_result = any(str(row.get(key, "")).strip() for key in ("deeploc_localization", "busca_localization"))
    if not has_external_result and construct_type not in {"C_ONLY", "BC"}:
        priority = "待外部定位"
    elif risk_score >= 40 or overall < 45:
        priority = "低"
    elif overall >= 70:
        priority = "高"
    else:
        priority = "中"
    return {
        **localization,
        "signal_peptide_quality": signal_score,
        "processing_quality": processing_score,
        "external_localization_support": localization_score,
        "localization_probability_score": localization_detail_score,
        "signal_peptide_detail_score": signal_detail_score,
        "source_context_score": source_context_score,
        "membrane_or_vacuole_risk": risk_score,
        "construct_design_risk": risk_score,
        "overall_score": overall,
        "fine_priority_score": fine_score,
        "overall_priority": priority,
    }


def _processing_score(row: dict[str, object]) -> int:
    construct_type = str(row.get("construct_type", ""))
    if construct_type == "C_ONLY":
        score = 5
    elif construct_type == "BC":
        score = 20
    elif construct_type == "AC":
        score = 55
    elif construct_type == "ABC":
        score = 65
        if truthy(row.get("b_ends_with_kex2_site")):
            score += 15
        if truthy(row.get("b_pre_region_like")):
            score -= 25
    elif construct_type == "POSITIVE_CONTROL_C":
        score = 75
    else:
        score = 50
    if truthy(row.get("has_er_retention_motif")):
        score -= 20
    if safe_int_from_float(row.get("internal_hydrophobic_run_max")) >= 18:
        score -= 10
    return max(0, min(100, score))


def _risk_score(row: dict[str, object], localization: dict[str, object]) -> int:
    score = 0
    if truthy(row.get("has_er_retention_motif")):
        score += 25
    if truthy(row.get("has_vacuolar_sorting_motif")):
        score += 15
    if truthy(row.get("gpi_anchor_like_risk")):
        score += 20
    if safe_int_from_float(row.get("internal_hydrophobic_run_max")) >= 18:
        score += 20
    if safe_float(row.get("low_complexity_fraction")) >= 0.28:
        score += 10
    if localization["external_membrane_risk"]:
        score += 25
    if localization["external_vacuole_risk"]:
        score += 25
    return min(100, score)


def _localization_probability_score(row: dict[str, object], localization: dict[str, object]) -> float:
    extracellular = safe_float(localization.get("external_extracellular_probability"))
    soluble = safe_float(localization.get("external_soluble_probability"))
    er_golgi = safe_float(localization.get("external_er_golgi_probability"))
    membrane = safe_float(localization.get("external_membrane_probability"))
    vacuole = safe_float(localization.get("external_vacuole_probability"))
    score = 15 + extracellular * 55 + soluble * 15 + er_golgi * 10 - membrane * 22 - vacuole * 18
    if _contains_any(str(row.get("deeploc_localization", "")).lower(), ("extracellular", "secreted")):
        score += 8
    if _contains_any(str(row.get("deeploc_membrane_types", "")).lower(), ("soluble",)):
        score += 4
    return round(max(0, min(100, score)), 1)


def _signal_detail_score(row: dict[str, object]) -> float:
    score = safe_float(row.get("rules_score")) * 0.45
    a_length = safe_int_from_float(row.get("a_length"))
    if 17 <= a_length <= 30:
        score += 12
    elif 14 <= a_length <= 35:
        score += 7
    else:
        score -= 6

    hydrophobicity = safe_float(row.get("rules_h_region_max_hydrophobicity"))
    if 2.0 <= hydrophobicity <= 3.4:
        score += 12
    elif 1.7 <= hydrophobicity <= 3.8:
        score += 7
    elif hydrophobicity:
        score -= 5

    n_positive = safe_int_from_float(row.get("rules_n_region_positive_count"))
    if 1 <= n_positive <= 3:
        score += 8
    elif n_positive > 3:
        score += 3

    if truthy(row.get("rules_c_region_small_neutral")):
        score += 8
    if str(row.get("uspnet_prediction", "")).strip().upper() == "SP":
        score += 8
    if str(row.get("uspnet_cleavage_sequence", "")).strip():
        score += 5
    if safe_int_from_float(row.get("similar_group_size")) > 1:
        score += min(6, safe_int_from_float(row.get("similar_group_size")))
    return round(max(0, min(100, score)), 1)


def _source_context_score(row: dict[str, object]) -> int:
    route = str(row.get("source_protein_route", "")).strip()
    evidence = str(row.get("source_protein_evidence_level", "")).strip()
    route_score = {
        "分泌/胞外倾向": 100,
        "分泌通路腔室倾向": 78,
        "膜/锚定倾向": 58,
        "胞内或非典型": 30,
        "未知": 45,
        "未评估": 45,
    }.get(route, 45)
    evidence_score = {
        "实验支持": 100,
        "人工/同源推断": 82,
        "自动/预测证据": 60,
        "无明确证据": 40,
    }.get(evidence, 50)
    return round(route_score * 0.65 + evidence_score * 0.35)


def _fine_priority_score(
    row: dict[str, object],
    localization: dict[str, object],
    overall_score: int,
    risk_score: int,
) -> float:
    localization_detail = _localization_probability_score(row, localization)
    signal_detail = _signal_detail_score(row)
    source_context = _source_context_score(row)
    processing_score = _processing_score(row)
    construct_bonus = 4 if str(row.get("construct_type", "")) == "ABC" and truthy(row.get("b_ends_with_kex2_site")) else 0
    score = (
        overall_score * 0.30
        + localization_detail * 0.30
        + signal_detail * 0.22
        + processing_score * 0.10
        + source_context * 0.08
        + construct_bonus
        - max(0, risk_score - 15) * 0.20
    )
    return round(max(0, min(100, score)), 1)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
