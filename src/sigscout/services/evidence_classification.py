from __future__ import annotations

from typing import TYPE_CHECKING

from sigscout.core.coercion import list_values

if TYPE_CHECKING:
    from sigscout.services.source_protein_annotation import RouteMatch


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


def evidence_level(
    row: dict[str, object],
    evidence: dict[str, list[dict[str, object]]],
    matches: list["RouteMatch"],
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
            codes.update(list_values(item.get("evidence_codes", [])))
            for key in ("go_evidence", "evidence_code"):
                value = str(item.get(key, "")).strip()
                if value:
                    codes.add(value)
    return codes


def confidence_for(route: str, evidence_level_value: str) -> str:
    if route == ROUTE_UNKNOWN:
        return "低"
    if evidence_level_value == "实验支持":
        return "高"
    if evidence_level_value == "人工/同源推断":
        return "中"
    if evidence_level_value == "自动/预测证据":
        return "低"
    return "低"


def evidence_summary(evidence: dict[str, list[dict[str, object]]], matches: list["RouteMatch"]) -> str:
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


def source_route_note(route: str, evidence_level_value: str, basis: str) -> str:
    if route == ROUTE_UNKNOWN:
        return "已汇总 UniProt/GO 结构化证据，但没有命中当前受控 ID 映射；建议人工复核或扩展映射。"
    if basis:
        return f"根据受控证据映射得到：{basis}；证据等级：{evidence_level_value}。"
    return f"根据受控证据映射得到；证据等级：{evidence_level_value}。"


def format_go(go_id: str, term: object) -> str:
    text = str(term or "").strip()
    return f"{go_id} {text}".strip()


def evidence_code_label(value: str) -> str:
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


def _go_evidence_prefix(value: str) -> str:
    text = str(value).strip()
    if ":" in text:
        return text.split(":", 1)[0]
    return text
