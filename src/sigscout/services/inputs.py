from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from pydantic import ValidationError

from sigscout.core.inputs import (
    CandidateInputBatch,
    TargetProteinInput,
    TargetProteinInputResult,
    clean_amino_acid_sequence,
    is_standard_amino_acid_sequence,
    REQUIRED_CANDIDATE_INPUT_COLUMNS,
)
from sigscout.core.models import SignalPeptideCandidate


@dataclass(frozen=True)
class StaticCandidateInputProvider:
    candidates: Iterable[SignalPeptideCandidate]
    source_name: str = "static candidates"

    def load_candidates(self) -> CandidateInputBatch:
        return CandidateInputBatch(
            source_name=self.source_name,
            candidates=list(self.candidates),
        )


@dataclass(frozen=True)
class CsvCandidateInputProvider:
    path: Path | None = None
    content: bytes | str | None = None
    source_name: str = "CSV candidate input"

    def load_candidates(self) -> CandidateInputBatch:
        text, read_errors = self._read_text()
        if read_errors:
            return CandidateInputBatch(self.source_name, [], read_errors)

        reader = csv.DictReader(io.StringIO(text))
        missing = _missing_columns(reader.fieldnames or [])
        if missing:
            return CandidateInputBatch(self.source_name, [], missing)

        candidates: list[SignalPeptideCandidate] = []
        errors: list[str] = []
        seen_ids: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            candidate, row_errors = _candidate_from_row(row, row_number, seen_ids)
            if row_errors:
                errors.extend(row_errors)
                continue
            if candidate is not None:
                seen_ids.add(candidate.candidate_id)
                candidates.append(candidate)

        return CandidateInputBatch(
            source_name=self.source_name,
            candidates=candidates,
            errors=errors,
            metadata={"path": str(self.path) if self.path else ""},
        )

    def _read_text(self) -> tuple[str, list[str]]:
        if self.content is not None:
            if isinstance(self.content, bytes):
                return self.content.decode("utf-8-sig"), []
            return str(self.content), []
        if self.path is None:
            return "", ["没有提供候选输入文件或内容。"]
        try:
            return self.path.read_text(encoding="utf-8-sig"), []
        except OSError as exc:
            return "", [f"候选输入文件读取失败：{exc}"]


@dataclass(frozen=True)
class StaticTargetProteinInputProvider:
    protein_id: str
    mature_sequence: str
    source_name: str = "manual target protein"
    description: str = ""

    def load_target(self) -> TargetProteinInputResult:
        sequence = clean_amino_acid_sequence(self.mature_sequence)
        if not is_standard_amino_acid_sequence(sequence):
            return TargetProteinInputResult(
                source_name=self.source_name,
                target=None,
                errors=["目标蛋白序列为空，或包含非标准氨基酸字母。"],
            )
        return TargetProteinInputResult(
            source_name=self.source_name,
            target=TargetProteinInput(
                protein_id=self.protein_id,
                mature_sequence=sequence,
                source_name=self.source_name,
                description=self.description,
            ),
        )


def _missing_columns(columns: Iterable[str]) -> list[str]:
    present = set(columns)
    missing = [column for column in REQUIRED_CANDIDATE_INPUT_COLUMNS if column not in present]
    if not missing:
        return []
    return [f"缺少候选输入必填列：{', '.join(missing)}"]


def _candidate_from_row(
    row: Mapping[str, object],
    row_number: int,
    seen_ids: set[str],
) -> tuple[SignalPeptideCandidate | None, list[str]]:
    cleaned = {key: _clean(row.get(key, "")) for key in row}
    candidate_id = cleaned.get("candidate_id", "")
    leader = clean_amino_acid_sequence(cleaned.get("leader_sequence", ""))
    signal = clean_amino_acid_sequence(cleaned.get("signal_peptide_sequence", ""))

    errors: list[str] = []
    if not candidate_id:
        errors.append(f"第 {row_number} 行：candidate_id 不能为空。")
    if candidate_id in seen_ids:
        errors.append(f"第 {row_number} 行：candidate_id 在输入文件中重复：{candidate_id}")
    if not is_standard_amino_acid_sequence(leader):
        errors.append(f"第 {row_number} 行：leader_sequence 只能包含标准氨基酸单字母代码。")
    if not is_standard_amino_acid_sequence(signal):
        errors.append(f"第 {row_number} 行：signal_peptide_sequence 只能包含标准氨基酸单字母代码。")
    if leader and signal and signal not in leader:
        errors.append(f"第 {row_number} 行：signal_peptide_sequence 应包含在 leader_sequence 中。")
    if errors:
        return None, errors

    payload: dict[str, object] = {
        "candidate_id": candidate_id,
        "leader_sequence": leader,
        "signal_peptide_sequence": signal,
        "category": cleaned.get("category", ""),
        "processing_route": cleaned.get("processing_route", ""),
        "source_note": cleaned.get("source_note", ""),
        "rationale": cleaned.get("rationale", ""),
        "caution": cleaned.get("caution", ""),
    }
    for key in (
        "category_label",
        "library_stage",
        "source_type",
        "accession",
        "uniprot_id",
        "protein_name",
        "organism_name",
        "protein_sequence",
    ):
        if cleaned.get(key, ""):
            payload[key] = cleaned[key]
    for key in (
        "leader_length",
        "signal_peptide_length",
        "construct_length",
        "protein_length",
        "uniprot_signal_start",
        "uniprot_signal_end",
    ):
        value = _optional_int(cleaned.get(key, ""))
        if value is not None:
            payload[key] = value
    for key in ("already_in_formal_library", "uniprot_reviewed"):
        if cleaned.get(key, ""):
            payload[key] = _optional_bool(cleaned[key])

    try:
        return SignalPeptideCandidate(**payload), []
    except ValidationError as exc:
        return None, [f"第 {row_number} 行：候选记录格式错误：{exc}"]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _optional_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "是"}
