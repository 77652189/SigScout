from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Iterable

from sigscout.core.models import AA_PATTERN


CONSTRUCT_TYPES = ("AC", "ABC")
DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE = "APVNTTTEDETAQIPAEAVIGYSDLEGDFDVAVLPFSNSTNNGLLFINTTIASIAAKEEGVSLEKR"
DEFAULT_OPN_TARGET_SEQUENCE = (
    "IPVKQADSGSSEEKQLYNKYPDAVATWLNPDPSQKQNLLAPQNAVSSEETNDFKQETLPSKSNESHDHMDDMDDEDDDDHVDSQDSIDSNDSDDVDDTDDSHQSDESHHSDESDELVTDFPTDLPATEVFTPVVPTVDTYDGRGDSVVYGLRSKSKKFRRPDIQYPDATDEDITSHMESEELNGAYKAIPVAQDLNAPSDWDSRGKDSYETSQLDDQSAETHSHKQSRLYKRKANDESNEHSDVIDSQELSKVSREFHSHEFHSHEDMLVVDPKSKEEDKHLKFRISHELDSASSEVN"
)
LOCALIZATION_ID_COLUMNS = (
    "construct_id",
    "id",
    "protein_id",
    "protein",
    "entry",
    "name",
    "sequence_name",
    "sequence id",
    "sequence name",
)
LOCALIZATION_COLUMNS = (
    "localization",
    "localizations",
    "location",
    "prediction",
    "predicted_location",
    "deeploc_location",
    "busca_prediction",
    "subcellular_location",
    "main location",
    "final localization",
)
LOCALIZATION_SCORE_COLUMNS = (
    "score",
    "probability",
    "confidence",
    "reliability",
    "extracellular",
    "extracellular_score",
    "secreted_score",
)
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


@dataclass(frozen=True)
class FusionConstructResult:
    rows: list[dict[str, object]]
    errors: list[str]


@dataclass(frozen=True)
class LocalizationImportResult:
    rows: list[dict[str, object]]
    errors: list[str]
    imported_count: int


def build_fusion_constructs(
    signal_rows: Iterable[dict[str, object]],
    *,
    b_sequence: str,
    c_sequence: str,
    include_ac: bool = True,
    include_abc: bool = True,
    include_controls: bool = True,
    positive_control_leader_sequence: str = "",
) -> FusionConstructResult:
    errors: list[str] = []
    b_clean = ""
    if b_sequence.strip():
        b_clean, b_errors = clean_protein_sequence(b_sequence, "B")
    else:
        b_errors = ["B 序列为空。"] if include_abc else []
    c_clean, c_errors = clean_protein_sequence(c_sequence, "C")
    positive_clean = ""
    if positive_control_leader_sequence.strip():
        positive_clean, positive_errors = clean_protein_sequence(positive_control_leader_sequence, "阳性对照 leader")
        errors.extend(positive_errors)
    errors.extend(b_errors)
    errors.extend(c_errors)
    if not include_ac and not include_abc and not include_controls:
        errors.append("至少需要选择 AC 或 ABC 中的一种构建。")
    if errors:
        return FusionConstructResult([], errors)

    rows: list[dict[str, object]] = []
    if include_controls:
        rows.append(_construct_row({}, "CONTROL", "C_ONLY", "", "", c_clean))
        if b_clean:
            rows.append(_construct_row({}, "CONTROL", "BC", "", b_clean, c_clean))
        if positive_clean:
            rows.append(_construct_row({}, "CONTROL", "POSITIVE_CONTROL_C", positive_clean, "", c_clean))

    for source in signal_rows:
        candidate_id = str(source.get("candidate_id", "")).strip()
        a_sequence = str(source.get("signal_peptide_sequence") or source.get("leader_sequence") or "").strip()
        a_clean, a_errors = clean_protein_sequence(a_sequence, f"A:{candidate_id or 'unknown'}")
        if a_errors:
            errors.extend(a_errors)
            continue
        if not candidate_id:
            candidate_id = f"candidate_{len(rows) + 1}"
        if include_ac:
            rows.append(_construct_row(source, candidate_id, "AC", a_clean, "", c_clean))
        if include_abc:
            rows.append(_construct_row(source, candidate_id, "ABC", a_clean, b_clean, c_clean))

    if not rows and not errors:
        errors.append("没有可用于生成融合构建的代表信号肽。")
    return FusionConstructResult(rows, errors)


