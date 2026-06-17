from __future__ import annotations

import csv
from pathlib import Path

from sigscout.adapters.uspnet import USPNetPrediction, USPNetRunResult
from sigscout.core.models import UniProtCandidateLibraryResult
from sigscout.services.screening import (
    SignalPeptideScreeningService,
    choose_representative,
    cluster_similar_signal_peptides,
    signal_peptide_identity,
)


def test_signal_peptide_screening_compares_rules_and_uspnet(tmp_path: Path) -> None:
    service = SignalPeptideScreeningService(
        tmp_path,
        library_service=FakeLibraryService(),
        uspnet_adapter=FakeUSPNetAdapter(),
    )

    result = service.screen_uniprot_candidates(max_records=2)

    assert result.success is True
    assert result.summary["uniprot_initial_hits"] == 2
    assert result.summary["rules_high_priority"] == 1
    assert result.summary["uspnet_completed"] == 2
    assert result.summary["uspnet_passed"] == 1
    assert result.summary["consensus_passed"] == 1
    assert result.comparison_csv and result.comparison_csv.exists()
    assert result.representatives_csv and result.representatives_csv.exists()
    assert result.representatives_fasta and result.representatives_fasta.exists()


def test_signal_peptide_similarity_clustering_keeps_representatives() -> None:
    rows = [
        _screened_row("A", "MKTLLALALALA", rules_score=80),
        _screened_row("B", "MKTLLALALVLA", rules_score=90),
        _screened_row("C", "MNNNNNNNNNNN", rules_score=100),
    ]

    clustered = cluster_similar_signal_peptides(rows, identity_threshold=0.80)
    by_id = {row["candidate_id"]: row for row in clustered}

    assert signal_peptide_identity("MKTLLALALALA", "MKTLLALALVLA") >= 0.80
    assert by_id["A"]["representative_id"] == "B"
    assert by_id["B"]["is_representative"] is True
    assert by_id["A"]["similar_group_size"] == 2
    assert by_id["C"]["similar_group_size"] == 1


def test_signal_peptide_clustering_does_not_hide_exact_duplicates() -> None:
    rows = [
        _screened_row("A", "MKTLLALALALA"),
        _screened_row("A_DUP", "MKTLLALALALA"),
    ]

    clustered = cluster_similar_signal_peptides(rows, identity_threshold=0.80)

    assert {row["similarity_group_id"] for row in clustered} == {"SPG_001", "SPG_002"}
    assert all(row["similar_group_size"] == 1 for row in clustered)


def test_representative_priority_prefers_consensus_then_uspnet() -> None:
    consensus = _screened_row("CONSENSUS", "MKTLLALALALA", consensus_pass=True, uspnet_pass=True, rules_score=75)
    uspnet = _screened_row("USPNET", "MKTLLALALVLA", consensus_pass=False, uspnet_pass=True, rules_score=100)
    rules = _screened_row("RULES", "MKTLLALALILA", consensus_pass=False, uspnet_pass=False, rules_score=100)

    representative = choose_representative([rules, uspnet, consensus])

    assert representative["candidate_id"] == "CONSENSUS"


def test_screening_writes_representative_outputs(tmp_path: Path) -> None:
    service = SignalPeptideScreeningService(
        tmp_path,
        library_service=SimilarLibraryService(),
        uspnet_adapter=FakeMissingUSPNetAdapter(),
    )

    result = service.screen_uniprot_candidates(max_records=3)

    assert result.summary["representative_candidate_count"] == 1
    assert result.summary["similar_candidates_collapsed_count"] == 1
    assert result.representatives_csv and result.representatives_csv.exists()
    assert result.representatives_fasta and result.representatives_fasta.exists()
    with result.representatives_csv.open(encoding="utf-8-sig", newline="") as handle:
        representative_rows = list(csv.DictReader(handle))
    assert len(representative_rows) == 1
    assert result.representatives_fasta.read_text(encoding="utf-8").count(">") == 1


