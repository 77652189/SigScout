from __future__ import annotations

from sigscout.adapters.quickgo import QuickGOAnnotationSource


def test_quickgo_source_groups_annotations_and_ancestors() -> None:
    source = FakeQuickGOAnnotationSource()

    result = source.fetch_cellular_component_annotations(["P12345", "P00508"])

    assert result.errors == []
    assert result.annotations_by_accession["P12345"][0]["go_id"] == "GO:0005886"
    assert result.annotations_by_accession["P12345"][0]["go_term"] == "plasma membrane"
    assert result.annotations_by_accession["P00508"][0]["go_evidence"] == "IEA"
    assert result.go_ancestors_by_id["GO:0005886"] == {"GO:0005886", "GO:0016020"}
    assert result.go_terms_by_id["GO:0016020"] == "membrane"


class FakeQuickGOAnnotationSource(QuickGOAnnotationSource):
    def _get_json(self, url: str):
        if "/annotation/search?" in url:
            return {
                "results": [
                    {
                        "geneProductId": "UniProtKB:P12345",
                        "goId": "GO:0005886",
                        "goEvidence": "IDA",
                        "evidenceCode": "ECO:0000314",
                        "qualifier": "located_in",
                        "reference": "PMID:1",
                        "assignedBy": "UniProt",
                    },
                    {
                        "geneProductId": "UniProtKB:P00508",
                        "goId": "GO:0005576",
                        "goEvidence": "IEA",
                        "evidenceCode": "ECO:0007322",
                        "qualifier": "located_in",
                        "reference": "GO_REF:1",
                        "assignedBy": "UniProt",
                    },
                ],
                "pageInfo": {"current": 1, "total": 1},
            }
        if "/ontology/go/terms/" in url:
            return {
                "results": [
                    {
                        "id": "GO:0005886",
                        "name": "plasma membrane",
                        "ancestors": ["GO:0005886", "GO:0016020"],
                    },
                    {"id": "GO:0016020", "name": "membrane", "ancestors": ["GO:0016020"]},
                    {"id": "GO:0005576", "name": "extracellular region", "ancestors": ["GO:0005576"]},
                ]
            }
        raise AssertionError(url)
