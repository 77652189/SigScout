from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from sigscout.core.coercion import json_dumps, list_values, now_iso
from sigscout.services.evidence_classification import (
    ROUTE_UNKNOWN,
    confidence_for,
    evidence_code_label,
    evidence_level,
    evidence_summary,
    format_go,
    source_route_note,
)


ANNOTATION_STATUS_PENDING = "未评估"
ANNOTATION_STATUS_DONE = "已评估"


@dataclass(frozen=True)
class SourceProteinAnnotationResult:
    rows: list[dict[str, object]]
    summary: dict[str, object]


@dataclass(frozen=True)
class RouteMatch:
    route: str
    priority: int
    basis: str
    evidence_codes: tuple[str, ...]
    source: str


def annotate_source_protein_routes(
    rows: list[dict[str, object]],
    *,
    quickgo_annotations_by_accession: dict[str, list[dict[str, object]]] | None = None,
    go_ancestors_by_id: dict[str, set[str]] | None = None,
    go_terms_by_id: dict[str, str] | None = None,
    quickgo_query_at: str = "",
    quickgo_errors: list[str] | None = None,
) -> SourceProteinAnnotationResult:
    route_map = _load_route_map()
    annotated = []
    for row in rows:
        quickgo_annotations = None
        if quickgo_annotations_by_accession is not None:
            quickgo_annotations = quickgo_annotations_by_accession.get(str(row.get("accession", "")).strip(), [])
        annotated.append(
            annotate_source_protein_route(
                row,
                route_map=route_map,
                quickgo_annotations=quickgo_annotations,
                go_ancestors_by_id=go_ancestors_by_id or {},
                go_terms_by_id=go_terms_by_id or {},
                quickgo_query_at=quickgo_query_at,
            )
        )
    counts = Counter(str(row.get("source_protein_route", ROUTE_UNKNOWN)) for row in annotated)
    evidence_counts = Counter(str(row.get("source_protein_evidence_level", "无明确证据")) for row in annotated)
    return SourceProteinAnnotationResult(
        rows=annotated,
        summary={
            "source_protein_annotation_run_at": now_iso(),
            "source_protein_annotation_status": ANNOTATION_STATUS_DONE,
            "source_protein_annotation_method": "UniProt controlled locations/features + GO cellular component evidence",
            "source_protein_route_map_version": str(route_map.get("version", "")),
            "source_protein_route_counts": dict(counts),
            "source_protein_evidence_level_counts": dict(evidence_counts),
            "source_protein_annotated_count": len(annotated),
            "source_protein_quickgo_query_at": quickgo_query_at,
            "source_protein_quickgo_error_count": len(quickgo_errors or []),
            "source_protein_quickgo_errors": quickgo_errors or [],
        },
    )


def annotate_source_protein_route(
    row: dict[str, object],
    *,
    route_map: dict[str, object] | None = None,
    quickgo_annotations: list[dict[str, object]] | None = None,
    go_ancestors_by_id: dict[str, set[str]] | None = None,
    go_terms_by_id: dict[str, str] | None = None,
    quickgo_query_at: str = "",
) -> dict[str, object]:
    route_map = route_map or _load_route_map()
    go_ancestors_by_id = go_ancestors_by_id or {}
    go_terms_by_id = go_terms_by_id or {}
    evidence = _row_evidence(row)
    quickgo = list(quickgo_annotations or evidence["quickgo"])
    if quickgo_annotations is not None:
        evidence["quickgo"] = quickgo

    _fill_go_terms(evidence, go_terms_by_id)
    matches = _route_matches(evidence, route_map, go_ancestors_by_id, go_terms_by_id)
    best_match = sorted(matches, key=lambda item: item.priority)[0] if matches else None
    level = evidence_level(row, evidence, matches)
    route = best_match.route if best_match else ROUTE_UNKNOWN
    confidence = confidence_for(route, level)
    selected_matches = [match for match in matches if match.route == route]
    basis = "; ".join(dict.fromkeys(match.basis for match in sorted(selected_matches, key=lambda item: item.priority)))
    summary = evidence_summary(evidence, selected_matches)

    return {
        **row,
        "source_protein_route": route,
        "source_protein_route_confidence": confidence,
        "source_protein_evidence_level": level,
        "source_protein_route_basis": basis,
        "source_protein_evidence_summary": summary,
        "source_protein_route_note": source_route_note(route, level, basis),
        "source_protein_quickgo_json": json_dumps(quickgo),
        "source_protein_quickgo_count": len(quickgo),
        "source_protein_quickgo_query_at": quickgo_query_at or str(row.get("source_protein_quickgo_query_at", "")),
        "source_protein_annotation_status": ANNOTATION_STATUS_DONE,
    }


