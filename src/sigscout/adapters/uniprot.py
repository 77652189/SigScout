from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sigscout.core.models import AA_PATTERN, SignalPeptideCandidate, UniProtCandidateLibraryResult


PICHIA_NATIVE_SIGNAL_LABEL = "毕赤酵母来源信号肽"


@dataclass
class UniProtSignalPeptideSource:
    existing_candidates: Iterable[SignalPeptideCandidate] = field(default_factory=list)
    candidate_prefix: str = "UNIPROT"

    def discover(
        self,
        *,
        taxon_id: int = 4922,
        max_records: int = 300,
        reviewed_only: bool = False,
        exclude_existing: bool = False,
        page_size: int = 100,
    ) -> UniProtCandidateLibraryResult:
        query = f"(organism_id:{taxon_id}) AND (ft_signal:*)"
        if reviewed_only:
            query += " AND (reviewed:true)"
        safe_page_size = max(1, min(int(page_size), 500))
        params = {
            "query": query,
            "format": "json",
            "size": str(safe_page_size),
            "fields": ",".join(
                [
                    "accession",
                    "id",
                    "protein_name",
                    "organism_name",
                    "ft_signal",
                    "ft_transmem",
                    "ft_intramem",
                    "ft_topo_dom",
                    "ft_carbohyd",
                    "cc_subcellular_location",
                    "keyword",
                    "go_c",
                    "sequence",
                ]
            ),
        }
        url = "https://rest.uniprot.org/uniprotkb/search?" + urlencode(params)
        next_url: str | None = url
        items: list[dict] = []
        initial_hit_count = 0
        errors: list[str] = []
        try:
            while next_url and len(items) < max_records:
                request = Request(next_url, headers={"User-Agent": "SigScout-local/0.1"})
                with urlopen(request, timeout=30) as response:
                    if not initial_hit_count:
                        initial_hit_count = _safe_int(response.headers.get("x-total-results"))
                    payload = json.loads(response.read().decode("utf-8"))
                    items.extend(payload.get("results", []))
                    next_url = _next_link(response.headers.get("Link"))
        except Exception as exc:
            return UniProtCandidateLibraryResult(
                rows=[],
                source_url=url,
                errors=[f"UniProt API 请求失败：{exc}"],
                initial_hit_count=initial_hit_count,
                fetched_record_count=len(items),
                extracted_signal_count=0,
                deduplicated_count=0,
                duplicate_count=0,
                duplicate_rows=[],
            )

        limited_items = items[:max_records]
        rows, row_errors, extracted_signal_count, duplicate_rows = self.rows_from_items(
            limited_items,
            exclude_existing=exclude_existing,
        )
        errors.extend(row_errors)
        if not initial_hit_count:
            initial_hit_count = len(items)
        return UniProtCandidateLibraryResult(
            rows=rows,
            source_url=url,
            errors=errors,
            initial_hit_count=initial_hit_count,
            fetched_record_count=len(limited_items),
            extracted_signal_count=extracted_signal_count,
            deduplicated_count=len(rows),
            duplicate_count=len(duplicate_rows),
            duplicate_rows=duplicate_rows,
        )

    def rows_from_payload(
        self,
        payload: dict,
        *,
        exclude_existing: bool = True,
    ) -> tuple[list[dict[str, object]], list[str]]:
        rows, errors, _extracted_count, _duplicate_rows = self.rows_from_items(
            payload.get("results", []),
            exclude_existing=exclude_existing,
        )
        return rows, errors

    def rows_from_items(
        self,
        items: Iterable[dict],
        *,
        exclude_existing: bool,
    ) -> tuple[list[dict[str, object]], list[str], int, list[dict[str, object]]]:
        existing_ids, existing_leaders = self._existing_sets()
        rows: list[dict[str, object]] = []
        duplicate_rows: list[dict[str, object]] = []
        errors: list[str] = []
        seen_sequences: dict[str, str] = {}
        extracted_signal_count = 0
        for item in items:
            accession = item.get("primaryAccession", "")
            sequence = item.get("sequence", {}).get("value", "")
            signal, signal_start, signal_end = _signal_feature(item, sequence)
            if not accession or not signal:
                continue
            extracted_signal_count += 1
            candidate_id = f"{self.candidate_prefix}_{_safe_id(accession)}"
            already_in_formal_library = candidate_id in existing_ids or signal in existing_leaders
            candidate = SignalPeptideCandidate(
                candidate_id=candidate_id,
                accession=accession,
                uniprot_id=item.get("uniProtkbId", ""),
                protein_name=_protein_name(item),
                organism_name=item.get("organism", {}).get("scientificName", ""),
                protein_sequence=sequence,
                protein_length=len(sequence),
                uniprot_signal_start=signal_start,
                uniprot_signal_end=signal_end,
                leader_sequence=signal,
                signal_peptide_sequence=signal,
                category="pichia_native_signal",
                category_label=PICHIA_NATIVE_SIGNAL_LABEL,
                processing_route="signal peptidase only",
                source_note="",
                rationale="UniProt 中带 signal peptide 注释的 Komagataella/Pichia 蛋白，适合作为外部候选草案。",
                caution="来自数据库自动发现；进入实验构建前需要人工确认切割位点、文献证据和目标蛋白适配性。",
                library_stage="外部发现草案",
                source_type="UniProt",
                already_in_formal_library=already_in_formal_library,
                uniprot_reviewed=_is_reviewed_entry(item),
            )
            row = candidate.as_row()
            row.update(_source_protein_evidence(item))
            row["source_note"] = (
                f"UniProt {row['accession']} {row['uniprot_id']}; "
                f"{row['organism_name']}; {row['protein_name']}"
            )
            if already_in_formal_library:
                duplicate_rows.append(
                    {
                        **row,
                        "duplicate_reason": "与正式候选库已有序列重复",
                        "duplicate_of": "formal_library",
                    }
                )
                if exclude_existing:
                    continue
            if signal in seen_sequences:
                duplicate_rows.append(
                    {
                        **row,
                        "duplicate_reason": "UniProt 结果中信号肽序列重复",
                        "duplicate_of": seen_sequences[signal],
                    }
                )
                continue
            seen_sequences[signal] = candidate_id
            rows.append(row)
        if not rows:
            errors.append("没有发现可加入草案的新 signal peptide；可能都已存在或查询结果没有明确序列。")
        return rows, errors, extracted_signal_count, duplicate_rows

    def _existing_sets(self) -> tuple[set[str], set[str]]:
        ids = set()
        leaders = set()
        for candidate in self.existing_candidates:
            ids.add(candidate.candidate_id)
            leaders.add(candidate.leader_sequence)
        return ids, leaders


