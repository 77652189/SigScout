from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sigscout.core.models import AA_PATTERN
from sigscout.services.exports import records_to_fasta, rows_to_csv
from sigscout.services.fusion_scoring import score_construct


CONSTRUCT_TYPES = ("AC", "ABC")
CONSTRUCT_SCHEMA_VERSION = 2
DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE = "APVNTTTEDETAQIPAEAVIGYSDLEGDFDVAVLPFSNSTNNGLLFINTTIASIAAKEEGVSLEKR"
DEFAULT_OPN_TARGET_SEQUENCE = (
    "IPVKQADSGSSEEKQLYNKYPDAVATWLNPDPSQKQNLLAPQNAVSSEETNDFKQETLPSKSNESHDHMDDMDDEDDDDHVDSQDSIDSNDSDDVDDTDDSHQSDESHHSDESDELVTDFPTDLPATEVFTPVVPTVDTYDGRGDSVVYGLRSKSKKFRRPDIQYPDATDEDITSHMESEELNGAYKAIPVAQDLNAPSDWDSRGKDSYETSQLDDQSAETHSHKQSRLYKRKANDESNEHSDVIDSQELSKVSREFHSHEFHSHEDMLVVDPKSKEEDKHLKFRISHELDSASSEVN"
)
DEFAULT_HLF_REFERENCE_SEQUENCE = (
    "MKLVFLVLLFLGALGLCLAGRRRSVQWCAVSQPEATKCFQWQRNMRKVRGPPVSCIKRDSPIQCIQAIAENRADAVTLDGGFIYEAGLAPYKLRPVAAEVYGTERQPRTHYYAVAVVKKGGSFQLNELQGLKSCHTGLRRTAGWNVPIGTLRPFLNWTGPPEPIEAAVARFFSASCVPGADKGQFPNLCRLCAGTGENKCAFSSQEPYFSYSGAFKCLRDGAGDVAFIRESTVFEDLSDEAERDEYELLCPDNTRKPVDKFKDCHLARVPSHAVVARSVNGKEDAIWNLLRQAQEKFGKDKSPKFQLFGSPSGQKDLLFKDSAIGFSRVPPRIDSGLYLGSGYFTAIQNLRKSEEEVAARRARVVWCAVGEQELRKCNQWSGLSEGSVTCSSASTTEDCIALVLKGEADAMSLDGGYVYTAGKCGLVPVLAENYKSQQSSDPDPNCVDRPVEGYLAVAVVRRSDTSLTWNSVKGKKSCHTAVDRTAGWNIPMGLLFNQTGSCKFDEYFSQSCAPGSDPRSNLCALCIGDEQGENKCVPNSNERYYGYTGAFRCLAENAGDVAFVKDVTVLQNTDGNNNEAWAKDLKLADFALLCLDGKRKPVTEARSCHLAMAPNHAVVSRMDKVERLKQVLLHQQAKFGRNGSDCPDKFCLFQSETKNLLFNDNTECLARLHGKTTYEKYLGPQYVAGITNLKKCSTSPLLEACEFLRK"
)
DEFAULT_HLF_TARGET_SEQUENCE = DEFAULT_HLF_REFERENCE_SEQUENCE[19:]


@dataclass(frozen=True)
class FusionConstructResult:
    rows: list[dict[str, object]]
    errors: list[str]


@dataclass(frozen=True)
class FusionTargetPreset:
    key: str
    label: str
    sequence: str
    source: str
    note: str


FUSION_TARGET_PRESETS = {
    "opn": FusionTargetPreset(
        key="opn",
        label="OPN / 骨桥蛋白",
        sequence=DEFAULT_OPN_TARGET_SEQUENCE,
        source="用户提供的 OPN 固定 C 序列",
        note="当前默认目标蛋白；用于骨桥蛋白分泌构建评估。",
    ),
    "hlf": FusionTargetPreset(
        key="hlf",
        label="hLF / 人乳铁蛋白",
        sequence=DEFAULT_HLF_TARGET_SEQUENCE,
        source="UniProtKB reviewed P02788; reference also aligned with Evaluation of the potential food allergy risks of human lactoferrin expressed in Komagataella phaffii (2024)",
        note="默认 C 使用 P02788 去除 native signal peptide 1-19 后的成熟人乳铁蛋白区域，避免与候选毕赤酵母信号肽 A 形成双信号肽。",
    ),
}