class FakeLibraryService:
    def discover_uniprot_candidate_library(self, **_kwargs):
        rows = [
            _library_row("OPN_UNIPROT_X12345", "X12345", "MKALLLALLALAAASAGA", "Secreted test protein"),
            _library_row("OPN_UNIPROT_LOW", "LOW", "MNNNNNNNNNNNNNNNNN", "Low complexity protein"),
        ]
        return UniProtCandidateLibraryResult(
            rows=rows,
            source_url="https://rest.uniprot.org/fixture",
            errors=[],
            initial_hit_count=2,
            fetched_record_count=2,
            extracted_signal_count=2,
            deduplicated_count=2,
        )


class SimilarLibraryService:
    def discover_uniprot_candidate_library(self, **_kwargs):
        rows = [
            _library_row("OPN_UNIPROT_SIM_A", "SIM_A", "MKTLLALALALAASAGA", "Similar protein A"),
            _library_row("OPN_UNIPROT_SIM_B", "SIM_B", "MKTLLALALALAAVAGA", "Similar protein B"),
            _library_row("OPN_UNIPROT_LOW", "LOW", "MNNNNNNNNNNNNNNNNN", "Low complexity protein"),
        ]
        return UniProtCandidateLibraryResult(
            rows=rows,
            source_url="https://rest.uniprot.org/similar-fixture",
            errors=[],
            initial_hit_count=3,
            fetched_record_count=3,
            extracted_signal_count=3,
            deduplicated_count=3,
        )


class FakeUSPNetAdapter:
    def run(self, _fasta_file: Path, output_dir: Path, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        return USPNetRunResult(
            available=True,
            success=True,
            message="ok",
            output_dir=output_dir,
            predictions=[
                USPNetPrediction(
                    candidate_id="OPN_UNIPROT_X12345",
                    predicted_type="SP",
                    predicted_cleavage="MKALLLALLALAAASAGA",
                    passed=True,
                    raw_sequence="MKALLLALLALAAASAGA",
                ),
                USPNetPrediction(
                    candidate_id="OPN_UNIPROT_LOW",
                    predicted_type="NO_SP",
                    predicted_cleavage="",
                    passed=False,
                    raw_sequence="MNNNNNNNNNNNNNNNNN",
                ),
            ],
        )


class FakeMissingUSPNetAdapter:
    def run(self, _fasta_file: Path, output_dir: Path, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        return USPNetRunResult(
            available=False,
            success=False,
            message="未检测到 USPNet 本地仓库。",
            output_dir=output_dir,
            predictions=[],
        )


def _library_row(candidate_id: str, accession: str, signal: str, protein_name: str) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "accession": accession,
        "uniprot_id": f"{accession}_PICPA",
        "protein_name": protein_name,
        "organism_name": "Komagataella phaffii",
        "protein_sequence": signal + "QREST",
        "protein_length": len(signal) + 5,
        "uniprot_signal_start": 1,
        "uniprot_signal_end": len(signal),
        "leader_sequence": signal,
        "signal_peptide_sequence": signal,
        "category": "pichia_native_signal",
        "processing_route": "signal peptidase only",
        "source_note": f"UniProt {accession}",
        "rationale": "fixture",
        "caution": "fixture",
        "leader_length": len(signal),
        "signal_peptide_length": len(signal),
        "library_stage": "外部发现草案",
        "source_type": "UniProt",
        "already_in_formal_library": False,
        "uniprot_reviewed": False,
    }


def _screened_row(
    candidate_id: str,
    signal: str,
    *,
    consensus_pass: bool = False,
    uspnet_pass: bool = False,
    rules_score: int = 100,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "signal_peptide_sequence": signal,
        "consensus_pass": consensus_pass,
        "uspnet_pass": uspnet_pass,
        "uspnet_prediction": "SP" if uspnet_pass else "NO_SP",
        "rules_high_priority": rules_score >= 90,
        "rules_score": rules_score,
        "recommended_for_draft_library": True,
        "uniprot_reviewed": False,
    }