def _signal_feature(item: dict, sequence: str) -> tuple[str, int | None, int | None]:
    for feature in item.get("features", []):
        if feature.get("type") != "Signal":
            continue
        location = feature.get("location", {})
        start = location.get("start", {}).get("value")
        end = location.get("end", {}).get("value")
        if not start or not end:
            continue
        start_int = int(start)
        end_int = int(end)
        signal = sequence[start_int - 1 : end_int]
        if AA_PATTERN.fullmatch(signal):
            return signal, start_int, end_int
    return "", None, None


def _protein_name(item: dict) -> str:
    recommended = item.get("proteinDescription", {}).get("recommendedName", {})
    full_name = recommended.get("fullName", {})
    if full_name.get("value"):
        return str(full_name["value"])
    submission_names = item.get("proteinDescription", {}).get("submissionNames", [])
    if submission_names:
        return str(submission_names[0].get("fullName", {}).get("value", ""))
    return ""


def _source_protein_evidence(item: dict) -> dict[str, object]:
    locations = _subcellular_location_terms(item)
    keywords = _keyword_entries(item)
    go_terms = _go_entries(item)
    features = _feature_entries(item)
    return {
        "source_protein_location": "; ".join(_unique_values(locations, "value")),
        "source_protein_location_ids": "; ".join(_unique_values(locations, "id")),
        "source_protein_location_evidence_codes": "; ".join(_unique_values_from_lists(locations, "evidence_codes")),
        "source_protein_keywords": "; ".join(_unique_values(keywords, "name")),
        "source_protein_keyword_ids": "; ".join(_unique_values(keywords, "id")),
        "source_protein_keyword_evidence_codes": "; ".join(_unique_values_from_lists(keywords, "evidence_codes")),
        "source_protein_go_terms": "; ".join(_go_display_terms(go_terms)),
        "source_protein_go_ids": "; ".join(_unique_values(go_terms, "go_id")),
        "source_protein_go_evidence": "; ".join(_unique_values(go_terms, "go_evidence")),
        "source_protein_feature_types": "; ".join(_unique_values(features, "type")),
        "source_protein_feature_evidence_codes": "; ".join(_unique_values_from_lists(features, "evidence_codes")),
        "source_protein_uniprot_location_json": _json_dumps(locations),
        "source_protein_uniprot_keyword_json": _json_dumps(keywords),
        "source_protein_uniprot_go_json": _json_dumps(go_terms),
        "source_protein_uniprot_feature_json": _json_dumps(features),
        "source_protein_annotation_status": "未评估",
    }


def _source_evidence_text(item: dict) -> str:
    parts = [
        _protein_name(item),
        _source_location_summary(item),
        " ".join(_keyword_names(item)),
        " ".join(_go_terms(item)),
    ]
    feature_descriptions = [
        str(feature.get("type", ""))
        + " "
        + str(feature.get("description", ""))
        for feature in item.get("features", [])
    ]
    parts.extend(feature_descriptions)
    return " ".join(part for part in parts if part)


def _feature_types(item: dict) -> list[str]:
    values = [str(feature.get("type", "")) for feature in item.get("features", []) if feature.get("type")]
    return list(dict.fromkeys(values))


def _source_location_summary(item: dict) -> str:
    return "; ".join(_unique_values(_subcellular_location_terms(item), "value"))


