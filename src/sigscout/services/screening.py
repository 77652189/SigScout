from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from sigscout.adapters.quickgo import QuickGOAnnotationSource
from sigscout.adapters.uspnet import USPNetAdapter
from sigscout.core.models import UniProtCandidateLibraryResult
from sigscout.services.exports import write_candidate_fasta, write_csv, write_json, write_signal_peptide_fasta
from sigscout.services.library import SignalPeptideLibraryService
from sigscout.services.rules import score_signal_peptide
from sigscout.services.source_protein_annotation import (
    annotate_source_protein_routes,
    ensure_source_protein_annotation_defaults,
)


UNIPROT_CANDIDATES_CSV = "uniprot_candidates.csv"
UNIPROT_DUPLICATES_CSV = "uniprot_duplicate_candidates.csv"
UNIPROT_DISCOVERY_SUMMARY_JSON = "uniprot_candidate_discovery_summary.json"
METHOD_INPUT_FASTA = "method_comparison_input.fasta"
METHOD_COMPARISON_CSV = "signal_peptide_method_comparison.csv"
RECOMMENDED_FASTA = "method_recommended_candidates.fasta"
REPRESENTATIVES_CSV = "signal_peptide_representatives.csv"
REPRESENTATIVES_FASTA = "method_representative_candidates.fasta"
METHOD_SUMMARY_JSON = "signal_peptide_method_comparison_summary.json"
SIMILARITY_IDENTITY_THRESHOLD = 0.80


@dataclass(frozen=True)
class SignalPeptideScreeningResult:
    available: bool
    success: bool
    message: str
    summary: dict[str, object]
    rows: list[dict[str, object]]
    output_dir: Path
    uniprot_csv: Path | None = None
    duplicate_csv: Path | None = None
    input_fasta: Path | None = None
    comparison_csv: Path | None = None
    recommended_fasta: Path | None = None
    representatives_csv: Path | None = None
    representatives_fasta: Path | None = None
    uspnet_raw_dir: Path | None = None
    summary_json: Path | None = None
    errors: list[str] | None = None


