from __future__ import annotations

from sigscout.services.inputs import CsvCandidateInputProvider, StaticTargetProteinInputProvider
from sigscout.services.library import SignalPeptideLibraryService


def test_csv_candidate_input_provider_loads_library_candidates() -> None:
    content = (
        "candidate_id,leader_sequence,signal_peptide_sequence,category,processing_route,"
        "source_note,rationale,caution\n"
        "CSV_SIGNAL_001,mkfaistlliilqaaavfaa,MKFAISTLLIILQAAAVFAA,"
        "pichia_native_signal,signal peptidase only,manual,"
        "candidate from uploaded file,needs wet-lab confirmation\n"
    )
    provider = CsvCandidateInputProvider(content=content, source_name="uploaded csv")

    batch = provider.load_candidates()
    service = SignalPeptideLibraryService.from_input_provider(provider)

    assert batch.errors == []
    assert batch.source_name == "uploaded csv"
    assert batch.candidates[0].candidate_id == "CSV_SIGNAL_001"
    assert batch.candidates[0].leader_sequence == "MKFAISTLLIILQAAAVFAA"
    assert service.input_errors == []
    assert service.input_source_name == "uploaded csv"
    assert service.library_rows()[0]["signal_peptide_length"] == 20


def test_csv_candidate_input_provider_reports_input_errors() -> None:
    provider = CsvCandidateInputProvider(content="candidate_id,leader_sequence\nBROKEN,ABC\n")

    batch = provider.load_candidates()

    assert batch.candidates == []
    assert "缺少候选输入必填列" in batch.errors[0]


def test_static_target_protein_input_provider_normalizes_sequence() -> None:
    provider = StaticTargetProteinInputProvider(
        protein_id="OPN",
        mature_sequence="ipvkqadsgs\nseek",
        source_name="docx",
    )

    result = provider.load_target()

    assert result.errors == []
    assert result.target is not None
    assert result.target.mature_sequence == "IPVKQADSGSSEEK"