def clean_protein_sequence(value: str, label: str) -> tuple[str, list[str]]:
    sequence = re.sub(r"[^A-Za-z]", "", str(value or "")).upper()
    if not sequence:
        return "", [f"{label} 序列为空。"]
    if not AA_PATTERN.fullmatch(sequence):
        invalid = "".join(sorted(set(sequence) - set("ACDEFGHIKLMNPQRSTVWY")))
        return "", [f"{label} 序列含有非标准氨基酸字符：{invalid}。"]
    return sequence, []


def fusion_constructs_to_fasta(rows: Iterable[dict[str, object]]) -> str:
    lines: list[str] = []
    for row in rows:
        construct_id = str(row.get("construct_id", "")).strip()
        source_id = str(row.get("candidate_id", "")).strip()
        construct_type = str(row.get("construct_type", "")).strip()
        sequence = str(row.get("construct_sequence", "")).strip()
        if not construct_id or not sequence:
            continue
        header = f"{construct_id}|source={source_id}|type={construct_type}|len={len(sequence)}"
        lines.append(f">{header}")
        lines.extend(sequence[index : index + 80] for index in range(0, len(sequence), 80))
    return "\n".join(lines) + ("\n" if lines else "")


def fusion_constructs_to_csv(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def import_localization_results(
    construct_rows: list[dict[str, object]],
    content: bytes | str,
    *,
    tool_name: str,
) -> LocalizationImportResult:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else str(content)
    table, errors = _read_delimited_table(text)
    if errors:
        return LocalizationImportResult(construct_rows, errors, 0)
    indexed = {_normalize_id(row.get("construct_id", "")): dict(row) for row in construct_rows}
    imported = 0
    for row in table:
        construct_id = _extract_first(row, LOCALIZATION_ID_COLUMNS)
        key = _find_construct_key(construct_id, indexed)
        if not key:
            continue
        localization = _extract_first(row, LOCALIZATION_COLUMNS)
        score = _extract_first(row, LOCALIZATION_SCORE_COLUMNS)
        raw = {f"{tool_name}_{_safe_column_name(k)}": v for k, v in row.items() if str(v).strip()}
        indexed[key].update(
            {
                f"{tool_name}_localization": localization,
                f"{tool_name}_score": score,
                f"{tool_name}_raw": "; ".join(f"{k}={v}" for k, v in raw.items()),
                **raw,
            }
        )
        indexed[key].update(score_construct(indexed[key]))
        imported += 1
    merged = [indexed[_normalize_id(row.get("construct_id", ""))] for row in construct_rows]
    errors = [] if imported else [f"没有在 {tool_name} 结果中匹配到 construct_id。"]
    return LocalizationImportResult(merged, errors, imported)


def summarize_localization(row: dict[str, object]) -> dict[str, object]:
    localization_text = " ".join(
        str(row.get(key, "")) for key in ("deeploc_localization", "busca_localization")
    ).lower()
    membrane_type_text = " ".join(
        str(row.get(key, "")) for key in ("deeploc_membrane_types", "busca_membrane_types")
    ).lower()
    extracellular_score = max(_safe_float(row.get("deeploc_extracellular")), _safe_float(row.get("busca_extracellular")))
    er_golgi_score = max(
        _safe_float(row.get("deeploc_endoplasmic_reticulum")),
        _safe_float(row.get("deeploc_golgi_apparatus")),
        _safe_float(row.get("busca_endoplasmic_reticulum")),
        _safe_float(row.get("busca_golgi_apparatus")),
    )
    membrane_score = max(
        _safe_float(row.get("deeploc_cell_membrane")),
        _safe_float(row.get("deeploc_transmembrane")),
        _safe_float(row.get("deeploc_lipid_anchor")),
        _safe_float(row.get("busca_cell_membrane")),
        _safe_float(row.get("busca_transmembrane")),
        _safe_float(row.get("busca_lipid_anchor")),
    )
    vacuole_score = max(_safe_float(row.get("deeploc_lysosome_vacuole")), _safe_float(row.get("busca_lysosome_vacuole")))
    soluble_score = max(_safe_float(row.get("deeploc_soluble")), _safe_float(row.get("busca_soluble")))
    return {
        "external_secreted_signal": _contains_any(localization_text, ("extracellular", "secreted", "outside"))
        or extracellular_score >= DEEPLOC_THRESHOLDS["extracellular"],
        "external_er_golgi_signal": _contains_any(localization_text, ("endoplasmic reticulum", "golgi", "secretory pathway"))
        or _safe_float(row.get("deeploc_endoplasmic_reticulum")) >= DEEPLOC_THRESHOLDS["endoplasmic_reticulum"]
        or _safe_float(row.get("deeploc_golgi_apparatus")) >= DEEPLOC_THRESHOLDS["golgi_apparatus"],
        "external_membrane_risk": _contains_any(localization_text, ("plasma membrane", "cell membrane"))
        or _contains_any(membrane_type_text, ("transmembrane", "lipid anchor", "lipid-anchored"))
        or _safe_float(row.get("deeploc_cell_membrane")) >= DEEPLOC_THRESHOLDS["cell_membrane"]
        or _safe_float(row.get("deeploc_transmembrane")) >= DEEPLOC_THRESHOLDS["transmembrane"]
        or _safe_float(row.get("deeploc_lipid_anchor")) >= DEEPLOC_THRESHOLDS["lipid_anchor"],
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
    signal_score = _safe_int(row.get("rules_score"))
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


def _construct_row(
    source: dict[str, object],
    candidate_id: str,
    construct_type: str,
    a_sequence: str,
    b_sequence: str,
    c_sequence: str,
) -> dict[str, object]:
    sequence = a_sequence + b_sequence + c_sequence
    row = {
        "construct_id": f"{candidate_id}_{construct_type}",
        "candidate_id": candidate_id,
        "construct_type": construct_type,
        "accession": source.get("accession", ""),
        "protein_name": source.get("protein_name", ""),
        "source_protein_route": source.get("source_protein_route", ""),
        "source_protein_evidence_level": source.get("source_protein_evidence_level", ""),
        "rules_score": source.get("rules_score", ""),
        "rules_n_region_positive_count": source.get("rules_n_region_positive_count", ""),
        "rules_h_region_max_hydrophobicity": source.get("rules_h_region_max_hydrophobicity", ""),
        "rules_c_region_small_neutral": source.get("rules_c_region_small_neutral", ""),
        "uspnet_prediction": source.get("uspnet_prediction", ""),
        "uspnet_cleavage_sequence": source.get("uspnet_cleavage_sequence", ""),
        "screening_status": source.get("screening_status", ""),
        "similar_group_size": source.get("similar_group_size", ""),
        "a_signal_peptide": a_sequence,
        "b_fixed_sequence": b_sequence,
        "c_target_sequence": c_sequence,
        "a_length": len(a_sequence),
        "b_length": len(b_sequence),
        "c_length": len(c_sequence),
        "construct_length": len(sequence),
        "construct_sequence": sequence,
    }
    row.update(_sequence_risks(sequence))
    row.update(_processing_notes(construct_type, a_sequence, b_sequence, c_sequence))
    row.update(score_construct(row))
    return row


def _sequence_risks(sequence: str) -> dict[str, object]:
    tail = sequence[-8:]
    c_tail = sequence[-35:]
    return {
        "has_er_retention_motif": tail.endswith(("KDEL", "HDEL")),
        "has_basic_processing_site": any(site in sequence for site in ("KR", "RR", "RK")),
        "kex2_site_count": sum(sequence.count(site) for site in ("KR", "RR", "RK")),
        "ste13_eaea_count": sequence.count("EAEA"),
        "has_vacuolar_sorting_motif": bool(re.search(r"NPIR|QRPL|Y..[LIVMFY]", sequence)),
        "gpi_anchor_like_risk": _max_hydrophobic_run(c_tail) >= 12,
        "low_complexity_fraction": round(_max_residue_fraction(sequence), 3),
        "internal_hydrophobic_run_max": _max_hydrophobic_run(sequence),
    }


def _processing_notes(
    construct_type: str,
    a_sequence: str,
    b_sequence: str,
    c_sequence: str,
) -> dict[str, object]:
    b_ends_with_kex2 = b_sequence.endswith(("KR", "RR"))
    b_has_pre_region_like_n_terminus = _max_hydrophobic_run(b_sequence[:25]) >= 8
    notes: list[str] = []
    if construct_type == "AC":
        notes.append("A 直接连接 C；重点复核 A 的信号肽切割后 C 端起始残基。")
    elif not b_sequence:
        notes.append("ABC 未提供 B 序列。")
    else:
        if b_ends_with_kex2:
            notes.append("B 末端带 Kex2 型碱性加工位点，适合作为 pro-region 辅助段候选。")
        else:
            notes.append("B 末端未见 KR/RR，需确认是否保留正确 Kex2 加工位点。")
        if b_has_pre_region_like_n_terminus:
            notes.append("B 的 N 端存在较长疏水段，可能包含 pre-region；需避免与 A 形成双信号肽。")
        else:
            notes.append("B 未显示明显 N 端疏水 pre-region，更像去除 pre-region 后的 pro 区片段。")
    if c_sequence.startswith(("KR", "RR")):
        notes.append("C 起始处也含碱性位点，需人工复核是否造成额外切割。")
    return {
        "b_ends_with_kex2_site": b_ends_with_kex2,
        "b_pre_region_like": b_has_pre_region_like_n_terminus,
        "a_c_junction": (a_sequence[-6:] + "|" + c_sequence[:6]) if c_sequence else "",
        "a_b_junction": (a_sequence[-6:] + "|" + b_sequence[:6]) if b_sequence else "",
        "b_c_junction": (b_sequence[-6:] + "|" + c_sequence[:6]) if b_sequence and c_sequence else "",
        "processing_site_note": " ".join(notes),
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
        if _truthy(row.get("b_ends_with_kex2_site")):
            score += 15
        if _truthy(row.get("b_pre_region_like")):
            score -= 25
    elif construct_type == "POSITIVE_CONTROL_C":
        score = 75
    else:
        score = 50
    if _truthy(row.get("has_er_retention_motif")):
        score -= 20
    if _safe_int(row.get("internal_hydrophobic_run_max")) >= 18:
        score -= 10
    return max(0, min(100, score))


def _risk_score(row: dict[str, object], localization: dict[str, object]) -> int:
    score = 0
    if _truthy(row.get("has_er_retention_motif")):
        score += 25
    if _truthy(row.get("has_vacuolar_sorting_motif")):
        score += 15
    if _truthy(row.get("gpi_anchor_like_risk")):
        score += 20
    if _safe_int(row.get("internal_hydrophobic_run_max")) >= 18:
        score += 20
    if _safe_float(row.get("low_complexity_fraction")) >= 0.28:
        score += 10
    if localization["external_membrane_risk"]:
        score += 25
    if localization["external_vacuole_risk"]:
        score += 25
    return min(100, score)


def _localization_probability_score(row: dict[str, object], localization: dict[str, object]) -> float:
    extracellular = _safe_float(localization.get("external_extracellular_probability"))
    soluble = _safe_float(localization.get("external_soluble_probability"))
    er_golgi = _safe_float(localization.get("external_er_golgi_probability"))
    membrane = _safe_float(localization.get("external_membrane_probability"))
    vacuole = _safe_float(localization.get("external_vacuole_probability"))
    score = 15 + extracellular * 55 + soluble * 15 + er_golgi * 10 - membrane * 22 - vacuole * 18
    if _contains_any(str(row.get("deeploc_localization", "")).lower(), ("extracellular", "secreted")):
        score += 8
    if _contains_any(str(row.get("deeploc_membrane_types", "")).lower(), ("soluble",)):
        score += 4
    return round(max(0, min(100, score)), 1)


def _signal_detail_score(row: dict[str, object]) -> float:
    score = _safe_float(row.get("rules_score")) * 0.45
    a_length = _safe_int(row.get("a_length"))
    if 17 <= a_length <= 30:
        score += 12
    elif 14 <= a_length <= 35:
        score += 7
    else:
        score -= 6

    hydrophobicity = _safe_float(row.get("rules_h_region_max_hydrophobicity"))
    if 2.0 <= hydrophobicity <= 3.4:
        score += 12
    elif 1.7 <= hydrophobicity <= 3.8:
        score += 7
    elif hydrophobicity:
        score -= 5

    n_positive = _safe_int(row.get("rules_n_region_positive_count"))
    if 1 <= n_positive <= 3:
        score += 8
    elif n_positive > 3:
        score += 3

    if _truthy(row.get("rules_c_region_small_neutral")):
        score += 8
    if str(row.get("uspnet_prediction", "")).strip().upper() == "SP":
        score += 8
    if str(row.get("uspnet_cleavage_sequence", "")).strip():
        score += 5
    if _safe_int(row.get("similar_group_size")) > 1:
        score += min(6, _safe_int(row.get("similar_group_size")))
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
    construct_bonus = 4 if str(row.get("construct_type", "")) == "ABC" and _truthy(row.get("b_ends_with_kex2_site")) else 0
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


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _max_hydrophobic_run(sequence: str) -> int:
    hydrophobic = set("AILMFWYV")
    longest = current = 0
    for aa in sequence:
        if aa in hydrophobic:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _max_residue_fraction(sequence: str) -> float:
    if not sequence:
        return 0.0
    return max(sequence.count(aa) for aa in set(sequence)) / len(sequence)


def _safe_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _read_delimited_table(text: str) -> tuple[list[dict[str, str]], list[str]]:
    if not text.strip():
        return [], ["导入文件为空。"]
    sample = text[:2048]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]
    except csv.Error as exc:
        return [], [f"定位结果读取失败：{exc}"]
    if not reader.fieldnames:
        return [], ["导入文件没有表头。"]
    return rows, []


def _extract_first(row: dict[str, str], candidates: tuple[str, ...]) -> str:
    normalized = {_safe_column_name(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalized.get(_safe_column_name(candidate), "")
        if str(value).strip():
            return str(value).strip()
    return ""


def _safe_column_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _normalize_id(value: object) -> str:
    return str(value or "").strip().split("|", 1)[0]


def _find_construct_key(value: object, indexed: dict[str, dict[str, object]]) -> str:
    for key in _localization_id_candidates(value):
        if key in indexed:
            return key
    return ""


def _localization_id_candidates(value: object) -> list[str]:
    normalized = _normalize_id(value)
    if not normalized:
        return []
    candidates = [normalized]
    flattened = re.split(r"_source_", normalized, maxsplit=1, flags=re.IGNORECASE)[0]
    if flattened and flattened not in candidates:
        candidates.append(flattened)
    return candidates


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
