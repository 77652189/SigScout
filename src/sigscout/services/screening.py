from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from sigscout.adapters.quickgo import QuickGOAnnotationSource
from sigscout.adapters.uspnet import USPNetAdapter
from sigscout.core.coercion import now_iso, safe_int_from_float, truthy
from sigscout.core.models import UniProtCandidateLibraryResult
from sigscout.services.exports import write_candidate_fasta, write_csv, write_json, write_signal_peptide_fasta
from sigscout.services.library import SignalPeptideLibraryService
from sigscout.services.rules import score_signal_peptide
from sigscout.services.similarity import cluster_similar_signal_peptides
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
        query_at = now_iso()
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

        candidate_rows, discovery, reused_uniprot = self._discover_step(
            paths,
            taxon_id=taxon_id,
            max_records=max_records,
            reviewed_only=reviewed_only,
            refresh_uniprot=refresh_uniprot,
        )
        errors = list(discovery.errors)
        summary = self._build_initial_summary(
            taxon_id=taxon_id,
            max_records=max_records,
            reviewed_only=reviewed_only,
            discovery=discovery,
            reused_uniprot=reused_uniprot,
        )

        if not candidate_rows:
            return self._empty_screening_result(paths, output_dir, summary, errors)

        screened_rows = self._rule_score_step(candidate_rows, summary)
        screened_rows, uspnet_raw_dir = self._uspnet_merge_step(
            screened_rows, output_dir, paths["input_fasta"], summary, errors, timeout_seconds
        )
        screened_rows = self._similarity_step(screened_rows, summary)

        return self._finalize_screening_result(paths, output_dir, screened_rows, summary, errors, uspnet_raw_dir)

    def _discover_step(
        self,
        paths: dict[str, Path],
        *,
        taxon_id: int,
        max_records: int,
        reviewed_only: bool,
        refresh_uniprot: bool,
    ) -> tuple[list[dict[str, object]], UniProtCandidateLibraryResult, bool]:
        previous_annotation_rows = (
            _read_csv_rows(paths["comparison_csv"])
            if paths["comparison_csv"].exists()
            else []
        )
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
        candidate_rows = _merge_preserved_source_annotations(candidate_rows, previous_annotation_rows)
        write_candidate_fasta(paths["input_fasta"], candidate_rows)
        return candidate_rows, discovery, reused_uniprot

    def _build_initial_summary(
        self,
        *,
        taxon_id: int,
        max_records: int,
        reviewed_only: bool,
        discovery: UniProtCandidateLibraryResult,
        reused_uniprot: bool,
    ) -> dict[str, object]:
        return {
            "target_key": self.target_key,
            "target_label": self.target_label,
            "taxon_id": taxon_id,
            "reviewed_only": reviewed_only,
            "max_records": max_records,
            "uniprot_query_at": discovery.query_at,
            "screening_run_at": now_iso(),
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

    def _empty_screening_result(
        self,
        paths: dict[str, Path],
        output_dir: Path,
        summary: dict[str, object],
        errors: list[str],
    ) -> SignalPeptideScreeningResult:
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

    def _rule_score_step(
        self,
        candidate_rows: list[dict[str, object]],
        summary: dict[str, object],
    ) -> list[dict[str, object]]:
        screened_rows = [_add_rule_screening(row) for row in candidate_rows]
        summary["rules_passed"] = sum(1 for row in screened_rows if row["rules_pass"])
        summary["rules_high_priority"] = sum(1 for row in screened_rows if row["rules_high_priority"])
        summary.update(_rules_score_distribution(screened_rows))
        return screened_rows

    def _uspnet_merge_step(
        self,
        screened_rows: list[dict[str, object]],
        output_dir: Path,
        input_fasta: Path,
        summary: dict[str, object],
        errors: list[str],
        timeout_seconds: int,
    ) -> tuple[list[dict[str, object]], Path]:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        uspnet_raw_dir = output_dir / "uspnet_raw" / run_id
        uspnet_result = self.uspnet_adapter.run(input_fasta, uspnet_raw_dir, timeout_seconds=timeout_seconds)
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
        return screened_rows, uspnet_raw_dir

    def _similarity_step(
        self,
        screened_rows: list[dict[str, object]],
        summary: dict[str, object],
    ) -> list[dict[str, object]]:
        uspnet_results_usable = bool(summary["uspnet_success"])
        screened_rows = [_finalize_recommendation(row, uspnet_results_usable) for row in screened_rows]
        screened_rows = cluster_similar_signal_peptides(screened_rows)
        summary["consensus_passed"] = sum(1 for row in screened_rows if row["consensus_pass"])
        summary["needs_external_review"] = sum(
            1 for row in screened_rows if row["screening_status"] == "规则高优先级，待 USPNet 复核"
        )
        summary.update(_similarity_summary(screened_rows))
        return screened_rows

    def _finalize_screening_result(
        self,
        paths: dict[str, Path],
        output_dir: Path,
        screened_rows: list[dict[str, object]],
        summary: dict[str, object],
        errors: list[str],
        uspnet_raw_dir: Path,
    ) -> SignalPeptideScreeningResult:
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
        rows_by_path = self._load_persisted_rows_for_annotation(paths)
        annotation_kwargs = self._collect_quickgo_annotations(rows_by_path, use_quickgo=use_quickgo)
        annotated_any, summary_update = self._annotate_persisted_csv_files(rows_by_path, annotation_kwargs, paths)

        if not annotated_any:
            return {
                "success": False,
                "message": "没有找到可评估的候选 CSV；请先刷新毕赤酵母信号肽筛选结果。",
            }
        return self._finalize_source_protein_annotation(paths, summary_update)

    def _load_persisted_rows_for_annotation(
        self, paths: dict[str, Path]
    ) -> dict[str, list[dict[str, object]]]:
        rows_by_path: dict[str, list[dict[str, object]]] = {}
        for key in ("uniprot_csv", "duplicate_csv", "comparison_csv"):
            path = paths[key]
            if path.exists():
                rows_by_path[key] = _read_csv_rows(path)
        return rows_by_path

    def _collect_quickgo_annotations(
        self,
        rows_by_path: dict[str, list[dict[str, object]]],
        *,
        use_quickgo: bool,
    ) -> dict[str, object]:
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
        return {
            "quickgo_annotations_by_accession": quickgo_annotations_by_accession,
            "go_ancestors_by_id": quickgo_ancestors_by_id,
            "go_terms_by_id": quickgo_terms_by_id,
            "quickgo_query_at": quickgo_query_at,
            "quickgo_errors": quickgo_errors,
        }

    def _annotate_persisted_csv_files(
        self,
        rows_by_path: dict[str, list[dict[str, object]]],
        annotation_kwargs: dict[str, object],
        paths: dict[str, Path],
    ) -> tuple[bool, dict[str, object]]:
        annotated_any = False
        summary_update: dict[str, object] = {}

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

        return annotated_any, summary_update

    def _finalize_source_protein_annotation(
        self,
        paths: dict[str, Path],
        summary_update: dict[str, object],
    ) -> dict[str, object]:
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
            initial_hit_count=safe_int_from_float(summary.get("initial_hit_count", len(rows))),
            fetched_record_count=safe_int_from_float(summary.get("fetched_record_count", len(rows))),
            extracted_signal_count=safe_int_from_float(summary.get("extracted_signal_count", len(rows) + len(duplicate_rows))),
            deduplicated_count=safe_int_from_float(summary.get("deduplicated_count", len(rows))),
            duplicate_count=safe_int_from_float(summary.get("duplicate_count", len(duplicate_rows))),
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
            coerced[column] = truthy(coerced[column])
    return coerced


def _merge_preserved_source_annotations(
    current_rows: list[dict[str, object]],
    previous_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep completed source evidence for unchanged UniProt accessions across refreshes."""
    completed_by_accession = {
        str(row.get("accession", "")).strip(): row
        for row in previous_rows
        if str(row.get("accession", "")).strip()
        and str(row.get("source_protein_annotation_status", "")).strip() == "已评估"
    }
    if not completed_by_accession:
        return current_rows
    merged_rows = []
    for row in current_rows:
        previous = completed_by_accession.get(str(row.get("accession", "")).strip())
        if previous is None:
            merged_rows.append(row)
            continue
        updated = dict(row)
        for key, value in previous.items():
            if key.startswith("source_protein_"):
                updated[key] = value
        merged_rows.append(updated)
    return merged_rows


def _ensure_screening_row_defaults(row: dict[str, object]) -> dict[str, object]:
    updated = _coerce_row_types(row)
    updated.setdefault("rules_n_region_negative_count", 0)
    updated.setdefault("rules_n_region_pass", safe_int_from_float(updated.get("rules_n_region_positive_count")) >= 1)
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
        safe_int_from_float(summary.get("taxon_id")) == taxon_id
        and safe_int_from_float(summary.get("max_records")) == max_records
        and bool(summary.get("reviewed_only")) == reviewed_only
        and bool(summary.get("exclude_existing", True)) == exclude_existing
    )


def _rules_score_distribution(rows: list[dict[str, object]]) -> dict[str, int]:
    scores = [safe_int_from_float(row.get("rules_score")) for row in rows]
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
