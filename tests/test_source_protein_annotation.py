from __future__ import annotations

from sigscout.services.source_protein_annotation import (
    annotate_source_protein_route,
    annotate_source_protein_routes,
    ensure_source_protein_annotation_defaults,
)


def test_source_protein_annotation_marks_secreted_protein() -> None:
    row = {
        "protein_name": "Secreted test protein",
        "source_protein_uniprot_location_json": (
            '[{"id":"SL-0243","value":"Secreted","evidence_codes":["ECO:0000269"]}]'
        ),
    }

    annotated = annotate_source_protein_route(row)

    assert annotated["source_protein_route"] == "分泌/胞外倾向"
    assert annotated["source_protein_route_confidence"] == "高"
    assert annotated["source_protein_evidence_level"] == "实验支持"
    assert annotated["source_protein_annotation_status"] == "已评估"


def test_source_protein_annotation_marks_membrane_or_anchored_protein() -> None:
    row = {
        "protein_name": "GPI-anchored cell wall protein",
        "source_protein_uniprot_feature_json": (
            '[{"type":"Signal","evidence_codes":["ECO:0000256"]},'
            '{"type":"Transmembrane","evidence_codes":["ECO:0000256"]}]'
        ),
    }

    annotated = annotate_source_protein_route(row)

    assert annotated["source_protein_route"] == "膜/锚定倾向"
    assert annotated["source_protein_route_confidence"] == "低"
    assert annotated["source_protein_evidence_level"] == "自动/预测证据"
    assert "UniProt feature：Transmembrane -> 膜/锚定倾向" in str(annotated["source_protein_route_basis"])


def test_source_protein_annotation_defaults_are_pending_not_unknown() -> None:
    row = ensure_source_protein_annotation_defaults({"candidate_id": "A"})

    assert row["source_protein_route"] == "未评估"
    assert row["source_protein_route_confidence"] == ""
    assert row["source_protein_annotation_status"] == "未评估"


def test_source_protein_annotation_returns_summary_counts() -> None:
    result = annotate_source_protein_routes(
        [
            {"source_protein_uniprot_location_json": '[{"id":"SL-0243","value":"Secreted"}]'},
            {"source_protein_uniprot_feature_json": '[{"type":"Transmembrane"}]'},
        ]
    )

    assert result.summary["source_protein_annotation_status"] == "已评估"
    assert result.summary["source_protein_annotated_count"] == 2
    assert result.summary["source_protein_route_counts"]["分泌/胞外倾向"] == 1
    assert result.summary["source_protein_route_counts"]["膜/锚定倾向"] == 1


def test_source_protein_annotation_uses_quickgo_go_ancestors() -> None:
    result = annotate_source_protein_routes(
        [{"accession": "P12345"}],
        quickgo_annotations_by_accession={
            "P12345": [
                {
                    "source": "QuickGO/GOA",
                    "go_id": "GO:0005886",
                    "go_term": "plasma membrane",
                    "go_evidence": "IDA",
                    "evidence_code": "ECO:0000314",
                }
            ]
        },
        go_ancestors_by_id={"GO:0005886": {"GO:0005886", "GO:0016020"}},
        go_terms_by_id={"GO:0005886": "plasma membrane", "GO:0016020": "membrane"},
        quickgo_query_at="2026-06-18T10:00:00+08:00",
    )

    row = result.rows[0]
    assert row["source_protein_route"] == "膜/锚定倾向"
    assert row["source_protein_route_confidence"] == "高"
    assert row["source_protein_evidence_level"] == "实验支持"
    assert row["source_protein_quickgo_count"] == 1
    assert "GO:0005886 plasma membrane" in row["source_protein_route_basis"]
    assert "IDA/实验" in row["source_protein_route_basis"]


def test_source_protein_annotation_preserves_existing_quickgo_when_not_refetched() -> None:
    row = {
        "accession": "P12345",
        "source_protein_quickgo_json": (
            '[{"source":"QuickGO/GOA","go_id":"GO:0005886","go_term":"plasma membrane","go_evidence":"IDA"}]'
        ),
    }

    result = annotate_source_protein_routes(
        [row],
        go_ancestors_by_id={"GO:0005886": {"GO:0005886", "GO:0016020"}},
        go_terms_by_id={"GO:0005886": "plasma membrane", "GO:0016020": "membrane"},
    )

    assert result.rows[0]["source_protein_route"] == "膜/锚定倾向"
    assert result.rows[0]["source_protein_quickgo_count"] == 1