class SignalPeptideScreeningService:
    def __init__(
        self,
        output_dir: Path,
        *,
        library_service: SignalPeptideLibraryService | None = None,
        uspnet_adapter: USPNetAdapter | None = None,
        quickgo_source: QuickGOAnnotationSource | None = None,
        target_key: str = "opn",
        target_label: str = "OPN / 骨桥蛋白",
    ) -> None:
        self.output_dir = output_dir
        self.library_service = library_service or SignalPeptideLibraryService()
        self.uspnet_adapter = uspnet_adapter or USPNetAdapter()
        self.quickgo_source = quickgo_source or QuickGOAnnotationSource()
        self.target_key = target_key
        self.target_label = target_label

    def discover_and_persist_uniprot_candidates(
        self,
        *,
        taxon_id: int = 4922,
        max_records: int = 300,
        reviewed_only: bool = False,
        exclude_existing: bool = True,
    ) -> UniProtCandidateLibraryResult:
        query_at = _now_iso()
        discovery = self.library_service.discover_uniprot_candidate_library(
            taxon_id=taxon_id,
            max_records=max_records,
            reviewed_only=reviewed_only,
            exclude_existing=exclude_existing,
        )
        discovery = _with_query_at(discovery, query_at)
        discovery = UniProtCandidateLibraryResult(
            rows=[_ensure_target_context(row, self.target_key, self.target_label) for row in discovery.rows],
            source_url=discovery.source_url,
            errors=discovery.errors,
            initial_hit_count=discovery.initial_hit_count,
            fetched_record_count=discovery.fetched_record_count,
            extracted_signal_count=discovery.extracted_signal_count,
            deduplicated_count=discovery.deduplicated_count,
            duplicate_count=discovery.duplicate_count,
            duplicate_rows=[
                _ensure_target_context(row, self.target_key, self.target_label)
                for row in discovery.duplicate_rows
            ],
            query_at=discovery.query_at,
        )
        self._persist_uniprot_discovery(
            discovery,
            taxon_id=taxon_id,
            max_records=max_records,
            reviewed_only=reviewed_only,
            exclude_existing=exclude_existing,
        )
        return discovery

    def load_persisted_screening_result(self) -> SignalPeptideScreeningResult | None:
        paths = self._output_paths()
        summary_json = paths["summary_json"]
        comparison_csv = paths["comparison_csv"]
        if not comparison_csv.exists():
            return None
        try:
            payload = json.loads(summary_json.read_text(encoding="utf-8")) if summary_json.exists() else {}
            rows = [_ensure_screening_row_defaults(row) for row in _read_csv_rows(comparison_csv)]
        except (OSError, ValueError, pd.errors.ParserError):
            return None
        rows = _ensure_similarity_grouping(rows)
        rows = [_ensure_target_context(row, self.target_key, self.target_label) for row in rows]
        representative_rows = _representative_model_rows(rows)
        if rows and (not paths["representatives_csv"].exists() or not paths["representatives_fasta"].exists()):
            write_csv(paths["representatives_csv"], representative_rows)
            write_signal_peptide_fasta(paths["representatives_fasta"], representative_rows)
        summary = {key: value for key, value in payload.items() if key not in {"message", "errors"}}
        summary.setdefault("target_key", self.target_key)
        summary.setdefault("target_label", self.target_label)
        summary.setdefault("uniprot_candidate_source", "本地已保存的方法比较结果")
        summary.setdefault("uniprot_reused_from_disk", True)
        for key, value in _rules_score_distribution(rows).items():
            summary.setdefault(key, value)
        for key, value in _similarity_summary(rows).items():
            summary.setdefault(key, value)
        message = (
            f"已加载本地保存结果：候选 {len(rows)} 条，"
            f"代表序列 {summary.get('representative_candidate_count', 0)} 条。"
        )
        return SignalPeptideScreeningResult(
            available=bool(payload.get("uspnet_available", False)),
            success=bool(payload.get("success", True)),
            message=message,
            summary=summary,
            rows=rows,
            output_dir=paths["output_dir"],
            uniprot_csv=paths["uniprot_csv"],
            duplicate_csv=paths["duplicate_csv"],
            input_fasta=paths["input_fasta"],
            comparison_csv=comparison_csv,
            recommended_fasta=paths["recommended_fasta"],
            representatives_csv=paths["representatives_csv"],
            representatives_fasta=paths["representatives_fasta"],
            uspnet_raw_dir=Path(str(payload["uspnet_raw_dir"])) if payload.get("uspnet_raw_dir") else None,
            summary_json=summary_json if summary_json.exists() else None,
            errors=list(payload.get("errors", [])),
        )

    def screen_uniprot_candidates(
        self,
        *,
        taxon_id: int = 4922,
        max_records: int = 300,
        reviewed_only: bool = False,
        timeout_seconds: int = 3600,
        refresh_uniprot: bool = False,
    ) -> SignalPeptideScreeningResult:
        paths = self._output_paths()
        output_dir = paths["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)

        persisted_discovery = None if refresh_uniprot else self._load_persisted_uniprot_discovery(
            taxon_id=taxon_id,
            max_records=max_records,
            reviewed_only=reviewed_only,
            exclude_existing=True,
        )
        reused_uniprot = persisted_discovery is not None
        discovery = persisted_discovery or self.discover_and_persist_uniprot_candidates(
            taxon_id=taxon_id,
            max_records=max_records,
            reviewed_only=reviewed_only,
            exclude_existing=True,
        )
        candidate_rows = [
            _ensure_screening_row_defaults(_ensure_target_context(row, self.target_key, self.target_label))
            for row in discovery.rows
        ]
        write_candidate_fasta(paths["input_fasta"], candidate_rows)

        errors = list(discovery.errors)
        summary: dict[str, object] = {
            "target_key": self.target_key,
            "target_label": self.target_label,
            "taxon_id": taxon_id,
            "reviewed_only": reviewed_only,
            "max_records": max_records,
            "uniprot_query_at": discovery.query_at,
            "screening_run_at": _now_iso(),
            "uniprot_initial_hits": discovery.initial_hit_count,
            "uniprot_fetched_records": discovery.fetched_record_count,
            "uniprot_extracted_signal_count": discovery.extracted_signal_count,
            "uniprot_duplicate_count": discovery.duplicate_count,
            "deduplicated_candidates": discovery.deduplicated_count,
            "uniprot_candidate_source": "已复用本地保存的 UniProt 候选" if reused_uniprot else "UniProt API 实时查询",
            "uniprot_reused_from_disk": reused_uniprot,
            "uniprot_source_url": discovery.source_url,
            "rules_passed": 0,
            "rules_high_priority": 0,
            "rules_score_95_plus": 0,
            "rules_score_80_to_94": 0,
            "rules_score_65_to_79": 0,
            "rules_score_below_65": 0,
            "uspnet_available": False,
            "uspnet_success": False,
            "uspnet_completed": 0,
            "uspnet_passed": 0,
            "consensus_passed": 0,
            "needs_external_review": 0,
            "similarity_group_count": 0,
            "representative_candidate_count": 0,
            "similar_candidates_collapsed_count": 0,
        }

        if not candidate_rows:
            message = "UniProt 没有返回可用于比较的候选信号肽。"
            write_json(paths["summary_json"], {**summary, "success": False, "message": message, "errors": errors})
            return SignalPeptideScreeningResult(
                available=False,
                success=False,
                message=message,
                summary=summary,
                rows=[],
                output_dir=output_dir,
                uniprot_csv=paths["uniprot_csv"],
                duplicate_csv=paths["duplicate_csv"],
                input_fasta=paths["input_fasta"],
                representatives_csv=paths["representatives_csv"],
                representatives_fasta=paths["representatives_fasta"],
                summary_json=paths["summary_json"],
                errors=errors,
            )

        screened_rows = [_add_rule_screening(row) for row in candidate_rows]
        summary["rules_passed"] = sum(1 for row in screened_rows if row["rules_pass"])
        summary["rules_high_priority"] = sum(1 for row in screened_rows if row["rules_high_priority"])
        summary.update(_rules_score_distribution(screened_rows))

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        uspnet_raw_dir = output_dir / "uspnet_raw" / run_id
        uspnet_result = self.uspnet_adapter.run(paths["input_fasta"], uspnet_raw_dir, timeout_seconds=timeout_seconds)
        summary["uspnet_available"] = uspnet_result.available
        summary["uspnet_success"] = uspnet_result.success
        if not uspnet_result.available:
            errors.append(uspnet_result.message)
        else:
            prediction_by_id = {prediction.candidate_id: prediction for prediction in uspnet_result.predictions}
            screened_rows = [_merge_uspnet_screening(row, prediction_by_id) for row in screened_rows]
            summary["uspnet_completed"] = sum(1 for row in screened_rows if row["uspnet_completed"])
            summary["uspnet_passed"] = sum(1 for row in screened_rows if row["uspnet_pass"])
            if not uspnet_result.success:
                errors.append(uspnet_result.message)

        uspnet_results_usable = bool(summary["uspnet_success"])
        screened_rows = [_finalize_recommendation(row, uspnet_results_usable) for row in screened_rows]
        screened_rows = cluster_similar_signal_peptides(screened_rows)
        summary["consensus_passed"] = sum(1 for row in screened_rows if row["consensus_pass"])
        summary["needs_external_review"] = sum(1 for row in screened_rows if row["screening_status"] == "规则高优先级，待 USPNet 复核")
        summary.update(_similarity_summary(screened_rows))

        recommended_rows = [
            row
            for row in screened_rows
            if row["consensus_pass"] or row["screening_status"] == "规则高优先级，待 USPNet 复核"
        ]
        representative_rows = _representative_model_rows(screened_rows)
        write_csv(paths["comparison_csv"], screened_rows)
        write_signal_peptide_fasta(paths["recommended_fasta"], recommended_rows)
        write_csv(paths["representatives_csv"], representative_rows)
        write_signal_peptide_fasta(paths["representatives_fasta"], representative_rows)

        message = _screening_message(summary)
        write_json(
            paths["summary_json"],
            {
                **summary,
                "success": True,
                "message": message,
                "errors": errors,
                "uspnet_raw_dir": str(uspnet_raw_dir),
            },
        )
        return SignalPeptideScreeningResult(
            available=bool(summary["uspnet_available"]),
            success=True,
            message=message,
            summary=summary,
            rows=screened_rows,
            output_dir=output_dir,
            uniprot_csv=paths["uniprot_csv"],
            duplicate_csv=paths["duplicate_csv"],
            input_fasta=paths["input_fasta"],
            comparison_csv=paths["comparison_csv"],
            recommended_fasta=paths["recommended_fasta"],
            representatives_csv=paths["representatives_csv"],
            representatives_fasta=paths["representatives_fasta"],
            uspnet_raw_dir=uspnet_raw_dir,
            summary_json=paths["summary_json"],
            errors=errors,
        )

    def annotate_persisted_source_proteins(self, *, use_quickgo: bool = False) -> dict[str, object]:
        paths = self._output_paths()
        annotated_any = False
        summary_update: dict[str, object] = {}
        rows_by_path: dict[str, list[dict[str, object]]] = {}
        for key in ("uniprot_csv", "duplicate_csv", "comparison_csv"):
            path = paths[key]
            if path.exists():
                rows_by_path[key] = _read_csv_rows(path)

        quickgo_annotations_by_accession: dict[str, list[dict[str, object]]] | None = None
        quickgo_ancestors_by_id: dict[str, set[str]] = {}
        quickgo_terms_by_id: dict[str, str] = {}
        quickgo_errors: list[str] = []
        quickgo_query_at = ""
        if use_quickgo and rows_by_path:
            accessions = {
                str(row.get("accession", "")).strip()
                for rows in rows_by_path.values()
                for row in rows
                if str(row.get("accession", "")).strip()
            }
            quickgo_result = self.quickgo_source.fetch_cellular_component_annotations(accessions)
            quickgo_annotations_by_accession = quickgo_result.annotations_by_accession
            quickgo_ancestors_by_id = quickgo_result.go_ancestors_by_id
            quickgo_terms_by_id = quickgo_result.go_terms_by_id
            quickgo_errors = quickgo_result.errors
            quickgo_query_at = quickgo_result.query_at

        annotation_kwargs = {
            "quickgo_annotations_by_accession": quickgo_annotations_by_accession,
            "go_ancestors_by_id": quickgo_ancestors_by_id,
            "go_terms_by_id": quickgo_terms_by_id,
            "quickgo_query_at": quickgo_query_at,
            "quickgo_errors": quickgo_errors,
        }

        if "uniprot_csv" in rows_by_path:
            result = annotate_source_protein_routes(rows_by_path["uniprot_csv"], **annotation_kwargs)
            write_csv(paths["uniprot_csv"], result.rows)
            summary_update.update(result.summary)
            annotated_any = True

        if "duplicate_csv" in rows_by_path:
            result = annotate_source_protein_routes(rows_by_path["duplicate_csv"], **annotation_kwargs)
            write_csv(paths["duplicate_csv"], result.rows)
            annotated_any = True

        if "comparison_csv" in rows_by_path:
            result = annotate_source_protein_routes(rows_by_path["comparison_csv"], **annotation_kwargs)
            comparison_rows = _ensure_similarity_grouping([_ensure_screening_row_defaults(row) for row in result.rows])
            representative_rows = _representative_model_rows(comparison_rows)
            write_csv(paths["comparison_csv"], comparison_rows)
            write_csv(paths["representatives_csv"], representative_rows)
            summary_update.update(result.summary)
            annotated_any = True

        if annotated_any:
            summary_payload = _read_json_dict(paths["summary_json"])
            if summary_payload:
                write_json(paths["summary_json"], {**summary_payload, **summary_update})
            discovery_payload = _read_json_dict(paths["discovery_summary_json"])
            if discovery_payload:
                write_json(paths["discovery_summary_json"], {**discovery_payload, **summary_update})
            return {
                **summary_update,
                "success": True,
                "message": f"已完成来源蛋白辅助评估：{summary_update.get('source_protein_annotated_count', 0)} 条。",
            }

        return {
            "success": False,
            "message": "没有找到可评估的候选 CSV；请先刷新毕赤酵母信号肽筛选结果。",
        }

    def _output_paths(self) -> dict[str, Path]:
        output_dir = self.output_dir
        return {
            "output_dir": output_dir,
            "uniprot_csv": output_dir / UNIPROT_CANDIDATES_CSV,
            "duplicate_csv": output_dir / UNIPROT_DUPLICATES_CSV,
            "discovery_summary_json": output_dir / UNIPROT_DISCOVERY_SUMMARY_JSON,
            "input_fasta": output_dir / METHOD_INPUT_FASTA,
            "comparison_csv": output_dir / METHOD_COMPARISON_CSV,
            "recommended_fasta": output_dir / RECOMMENDED_FASTA,
            "representatives_csv": output_dir / REPRESENTATIVES_CSV,
            "representatives_fasta": output_dir / REPRESENTATIVES_FASTA,
            "summary_json": output_dir / METHOD_SUMMARY_JSON,
        }

    def _persist_uniprot_discovery(
        self,
        discovery: UniProtCandidateLibraryResult,
        *,
        taxon_id: int,
        max_records: int,
        reviewed_only: bool,
        exclude_existing: bool,
    ) -> None:
        paths = self._output_paths()
        write_csv(paths["uniprot_csv"], discovery.rows)
        write_csv(paths["duplicate_csv"], discovery.duplicate_rows)
        write_candidate_fasta(paths["input_fasta"], discovery.rows)
        write_json(
            paths["discovery_summary_json"],
            {
                "taxon_id": taxon_id,
                "max_records": max_records,
                "reviewed_only": reviewed_only,
                "exclude_existing": exclude_existing,
                "source_url": discovery.source_url,
                "query_at": discovery.query_at,
                "initial_hit_count": discovery.initial_hit_count,
                "fetched_record_count": discovery.fetched_record_count,
                "extracted_signal_count": discovery.extracted_signal_count,
                "deduplicated_count": discovery.deduplicated_count,
                "duplicate_count": discovery.duplicate_count,
                "errors": discovery.errors,
            },
        )

    def _load_persisted_uniprot_discovery(
        self,
        *,
        taxon_id: int,
        max_records: int,
        reviewed_only: bool,
        exclude_existing: bool,
    ) -> UniProtCandidateLibraryResult | None:
        paths = self._output_paths()
        summary = _read_json_dict(paths["discovery_summary_json"])
        if not paths["uniprot_csv"].exists():
            return None
        if summary and not _discovery_summary_matches(
            summary,
            taxon_id=taxon_id,
            max_records=max_records,
            reviewed_only=reviewed_only,
            exclude_existing=exclude_existing,
        ):
            return None
        try:
            rows = _read_csv_rows(paths["uniprot_csv"])
            duplicate_rows = _read_csv_rows(paths["duplicate_csv"]) if paths["duplicate_csv"].exists() else []
        except (OSError, pd.errors.ParserError):
            return None
        return UniProtCandidateLibraryResult(
            rows=rows,
            source_url=str(summary.get("source_url", "local persisted uniprot_candidates.csv")),
            errors=list(summary.get("errors", [])),
            initial_hit_count=_safe_int_value(summary.get("initial_hit_count", len(rows))),
            fetched_record_count=_safe_int_value(summary.get("fetched_record_count", len(rows))),
            extracted_signal_count=_safe_int_value(summary.get("extracted_signal_count", len(rows) + len(duplicate_rows))),
            deduplicated_count=_safe_int_value(summary.get("deduplicated_count", len(rows))),
            duplicate_count=_safe_int_value(summary.get("duplicate_count", len(duplicate_rows))),
            duplicate_rows=duplicate_rows,
            query_at=str(summary.get("query_at", "")),
        )


def _add_rule_screening(row: dict[str, object]) -> dict[str, object]:
    sequence = str(row.get("signal_peptide_sequence", ""))
    result = score_signal_peptide(sequence)
    return {
        **row,
        "uniprot_signal_annotated": bool(row.get("uniprot_signal_start")) and bool(row.get("uniprot_signal_end")),
        "rules_score": result.score,
        "rules_pass": result.passed,
        "rules_high_priority": result.passed and result.score >= 90,
        "rules_priority": "高" if result.passed and result.score >= 90 else ("中" if result.passed else "低"),
        "rules_score_note": _rules_score_note(result.score, result.passed),
        "rules_tier": result.tier,
        "rules_reasons": "；".join(result.reasons),
        "rules_risks": "；".join(result.risks),
        "rules_n_region_positive_count": result.n_region_positive_count,
        "rules_n_region_negative_count": result.n_region_negative_count,
        "rules_n_region_pass": result.n_region_pass,
        "rules_h_region_max_hydrophobicity": result.h_region_max_hydrophobicity,
        "rules_h_region_hydrophobic_count": result.h_region_hydrophobic_count,
        "rules_h_region_pass": result.h_region_pass,
        "rules_c_region_small_neutral": result.c_region_small_neutral_rule,
        "rules_c_region_pass": result.c_region_pass,
        "uspnet_completed": False,
        "uspnet_prediction": "",
        "uspnet_prediction_label": "未运行",
        "uspnet_interpretation": "尚未得到 USPNet 预测结果。",
        "uspnet_cleavage_sequence": "",
        "uspnet_pass": False,
    }


def _merge_uspnet_screening(row: dict[str, object], prediction_by_id: dict[str, object]) -> dict[str, object]:
    prediction = prediction_by_id.get(str(row.get("candidate_id", "")))
    if prediction is None:
        return {**row, "uspnet_completed": False}
    return {
        **row,
        "uspnet_completed": True,
        "uspnet_prediction": prediction.predicted_type,
        "uspnet_prediction_label": _uspnet_prediction_label(prediction.predicted_type),
        "uspnet_interpretation": _uspnet_interpretation(prediction.predicted_type, prediction.passed),
        "uspnet_cleavage_sequence": prediction.predicted_cleavage,
        "uspnet_pass": prediction.passed,
    }


def _finalize_recommendation(row: dict[str, object], uspnet_results_usable: bool) -> dict[str, object]:
    rules_high = bool(row.get("rules_high_priority"))
    uspnet_pass = bool(row.get("uspnet_pass"))
    consensus = bool(uspnet_results_usable and rules_high and uspnet_pass)
    if consensus:
        status = "多方法一致通过"
        recommended = True
    elif rules_high and not uspnet_results_usable:
        status = "规则高优先级，待 USPNet 复核"
        recommended = True
    elif rules_high and not uspnet_pass:
        status = "规则通过但 USPNet 不支持"
        recommended = False
    elif bool(row.get("rules_pass")):
        status = "规则中等通过，需人工复核"
        recommended = False
    else:
        status = "规则不推荐"
        recommended = False
    return {
        **row,
        "consensus_pass": consensus,
        "screening_status": status,
        "recommended_for_draft_library": recommended,
    }


def cluster_similar_signal_peptides(
    rows: list[dict[str, object]],
    identity_threshold: float = SIMILARITY_IDENTITY_THRESHOLD,
) -> list[dict[str, object]]:
    groups: list[list[dict[str, object]]] = []
    seen_exact_sequences: set[str] = set()
    for row in rows:
        sequence = str(row.get("signal_peptide_sequence", "")).strip().upper()
        row_copy = dict(row)
        if sequence and sequence in seen_exact_sequences:
            groups.append([row_copy])
            continue
        placed = False
        for group in groups:
            if any(
                _is_similar_but_not_identical(sequence, str(member.get("signal_peptide_sequence", "")), identity_threshold)
                for member in group
            ):
                group.append(row_copy)
                placed = True
                break
        if not placed:
            groups.append([row_copy])
        if sequence:
            seen_exact_sequences.add(sequence)

    clustered_rows: list[dict[str, object]] = []
    for index, group in enumerate(groups, start=1):
        representative = choose_representative(group)
        representative_id = str(representative.get("candidate_id", ""))
        group_id = f"SPG_{index:03d}"
        for row in group:
            similarity = signal_peptide_identity(
                str(row.get("signal_peptide_sequence", "")),
                str(representative.get("signal_peptide_sequence", "")),
            )
            clustered_rows.append(
                {
                    **row,
                    "similarity_group_id": group_id,
                    "is_representative": str(row.get("candidate_id", "")) == representative_id,
                    "representative_id": representative_id,
                    "similarity_to_representative": round(similarity, 3),
                    "similar_group_size": len(group),
                }
            )
    return clustered_rows


def choose_representative(group_rows: list[dict[str, object]]) -> dict[str, object]:
    if not group_rows:
        return {}
    return sorted(group_rows, key=_representative_sort_key)[0]


def signal_peptide_identity(seq_a: str, seq_b: str) -> float:
    a = seq_a.strip().upper()
    b = seq_b.strip().upper()
    if not a or not b:
        return 0.0
    distance = _levenshtein_distance(a, b)
    return max(0.0, 1.0 - (distance / max(len(a), len(b))))


def _is_similar_but_not_identical(seq_a: str, seq_b: str, identity_threshold: float) -> bool:
    if not seq_a or not seq_b or seq_a.strip().upper() == seq_b.strip().upper():
        return False
    return signal_peptide_identity(seq_a, seq_b) >= identity_threshold


def _representative_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        not bool(row.get("consensus_pass")),
        not _uspnet_supports_signal_peptide(row),
        not bool(row.get("rules_high_priority")),
        -_safe_int_value(row.get("rules_score")),
        not _reviewed_or_strong_evidence(row),
        len(str(row.get("signal_peptide_sequence", ""))),
        str(row.get("candidate_id", "")),
    )