def build_fusion_constructs(
    signal_rows: Iterable[dict[str, object]],
    *,
    b_sequence: str,
    c_sequence: str,
    target_key: str = "custom",
    target_label: str = "Custom target",
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
        rows.append(_construct_row({}, "CONTROL", "C_ONLY", "", "", c_clean, target_key, target_label))
        if b_clean:
            rows.append(_construct_row({}, "CONTROL", "BC", "", b_clean, c_clean, target_key, target_label))
        if positive_clean:
            rows.append(_construct_row({}, "CONTROL", "POSITIVE_CONTROL_C", positive_clean, "", c_clean, target_key, target_label))

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
            rows.append(_construct_row(source, candidate_id, "AC", a_clean, "", c_clean, target_key, target_label))
        if include_abc:
            rows.append(_construct_row(source, candidate_id, "ABC", a_clean, b_clean, c_clean, target_key, target_label))

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
    records = []
    for row in rows:
        construct_id = str(row.get("construct_id", "")).strip()
        source_id = str(row.get("candidate_id", "")).strip()
        construct_type = str(row.get("construct_type", "")).strip()
        target_key = str(row.get("target_key", "")).strip()
        sequence = str(row.get("construct_sequence", "")).strip()
        if not construct_id or not sequence:
            continue
        header = f"{construct_id}|source={source_id}|type={construct_type}|target={target_key}|len={len(sequence)}"
        records.append((header, sequence))
    return records_to_fasta(records)


def fusion_constructs_to_csv(rows: list[dict[str, object]]) -> str:
    return rows_to_csv(rows)


def save_fusion_construct_manifest(
    rows: list[dict[str, object]],
    output_dir: Path,
    target_key: str,
) -> Path:
    errors = validate_fusion_constructs(rows, target_key)
    if errors:
        raise ValueError(" ".join(errors))
    path = _fusion_construct_manifest_path(output_dir, target_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(fusion_constructs_to_csv(rows), encoding="utf-8")
    temporary.replace(path)
    return path


def load_fusion_construct_manifest(
    output_dir: Path,
    target_key: str,
) -> FusionConstructResult:
    path = _fusion_construct_manifest_path(output_dir, target_key)
    if not path.exists():
        return FusionConstructResult([], [])
    try:
        reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
        rows = [dict(row) for row in reader]
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return FusionConstructResult([], [f"构建清单读取失败：{exc}"])
    errors = validate_fusion_constructs(rows, target_key)
    return FusionConstructResult([] if errors else rows, errors)


def _fusion_construct_manifest_path(output_dir: Path, target_key: str) -> Path:
    safe_target = _safe_id_component(target_key, "target").lower()
    return Path(output_dir) / f"fusion_constructs_{safe_target}.csv"


def validate_fusion_constructs(
    rows: Iterable[dict[str, object]],
    target_key: str,
) -> list[str]:
    errors: list[str] = []
    safe_target = _safe_id_component(target_key, "target").lower()
    for row in rows:
        construct_id = str(row.get("construct_id", "")).strip()
        if str(row.get("construct_schema_version", "")).strip() != str(CONSTRUCT_SCHEMA_VERSION):
            errors.append("构建清单使用旧版 ID；请重新生成 FASTA 并重新计算定位结果。")
            continue
        if str(row.get("target_key", "")).strip().lower() != str(target_key).strip().lower():
            errors.append("构建清单目标与当前目标不一致；请切换目标或重新生成 FASTA。")
            continue
        sequence = str(row.get("construct_sequence", "")).strip().upper()
        try:
            sequence_sha1 = hashlib.sha1(sequence.encode("ascii")).hexdigest() if sequence else ""
        except UnicodeEncodeError:
            sequence_sha1 = ""
        if not sequence or str(row.get("construct_sequence_sha1", "")).strip().lower() != sequence_sha1:
            errors.append("构建序列摘要不一致；请重新生成 FASTA 并重新计算定位结果。")
            continue
        expected_id = _build_construct_id(
            target_key,
            row.get("candidate_id", ""),
            row.get("construct_type", ""),
            sequence_sha1,
        )
        if construct_id != expected_id or not construct_id.startswith(f"{safe_target}__"):
            errors.append("构建 ID 与目标或序列摘要不一致；请重新生成 FASTA 并重新计算定位结果。")
    return list(dict.fromkeys(errors))


def _construct_row(
    source: dict[str, object],
    candidate_id: str,
    construct_type: str,
    a_sequence: str,
    b_sequence: str,
    c_sequence: str,
    target_key: str,
    target_label: str,
) -> dict[str, object]:
    sequence = a_sequence + b_sequence + c_sequence
    sequence_sha1 = hashlib.sha1(sequence.encode("ascii")).hexdigest()
    row = {
        "construct_id": _build_construct_id(target_key, candidate_id, construct_type, sequence_sha1),
        "construct_schema_version": CONSTRUCT_SCHEMA_VERSION,
        "construct_sequence_sha1": sequence_sha1,
        "candidate_id": candidate_id,
        "construct_type": construct_type,
        "target_key": target_key,
        "target_label": target_label,
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


def _safe_id_component(value: object, fallback: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("_.-")
    return safe or fallback


def _build_construct_id(
    target_key: object,
    candidate_id: object,
    construct_type: object,
    sequence_sha1: str,
) -> str:
    safe_target = _safe_id_component(target_key, "target").lower()
    safe_candidate = _safe_id_component(candidate_id, "candidate")
    safe_type = _safe_id_component(construct_type, "construct")
    return f"{safe_target}__{safe_candidate}__{safe_type}__{sequence_sha1[:12]}"


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
    elif construct_type in {"ABC", "BC"} and not b_sequence:
        notes.append(f"{construct_type} 未提供 B 序列。")
    elif construct_type in {"ABC", "BC"}:
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