def ensure_source_protein_annotation_defaults(row: dict[str, object]) -> dict[str, object]:
    updated = dict(row)
    updated.setdefault("source_protein_location", "")
    updated.setdefault("source_protein_location_ids", "")
    updated.setdefault("source_protein_location_evidence_codes", "")
    updated.setdefault("source_protein_keywords", "")
    updated.setdefault("source_protein_keyword_ids", "")
    updated.setdefault("source_protein_keyword_evidence_codes", "")
    updated.setdefault("source_protein_go_terms", "")
    updated.setdefault("source_protein_go_ids", "")
    updated.setdefault("source_protein_go_evidence", "")
    updated.setdefault("source_protein_feature_types", "")
    updated.setdefault("source_protein_feature_evidence_codes", "")
    updated.setdefault("source_protein_uniprot_location_json", "[]")
    updated.setdefault("source_protein_uniprot_keyword_json", "[]")
    updated.setdefault("source_protein_uniprot_go_json", "[]")
    updated.setdefault("source_protein_uniprot_feature_json", "[]")
    updated.setdefault("source_protein_quickgo_json", "[]")
    updated.setdefault("source_protein_quickgo_count", 0)
    updated.setdefault("source_protein_quickgo_query_at", "")
    updated.setdefault("source_protein_evidence_level", "")
    updated.setdefault("source_protein_route_basis", "")
    updated.setdefault("source_protein_evidence_summary", "")
    updated.setdefault("source_protein_annotation_status", ANNOTATION_STATUS_PENDING)
    updated.setdefault("source_protein_route", ANNOTATION_STATUS_PENDING)
    updated.setdefault("source_protein_route_confidence", "")
    updated.setdefault("source_protein_route_note", "尚未运行来源蛋白定位辅助评估。")
    return updated