def _subcellular_location_terms(item: dict) -> list[dict[str, object]]:
    comments = item.get("comments", [])
    terms: list[dict[str, object]] = []
    for comment in comments:
        if comment.get("commentType") != "SUBCELLULAR LOCATION":
            continue
        for location_item in comment.get("subcellularLocations", []):
            for kind in ("location", "topology", "orientation"):
                term = location_item.get(kind, {})
                if not isinstance(term, dict):
                    continue
                value = str(term.get("value", "")).strip()
                term_id = str(term.get("id", "")).strip()
                if not value and not term_id:
                    continue
                evidences = _evidence_entries(term.get("evidences", []))
                terms.append(
                    {
                        "source": "UniProtKB",
                        "kind": kind,
                        "id": term_id,
                        "value": value,
                        "evidence_codes": _unique_values(evidences, "evidence_code"),
                        "evidence_sources": _unique_values(evidences, "source"),
                    }
                )
    return terms


def _keyword_names(item: dict) -> list[str]:
    return [
        str(keyword.get("name", ""))
        for keyword in item.get("keywords", [])
        if keyword.get("name")
    ]


def _keyword_entries(item: dict) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for keyword in item.get("keywords", []):
        name = str(keyword.get("name", "")).strip()
        keyword_id = str(keyword.get("id", "")).strip()
        if not name and not keyword_id:
            continue
        evidences = _evidence_entries(keyword.get("evidences", []))
        entries.append(
            {
                "source": "UniProtKB",
                "id": keyword_id,
                "name": name,
                "category": keyword.get("category", ""),
                "evidence_codes": _unique_values(evidences, "evidence_code"),
                "evidence_sources": _unique_values(evidences, "source"),
            }
        )
    return entries


def _go_terms(item: dict) -> list[str]:
    return [
        str(entry.get("term", ""))
        for entry in _go_entries(item)
        if entry.get("term")
    ]


def _go_entries(item: dict) -> list[dict[str, object]]:
    terms: list[str] = []
    entries: list[dict[str, object]] = []
    for reference in item.get("uniProtKBCrossReferences", []):
        if reference.get("database") != "GO":
            continue
        go_id = str(reference.get("id", "")).strip()
        go_term = ""
        go_evidence = ""
        for prop in reference.get("properties", []):
            key = str(prop.get("key", ""))
            value = str(prop.get("value", ""))
            if key == "GoTerm" and value.startswith("C:"):
                go_term = value[2:]
            elif key == "GoEvidenceType":
                go_evidence = value
        if go_id and go_term:
            entries.append(
                {
                    "source": "UniProtKB cross-reference",
                    "go_id": go_id,
                    "term": go_term,
                    "go_evidence": go_evidence,
                }
            )
    return entries


def _feature_entries(item: dict) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for feature in item.get("features", []):
        feature_type = str(feature.get("type", "")).strip()
        if not feature_type:
            continue
        evidences = _evidence_entries(feature.get("evidences", []))
        entries.append(
            {
                "source": "UniProtKB feature",
                "type": feature_type,
                "description": str(feature.get("description", "")),
                "evidence_codes": _unique_values(evidences, "evidence_code"),
                "evidence_sources": _unique_values(evidences, "source"),
            }
        )
    return entries


def _evidence_entries(evidences: object) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if not isinstance(evidences, list):
        return entries
    for evidence in evidences:
        if not isinstance(evidence, dict):
            continue
        entries.append(
            {
                "evidence_code": str(evidence.get("evidenceCode", "")).strip(),
                "source": str(evidence.get("source", "")).strip(),
                "id": str(evidence.get("id", "")).strip(),
            }
        )
    return entries


def _go_display_terms(entries: list[dict[str, object]]) -> list[str]:
    values: list[str] = []
    for entry in entries:
        go_id = str(entry.get("go_id", "")).strip()
        term = str(entry.get("term", "")).strip()
        evidence = str(entry.get("go_evidence", "")).strip()
        if not go_id and not term:
            continue
        label = f"{go_id} {term}".strip()
        if evidence:
            label += f" [{evidence}]"
        values.append(label)
    return values


def _unique_values(entries: list[dict[str, object]], key: str) -> list[str]:
    values = [str(entry.get(key, "")).strip() for entry in entries if str(entry.get(key, "")).strip()]
    return list(dict.fromkeys(values))


def _unique_values_from_lists(entries: list[dict[str, object]], key: str) -> list[str]:
    values: list[str] = []
    for entry in entries:
        raw_values = entry.get(key, [])
        if not isinstance(raw_values, list):
            raw_values = [raw_values]
        for value in raw_values:
            text = str(value).strip()
            if text:
                values.append(text)
    return list(dict.fromkeys(values))


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _is_reviewed_entry(item: dict) -> bool:
    entry_type = str(item.get("entryType", ""))
    text = entry_type.lower()
    return "reviewed" in text and "unreviewed" not in text


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()


def _safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    match = re.search(r"<([^>]+)>\s*;\s*rel=\"next\"", link_header)
    return match.group(1) if match else None
