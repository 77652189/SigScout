from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from sigscout.core.models import AA_PATTERN, SignalPeptideCandidate


REQUIRED_CANDIDATE_INPUT_COLUMNS = [
    "candidate_id",
    "leader_sequence",
    "signal_peptide_sequence",
    "category",
    "processing_route",
    "source_note",
    "rationale",
    "caution",
]


@dataclass(frozen=True)
class CandidateInputBatch:
    source_name: str
    candidates: list[SignalPeptideCandidate]
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class CandidateInputProvider(Protocol):
    source_name: str

    def load_candidates(self) -> CandidateInputBatch:
        """Return signal peptide candidates from a UI, file, API, or preset."""


@dataclass(frozen=True)
class TargetProteinInput:
    protein_id: str
    mature_sequence: str
    source_name: str
    description: str = ""


@dataclass(frozen=True)
class TargetProteinInputResult:
    source_name: str
    target: TargetProteinInput | None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class TargetProteinInputProvider(Protocol):
    source_name: str

    def load_target(self) -> TargetProteinInputResult:
        """Return one target protein sequence for downstream construct planning."""


def clean_amino_acid_sequence(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def is_standard_amino_acid_sequence(value: object) -> bool:
    sequence = clean_amino_acid_sequence(value)
    return bool(sequence and AA_PATTERN.fullmatch(sequence))