def _route_matches(
    evidence: dict[str, list[dict[str, object]]],
    route_map: dict[str, object],
    go_ancestors_by_id: dict[str, set[str]],
    go_terms_by_id: dict[str, str],
) -> list[RouteMatch]:
    routes = sorted(route_map.get("routes", []), key=lambda item: int(item.get("priority", 100)))
    matches: list[RouteMatch] = []
    for route_config in routes:
        route = str(route_config.get("route", ""))
        priority = int(route_config.get("priority", 100))
        feature_types = {str(value).lower() for value in route_config.get("feature_types", [])}
        sl_ids = {str(value) for value in route_config.get("uniprot_sl_ids", [])}
        go_roots = {str(value) for value in route_config.get("go_ancestor_ids", [])}

        for feature in evidence["features"]:
            feature_type = str(feature.get("type", ""))
            if feature_type.lower() in feature_types:
                matches.append(
                    RouteMatch(
                        route=route,
                        priority=priority,
                        basis=f"UniProt feature：{feature_type} -> {route}",
                        evidence_codes=tuple(list_values(feature.get("evidence_codes", []))),
                        source="UniProtKB feature",
                    )
                )

        for location in evidence["locations"]:
            location_id = str(location.get("id", "")).strip()
            if location_id and location_id in sl_ids:
                label = f"{location_id} {location.get('value', '')}".strip()
                matches.append(
                    RouteMatch(
                        route=route,
                        priority=priority,
                        basis=f"UniProt 定位：{label} -> {route}",
                        evidence_codes=tuple(list_values(location.get("evidence_codes", []))),
                        source="UniProtKB subcellular location",
                    )
                )

        for annotation in evidence["go"] + evidence["quickgo"]:
            go_id = str(annotation.get("go_id", "")).strip()
            if not go_id:
                continue
            ancestors = set(go_ancestors_by_id.get(go_id, set()))
            ancestors.add(go_id)
            matched_roots = sorted(ancestors & go_roots)
            if matched_roots:
                term = annotation.get("term") or annotation.get("go_term") or go_terms_by_id.get(go_id, "")
                evidence_code = str(annotation.get("go_evidence") or annotation.get("evidence_code") or "")
                root = matched_roots[0]
                root_term = go_terms_by_id.get(root, "")
                evidence_text = f"，证据：{evidence_code_label(evidence_code)}" if evidence_code else ""
                matches.append(
                    RouteMatch(
                        route=route,
                        priority=priority,
                        basis=(
                            f"GO 证据：{format_go(go_id, term)} 属于 {format_go(root, root_term)}，"
                            f"映射为{route}{evidence_text}"
                        ),
                        evidence_codes=tuple(value for value in (evidence_code,) if value),
                        source=str(annotation.get("source", "GO")),
                    )
                )
    return matches


def _row_evidence(row: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    locations = _parse_json_list(row.get("source_protein_uniprot_location_json"))
    go_entries = _parse_json_list(row.get("source_protein_uniprot_go_json"))
    features = _parse_json_list(row.get("source_protein_uniprot_feature_json"))
    quickgo = _parse_json_list(row.get("source_protein_quickgo_json"))
    if not go_entries:
        go_entries = _legacy_go_entries(row)
    if not features:
        features = _legacy_feature_entries(row)
    return {
        "locations": locations,
        "go": go_entries,
        "features": features,
        "quickgo": quickgo,
    }


def _fill_go_terms(evidence: dict[str, list[dict[str, object]]], go_terms_by_id: dict[str, str]) -> None:
    for item in evidence["go"] + evidence["quickgo"]:
        go_id = str(item.get("go_id", "")).strip()
        if not go_id:
            continue
        if not item.get("term") and go_terms_by_id.get(go_id):
            item["term"] = go_terms_by_id[go_id]
        if not item.get("go_term") and go_terms_by_id.get(go_id):
            item["go_term"] = go_terms_by_id[go_id]


def _legacy_go_entries(row: dict[str, object]) -> list[dict[str, object]]:
    ids = _split_values(row.get("source_protein_go_ids", ""))
    terms = _split_values(row.get("source_protein_go_terms", ""))
    evidence = _split_values(row.get("source_protein_go_evidence", ""))
    entries: list[dict[str, object]] = []
    for index, go_id in enumerate(ids):
        entries.append(
            {
                "source": "UniProtKB cross-reference",
                "go_id": go_id,
                "term": terms[index] if index < len(terms) else "",
                "go_evidence": evidence[index] if index < len(evidence) else "",
            }
        )
    return entries


def _legacy_feature_entries(row: dict[str, object]) -> list[dict[str, object]]:
    evidence_codes = _split_values(row.get("source_protein_feature_evidence_codes", ""))
    return [
        {
            "source": "UniProtKB feature",
            "type": feature_type,
            "evidence_codes": evidence_codes,
        }
        for feature_type in _split_values(row.get("source_protein_feature_types", ""))
    ]


def _load_route_map() -> dict[str, object]:
    try:
        text = files("sigscout.data").joinpath("source_protein_route_map.json").read_text(encoding="utf-8")
        return json.loads(text)
    except Exception:
        path = Path(__file__).resolve().parents[1] / "data" / "source_protein_route_map.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"version": "fallback", "routes": []}


def _parse_json_list(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _split_values(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