def _uspnet_supports_signal_peptide(row: dict[str, object]) -> bool:
    return bool(row.get("uspnet_pass")) or str(row.get("uspnet_prediction", "")).strip().upper() == "SP"


def _reviewed_or_strong_evidence(row: dict[str, object]) -> bool:
    if bool(row.get("uniprot_reviewed")):
        return True
    text = " ".join(
        str(row.get(key, ""))
        for key in ("source_note", "rationale", "protein_existence", "evidence_level")
    ).lower()
    return "reviewed" in text or "evidence at protein level" in text


def _levenshtein_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for index_a, char_a in enumerate(a, start=1):
        current = [index_a]
        for index_b, char_b in enumerate(b, start=1):
            substitution = previous[index_b - 1] + (0 if char_a == char_b else 1)
            insertion = current[index_b - 1] + 1
            deletion = previous[index_b] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def _representative_model_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if bool(row.get("recommended_for_draft_library")) and bool(row.get("is_representative"))
    ]


def _ensure_target_context(row: dict[str, object], target_key: str, target_label: str) -> dict[str, object]:
    return {
        **row,
        "target_key": str(row.get("target_key") or target_key),
        "target_label": str(row.get("target_label") or target_label),
    }


def _with_query_at(discovery: UniProtCandidateLibraryResult, query_at: str) -> UniProtCandidateLibraryResult:
    if discovery.query_at:
        return discovery
    return UniProtCandidateLibraryResult(
        rows=discovery.rows,
        source_url=discovery.source_url,
        errors=discovery.errors,
        initial_hit_count=discovery.initial_hit_count,
        fetched_record_count=discovery.fetched_record_count,
        extracted_signal_count=discovery.extracted_signal_count,
        deduplicated_count=discovery.deduplicated_count,
        duplicate_count=discovery.duplicate_count,
        duplicate_rows=discovery.duplicate_rows,
        query_at=query_at,
    )


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _read_json_dict(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_csv_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        frame = pd.read_csv(path).fillna("")
    except pd.errors.EmptyDataError:
        return []
    return [_coerce_row_types(row) for row in frame.to_dict(orient="records")]


def _coerce_row_types(row: dict[str, object]) -> dict[str, object]:
    bool_columns = {
        "already_in_formal_library",
        "uniprot_reviewed",
        "uniprot_signal_annotated",
        "rules_pass",
        "rules_high_priority",
        "rules_n_region_pass",
        "rules_h_region_pass",
        "rules_c_region_small_neutral",
        "rules_c_region_pass",
        "uspnet_completed",
        "uspnet_pass",
        "consensus_pass",
        "recommended_for_draft_library",
        "is_representative",
    }
    coerced = dict(row)
    for column in bool_columns:
        if column in coerced:
            coerced[column] = _coerce_bool(coerced[column])
    return coerced


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _ensure_screening_row_defaults(row: dict[str, object]) -> dict[str, object]:
    updated = _coerce_row_types(row)
    updated.setdefault("rules_n_region_negative_count", 0)
    updated.setdefault("rules_n_region_pass", _safe_int_value(updated.get("rules_n_region_positive_count")) >= 1)
    updated.setdefault("rules_h_region_hydrophobic_count", 0)
    updated.setdefault("rules_h_region_pass", float(updated.get("rules_h_region_max_hydrophobicity") or 0) >= 1.8)
    updated.setdefault("rules_c_region_pass", bool(updated.get("rules_c_region_small_neutral")))
    updated.setdefault("uspnet_prediction_label", _uspnet_prediction_label(str(updated.get("uspnet_prediction", ""))))
    updated.setdefault(
        "uspnet_interpretation",
        _uspnet_interpretation(str(updated.get("uspnet_prediction", "")), bool(updated.get("uspnet_pass"))),
    )
    updated.setdefault("similarity_group_id", "")
    updated.setdefault("is_representative", False)
    updated.setdefault("representative_id", "")
    updated.setdefault("similarity_to_representative", 0.0)
    updated.setdefault("similar_group_size", 1)
    return ensure_source_protein_annotation_defaults(updated)


def _ensure_similarity_grouping(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if not rows:
        return rows
    if all(str(row.get("similarity_group_id", "")).strip() for row in rows):
        return rows
    return cluster_similar_signal_peptides(rows)


def _discovery_summary_matches(
    summary: dict[str, object],
    *,
    taxon_id: int,
    max_records: int,
    reviewed_only: bool,
    exclude_existing: bool,
) -> bool:
    return (
        _safe_int_value(summary.get("taxon_id")) == taxon_id
        and _safe_int_value(summary.get("max_records")) == max_records
        and bool(summary.get("reviewed_only")) == reviewed_only
        and bool(summary.get("exclude_existing", True)) == exclude_existing
    )


def _rules_score_distribution(rows: list[dict[str, object]]) -> dict[str, int]:
    scores = [_safe_int_value(row.get("rules_score")) for row in rows]
    return {
        "rules_score_95_plus": sum(1 for score in scores if score >= 95),
        "rules_score_80_to_94": sum(1 for score in scores if 80 <= score <= 94),
        "rules_score_65_to_79": sum(1 for score in scores if 65 <= score <= 79),
        "rules_score_below_65": sum(1 for score in scores if score < 65),
    }


def _similarity_summary(rows: list[dict[str, object]]) -> dict[str, int]:
    model_ready_rows = [row for row in rows if bool(row.get("recommended_for_draft_library"))]
    representatives = [row for row in model_ready_rows if bool(row.get("is_representative"))]
    group_ids = {str(row.get("similarity_group_id", "")) for row in model_ready_rows if row.get("similarity_group_id")}
    return {
        "similarity_group_count": len(group_ids),
        "representative_candidate_count": len(representatives),
        "similar_candidates_collapsed_count": max(0, len(model_ready_rows) - len(representatives)),
    }


def _safe_int_value(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _rules_score_note(score: int, passed: bool) -> str:
    if score >= 95:
        return "典型信号肽特征完整；只说明像 signal peptide，不代表产量更高。"
    if score >= 80:
        return "主要结构特征较完整，适合进入候选讨论。"
    if passed:
        return "规则通过但有明显不确定性，建议人工复核。"
    return "规则不支持优先进入实验候选。"


def _uspnet_prediction_label(predicted_type: str) -> str:
    prediction = predicted_type.strip().upper()
    labels = {
        "SP": "SP：经典 Sec/SPI 信号肽（默认通过）",
        "NO_SP": "NO_SP：USPNet 不支持信号肽",
        "LIPO": "LIPO：脂蛋白信号肽（非默认目标）",
        "TAT": "TAT：Tat 通路信号肽（非默认目标）",
        "TATLIPO": "TATLIPO：Tat 脂蛋白信号肽（非默认目标）",
        "PILIN": "PILIN：菌毛相关信号肽（非默认目标）",
    }
    if prediction:
        return labels.get(prediction, f"{prediction}：USPNet 原始类别")
    return "未运行"


def _uspnet_interpretation(predicted_type: str, passed: bool) -> str:
    prediction = predicted_type.strip().upper()
    if passed:
        return "USPNet 支持该序列为经典 Sec/SPI 信号肽，符合本项目默认筛选目标。"
    if prediction == "NO_SP":
        return "机器学习复核不支持该序列作为信号肽，建议降级或人工复核。"
    if prediction in {"LIPO", "TAT", "TATLIPO", "PILIN"}:
        return "USPNet 判断为信号相关但非经典 Sec/SPI 类型；用于毕赤酵母常规分泌表达时不作为默认通过。"
    if prediction:
        return "USPNet 给出非 SP 类别，需结合规则和来源证据人工判断。"
    return "尚未得到 USPNet 预测结果。"


def _screening_message(summary: dict[str, object]) -> str:
    base = (
        f"UniProt 初始命中 {summary['uniprot_initial_hits']} 条，"
        f"去重后 {summary['deduplicated_candidates']} 条，"
        f"规则高优先级 {summary['rules_high_priority']} 条，"
        f"代表序列 {summary['representative_candidate_count']} 条。"
    )
    if summary["uspnet_success"]:
        return base + f"USPNet 通过 {summary['uspnet_passed']} 条，多方法一致通过 {summary['consensus_passed']} 条。"
    if summary["uspnet_available"]:
        return base + "USPNet 已检测到，但本次运行未完成，因此没有一致通过结论。"
    return base + "USPNet 尚未安装，因此当前结果来自 UniProt 注释和透明规则筛选。"
