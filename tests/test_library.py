from __future__ import annotations

from sigscout.adapters.uniprot import UniProtSignalPeptideSource, _next_link
from sigscout.presets.opn import opn_library_service
from sigscout.services.library import SignalPeptideLibraryService


def test_opn_preset_library_contains_current_candidates() -> None:
    service = opn_library_service()
    rows = service.library_rows()
    by_id = {row["candidate_id"]: row for row in rows}

    assert len(rows) == 7
    assert by_id["OPN_PPA_PASCHR3_0030"]["library_stage"] == "首轮推荐"
    assert by_id["OPN_ALPHA_FULL_PROJECT"]["source_type"] == "项目基线"
    assert service.candidate_prefix == "OPN_UNIPROT"


def test_signal_peptide_library_validates_import_csv() -> None:
    service = SignalPeptideLibraryService()
    content = (
        "candidate_id,leader_sequence,signal_peptide_sequence,category,processing_route,"
        "source_note,rationale,caution\n"
        "NEW_SIGNAL_001,MKFAISTLLIILQAAAVFAA,MKFAISTLLIILQAAAVFAA,"
        "pichia_native_signal,signal peptidase only,UniProt candidate,"
        "adds a new Pichia-native candidate,needs external confirmation\n"
    ).encode("utf-8")

    result = service.validate_import_csv(content)

    assert result.valid is True
    assert result.rows[0]["candidate_id"] == "NEW_SIGNAL_001"
    assert service.merged_draft_csv(result.rows).startswith(b"\xef\xbb\xbf")


def test_uniprot_source_extracts_signal_features_and_duplicates() -> None:
    source = UniProtSignalPeptideSource(candidate_prefix="OPN_UNIPROT")
    items = [
        _uniprot_item("X12345", "TEST1_PICPA", "Secreted test protein 1"),
        _uniprot_item("Y12345", "TEST2_PICPA", "Secreted test protein 2"),
    ]

    rows, errors, extracted_count, duplicate_rows = source.rows_from_items(items, exclude_existing=False)

    assert errors == []
    assert extracted_count == 2
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == "OPN_UNIPROT_X12345"
    assert rows[0]["signal_peptide_sequence"] == "MKTLLALALALAAPAA"
    assert len(duplicate_rows) == 1
    assert duplicate_rows[0]["duplicate_of"] == "OPN_UNIPROT_X12345"


def test_uniprot_next_link_parser_handles_commas_inside_url() -> None:
    header = (
        '<https://rest.uniprot.org/uniprotkb/search?format=json&'
        'fields=accession,id,protein_name,organism_name,ft_signal,sequence&'
        'cursor=abc&size=100>; rel="next"'
    )

    assert _next_link(header) == (
        "https://rest.uniprot.org/uniprotkb/search?format=json&"
        "fields=accession,id,protein_name,organism_name,ft_signal,sequence&"
        "cursor=abc&size=100"
    )


def _uniprot_item(accession: str, uniprot_id: str, protein_name: str) -> dict:
    return {
        "primaryAccession": accession,
        "uniProtkbId": uniprot_id,
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "organism": {"scientificName": "Komagataella pastoris"},
        "proteinDescription": {
            "recommendedName": {"fullName": {"value": protein_name}}
        },
        "sequence": {"value": "MKTLLALALALAAPAAQREST"},
        "features": [
            {
                "type": "Signal",
                "location": {"start": {"value": 1}, "end": {"value": 16}},
            }
        ],
    }

