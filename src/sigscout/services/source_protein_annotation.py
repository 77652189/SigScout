from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Iterable


ANNOTATION_STATUS_PENDING = "未评估"
ANNOTATION_STATUS_DONE = "已评估"
ROUTE_UNKNOWN = "未知"

EXPERIMENTAL_GO_EVIDENCE = {
    "EXP",
    "IDA",
    "IPI",
    "IMP",
    "IGI",
    "IEP",
    "HTP",
    "HDA",
    "HMP",
    "HGI",
    "HEP",
}
CURATED_GO_EVIDENCE = {
    "ISS",
    "ISO",
    "ISA",
    "ISM",
    "IGC",
    "IBA",
    "IBD",
    "IKR",
    "IRD",
    "RCA",
    "TAS",
    "IC",
}
AUTOMATIC_GO_EVIDENCE = {"IEA"}

EXPERIMENTAL_ECO_CODES = {"ECO:0000269"}
CURATED_ECO_CODES = {"ECO:0000305", "ECO:0000250"}
AUTOMATIC_ECO_CODES = {"ECO:0000256", "ECO:0007826", "ECO:0007322"}


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
            "source_protein_annotation_run_at": _now_iso(),
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
    evidence_level = _evidence_level(row, evidence, matches)
    route = best_match.route if best_match else ROUTE_UNKNOWN
    confidence = _confidence_for(route, evidence_level)
    selected_matches = [match for match in matches if match.route == route]
    basis = "; ".join(dict.fromkeys(match.basis for match in sorted(selected_matches, key=lambda item: item.priority)))
    summary = _evidence_summary(evidence, selected_matches)

    return {
        **row,
        "source_protein_route": route,
        "source_protein_route_confidence": confidence,
        "source_protein_evidence_level": evidence_level,
        "source_protein_route_basis": basis,
        "source_protein_evidence_summary": summary,
        "source_protein_route_note": _source_route_note(route, evidence_level, basis),
        "source_protein_quickgo_json": _json_dumps(quickgo),
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
                        evidence_codes=tuple(_list_values(feature.get("evidence_codes", []))),
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
                        evidence_codes=tuple(_list_values(location.get("evidence_codes", []))),
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
                evidence_text = f"，证据：{_evidence_code_label(evidence_code)}" if evidence_code else ""
                matches.append(
                    RouteMatch(
                        route=route,
                        priority=priority,
                        basis=(
                            f"GO 证据：{_format_go(go_id, term)} 属于 {_format_go(root, root_term)}，"
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


def _evidence_level(
    row: dict[str, object],
    evidence: dict[str, list[dict[str, object]]],
    matches: list[RouteMatch],
) -> str:
    codes = _all_evidence_codes(evidence)
    match_codes = {code for match in matches for code in match.evidence_codes}
    all_codes = codes | match_codes
    go_codes = {_go_evidence_prefix(code) for code in all_codes if _go_evidence_prefix(code)}
    eco_codes = {code for code in all_codes if code.startswith("ECO:")}
    if go_codes & EXPERIMENTAL_GO_EVIDENCE or eco_codes & EXPERIMENTAL_ECO_CODES:
        return "实验支持"
    if go_codes & CURATED_GO_EVIDENCE or eco_codes & CURATED_ECO_CODES:
        return "人工/同源推断"
    if go_codes & AUTOMATIC_GO_EVIDENCE or eco_codes & AUTOMATIC_ECO_CODES or all_codes:
        return "自动/预测证据"
    return "无明确证据"


def _all_evidence_codes(evidence: dict[str, list[dict[str, object]]]) -> set[str]:
    codes: set[str] = set()
    for group in evidence.values():
        for item in group:
            codes.update(_list_values(item.get("evidence_codes", [])))
            for key in ("go_evidence", "evidence_code"):
                value = str(item.get(key, "")).strip()
                if value:
                    codes.add(value)
    return codes


def _confidence_for(route: str, evidence_level: str) -> str:
    if route == ROUTE_UNKNOWN:
        return "低"
    if evidence_level == "实验支持":
        return "高"
    if evidence_level == "人工/同源推断":
        return "中"
    if evidence_level == "自动/预测证据":
        return "低"
    return "低"


def _evidence_summary(evidence: dict[str, list[dict[str, object]]], matches: list[RouteMatch]) -> str:
    parts: list[str] = []
    locations = [
        f"{item.get('id', '')} {item.get('value', '')}".strip()
        for item in evidence["locations"]
        if item.get("id") or item.get("value")
    ]
    go_ids = [
        f"{item.get('go_id', '')} {item.get('term') or item.get('go_term') or ''}".strip()
        for item in evidence["go"] + evidence["quickgo"]
        if item.get("go_id")
    ]
    features = [str(item.get("type", "")).strip() for item in evidence["features"] if item.get("type")]
    if locations:
        parts.append("UniProt SL: " + ", ".join(dict.fromkeys(locations[:4])))
    if go_ids:
        parts.append("GO: " + ", ".join(dict.fromkeys(go_ids[:4])))
    if features:
        parts.append("Feature: " + ", ".join(dict.fromkeys(features[:4])))
    if matches:
        parts.append("命中依据: " + "; ".join(dict.fromkeys(match.basis for match in matches[:4])))
    return " | ".join(parts)


def _source_route_note(route: str, evidence_level: str, basis: str) -> str:
    if route == ROUTE_UNKNOWN:
        return "已汇总 UniProt/GO 结构化证据，但没有命中当前受控 ID 映射；建议人工复核或扩展映射。"
    if basis:
        return f"根据受控证据映射得到：{basis}；证据等级：{evidence_level}。"
    return f"根据受控证据映射得到；证据等级：{evidence_level}。"


def _format_go(go_id: str, term: object) -> str:
    text = str(term or "").strip()
    return f"{go_id} {text}".strip()


def _evidence_code_label(value: str) -> str:
    prefix = _go_evidence_prefix(value)
    if prefix in EXPERIMENTAL_GO_EVIDENCE:
        return f"{value}/实验"
    if prefix in CURATED_GO_EVIDENCE:
        return f"{value}/人工或同源推断"
    if prefix in AUTOMATIC_GO_EVIDENCE:
        return f"{value}/自动注释"
    if value in EXPERIMENTAL_ECO_CODES:
        return f"{value}/实验"
    if value in CURATED_ECO_CODES:
        return f"{value}/人工或同源推断"
    if value in AUTOMATIC_ECO_CODES:
        return f"{value}/自动注释"
    return value


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


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _split_values(value: object) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _list_values(value: object) -> list[str]:
    if isinstance(value, list):
        values = value
    else:
        values = [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _go_evidence_prefix(value: str) -> str:
    text = str(value).strip()
    if ":" in text:
        return text.split(":", 1)[0]
    return text


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
