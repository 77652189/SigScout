from __future__ import annotations

from sigscout.adapters.uniprot import UniProtSignalPeptideSource, _next_link
from sigscout.services.library import SignalPeptideLibraryService


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
    assert "source_protein_route" not in rows[0]
    assert rows[0]["source_protein_annotation_status"] == "未评估"
    assert "Secreted" in rows[0]["source_protein_location"]
    assert "SL-0243" in rows[0]["source_protein_location_ids"]
    assert "GO:0005576 extracellular region" in rows[0]["source_protein_go_terms"]
    assert "GO:0005576" in rows[0]["source_protein_go_ids"]
    assert "ECO:0000269" in rows[0]["source_protein_location_evidence_codes"]
    assert "source_protein_uniprot_location_json" in rows[0]
    assert len(duplicate_rows) == 1
    assert duplicate_rows[0]["duplicate_of"] == "OPN_UNIPROT_X12345"


def test_uniprot_source_keeps_membrane_evidence_without_classifying() -> None:
    source = UniProtSignalPeptideSource(candidate_prefix="PICHIA_UNIPROT")
    item = _uniprot_item("M12345", "MEMBRANE_PICPA", "GPI-anchored cell wall protein")
    item["features"].append({"type": "Transmembrane", "description": "Helical"})
    item["keywords"] = [{"name": "Membrane"}]

    rows, _errors, _extracted_count, _duplicate_rows = source.rows_from_items([item], exclude_existing=False)

    assert "source_protein_route" not in rows[0]
    assert rows[0]["source_protein_annotation_status"] == "未评估"
    assert "Transmembrane" in rows[0]["source_protein_feature_types"]
    assert "Membrane" in rows[0]["source_protein_keywords"]


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
        "comments": [
            {
                "commentType": "SUBCELLULAR LOCATION",
                "subcellularLocations": [
                    {
                        "location": {
                            "value": "Secreted",
                            "id": "SL-0243",
                            "evidences": [{"evidenceCode": "ECO:0000269", "source": "PubMed", "id": "123"}],
                        }
                    },
                ],
            }
        ],
        "keywords": [{"name": "Signal"}],
        "uniProtKBCrossReferences": [
            {
                "database": "GO",
                "id": "GO:0005576",
                "properties": [{"key": "GoTerm", "value": "C:extracellular region"}],
            }
        ],
        "features": [
            {
                "type": "Signal",
                "location": {"start": {"value": 1}, "end": {"value": 16}},
            }
        ],
    }
