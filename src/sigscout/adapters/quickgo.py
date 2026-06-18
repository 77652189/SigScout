from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


QUICKGO_BASE_URL = "https://www.ebi.ac.uk/QuickGO/services"


@dataclass(frozen=True)
class QuickGOAnnotationResult:
    annotations_by_accession: dict[str, list[dict[str, object]]]
    go_ancestors_by_id: dict[str, set[str]]
    go_terms_by_id: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    query_at: str = ""


class QuickGOAnnotationSource:
    def __init__(
        self,
        *,
        base_url: str = QUICKGO_BASE_URL,
        timeout_seconds: int = 30,
        batch_size: int = 50,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, min(batch_size, 100))

    def fetch_cellular_component_annotations(
        self,
        accessions: Iterable[str],
    ) -> QuickGOAnnotationResult:
        clean_accessions = sorted({str(accession).strip() for accession in accessions if str(accession).strip()})
        annotations: dict[str, list[dict[str, object]]] = {accession: [] for accession in clean_accessions}
        errors: list[str] = []
        query_at = _now_iso()
        for batch in _chunks(clean_accessions, self.batch_size):
            try:
                batch_annotations = self._fetch_annotation_batch(batch)
            except Exception as exc:
                errors.append(f"QuickGO annotation 请求失败：{exc}")
                continue
            for row in batch_annotations:
                accession = _accession_from_gene_product(str(row.get("geneProductId", "")))
                if not accession:
                    continue
                annotations.setdefault(accession, []).append(_normalise_annotation(row))

        go_ids = sorted(
            {
                str(annotation.get("go_id", "")).strip()
                for rows in annotations.values()
                for annotation in rows
                if str(annotation.get("go_id", "")).strip()
            }
        )
        ancestors: dict[str, set[str]] = {}
        terms_by_id: dict[str, str] = {}
        if go_ids:
            try:
                ancestors = self.fetch_go_ancestors(go_ids)
            except Exception as exc:
                errors.append(f"QuickGO ontology 请求失败：{exc}")
            ontology_ids = sorted(set(go_ids) | {ancestor for values in ancestors.values() for ancestor in values})
            try:
                terms_by_id = self.fetch_go_terms(ontology_ids)
            except Exception as exc:
                errors.append(f"QuickGO term 请求失败：{exc}")
            for rows in annotations.values():
                for annotation in rows:
                    if not annotation.get("go_term"):
                        annotation["go_term"] = terms_by_id.get(str(annotation.get("go_id", "")), "")

        return QuickGOAnnotationResult(
            annotations_by_accession=annotations,
            go_ancestors_by_id=ancestors,
            go_terms_by_id=terms_by_id,
            errors=errors,
            query_at=query_at,
        )

    def fetch_go_ancestors(self, go_ids: Iterable[str]) -> dict[str, set[str]]:
        clean_ids = sorted({str(go_id).strip() for go_id in go_ids if str(go_id).strip()})
        ancestors: dict[str, set[str]] = {}
        for batch in _chunks(clean_ids, self.batch_size):
            url = f"{self.base_url}/ontology/go/terms/{','.join(batch)}/ancestors"
            payload = self._get_json(url)
            for result in payload.get("results", []):
                go_id = str(result.get("id", "")).strip()
                if not go_id:
                    continue
                values = {str(value).strip() for value in result.get("ancestors", []) if str(value).strip()}
                values.add(go_id)
                ancestors[go_id] = values
        return ancestors

    def fetch_go_terms(self, go_ids: Iterable[str]) -> dict[str, str]:
        clean_ids = sorted({str(go_id).strip() for go_id in go_ids if str(go_id).strip()})
        terms: dict[str, str] = {}
        for batch in _chunks(clean_ids, self.batch_size):
            url = f"{self.base_url}/ontology/go/terms/{','.join(batch)}"
            payload = self._get_json(url)
            for result in payload.get("results", []):
                go_id = str(result.get("id", "")).strip()
                name = str(result.get("name", "")).strip()
                if go_id and name:
                    terms[go_id] = name
        return terms

    def _fetch_annotation_batch(self, accessions: list[str]) -> list[dict[str, object]]:
        all_results: list[dict[str, object]] = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            params = {
                "geneProductId": ",".join(f"UniProtKB:{accession}" for accession in accessions),
                "aspect": "cellular_component",
                "limit": "100",
                "page": str(page),
            }
            url = f"{self.base_url}/annotation/search?{urlencode(params)}"
            payload = self._get_json(url)
            all_results.extend(payload.get("results", []))
            page_info = payload.get("pageInfo", {})
            total_pages = _safe_int(page_info.get("total")) or 1
            page += 1
        return all_results

    def _get_json(self, url: str) -> dict[str, object]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "SigScout-local/0.1",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def _normalise_annotation(row: dict[str, object]) -> dict[str, object]:
    return {
        "source": "QuickGO/GOA",
        "gene_product_id": row.get("geneProductId", ""),
        "go_id": row.get("goId", ""),
        "go_term": row.get("goName") or "",
        "go_evidence": row.get("goEvidence", ""),
        "evidence_code": row.get("evidenceCode", ""),
        "qualifier": row.get("qualifier", ""),
        "reference": row.get("reference", ""),
        "assigned_by": row.get("assignedBy", ""),
        "date": row.get("date", ""),
    }


def _accession_from_gene_product(value: str) -> str:
    prefix = "UniProtKB:"
    if not value.startswith(prefix):
        return ""
    return value[len(prefix) :].strip()


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
