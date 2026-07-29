from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from sigscout.adapters.uspnet import USPNetAdapter
from sigscout.core.paths import ProjectPaths
from sigscout.services.library import SignalPeptideLibraryService
from sigscout.services.screening import SignalPeptideScreeningResult, SignalPeptideScreeningService


st.set_page_config(
    page_title="SigScout",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

PATHS = ProjectPaths.discover(Path(__file__))


def _css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }
        [data-testid="stMetricValue"] { font-size: 1.25rem; }
        h1, h2, h3 { letter-spacing: 0; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(148, 163, 184, 0.24);
            background: rgba(15, 23, 42, 0.22);
        }
        .candidate-title {
            font-size: 1.02rem;
            font-weight: 700;
            letter-spacing: 0;
            padding-top: 0.12rem;
        }
        .fusion-title {
            font-size: 1rem;
            font-weight: 750;
            letter-spacing: 0;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }
        .fusion-mini-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.65rem 0 0.7rem;
        }
        .fusion-mini-cell {
            border: 1px solid rgba(148, 163, 184, 0.20);
            background: rgba(15, 23, 42, 0.36);
            border-radius: 8px;
            padding: 0.55rem 0.65rem;
            min-height: 3.25rem;
        }
        .fusion-mini-cell span {
            display: block;
            color: #94a3b8;
            font-size: 0.74rem;
            line-height: 1.2;
            margin-bottom: 0.28rem;
        }
        .fusion-mini-cell strong {
            display: block;
            font-size: 1rem;
            line-height: 1.2;
            color: #e2e8f0;
        }
        .sig-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 1.65rem;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 650;
            white-space: nowrap;
            border: 1px solid rgba(148, 163, 184, 0.3);
        }
        .route-secreted { background: rgba(20, 184, 166, 0.18); color: #7dd3fc; border-color: rgba(20, 184, 166, 0.34); }
        .route-membrane { background: rgba(99, 102, 241, 0.18); color: #c4b5fd; border-color: rgba(129, 140, 248, 0.34); }
        .route-compartment { background: rgba(245, 158, 11, 0.17); color: #fcd34d; border-color: rgba(245, 158, 11, 0.34); }
        .route-intracellular { background: rgba(244, 63, 94, 0.16); color: #fda4af; border-color: rgba(244, 63, 94, 0.32); }
        .route-unknown { background: rgba(100, 116, 139, 0.22); color: #cbd5e1; border-color: rgba(148, 163, 184, 0.34); }
        .evidence-strong { background: rgba(34, 197, 94, 0.18); color: #86efac; border-color: rgba(34, 197, 94, 0.34); }
        .evidence-curated { background: rgba(59, 130, 246, 0.18); color: #93c5fd; border-color: rgba(59, 130, 246, 0.34); }
        .evidence-auto { background: rgba(234, 179, 8, 0.16); color: #fde68a; border-color: rgba(234, 179, 8, 0.34); }
        .evidence-none { background: rgba(100, 116, 139, 0.18); color: #cbd5e1; border-color: rgba(148, 163, 184, 0.3); }
        .identity-block {
            padding-top: 0.1rem;
        }
        .source-protein {
            font-weight: 650;
            line-height: 1.35;
            margin-bottom: 0.15rem;
        }
        .muted-line {
            color: #94a3b8;
            font-size: 0.82rem;
            line-height: 1.35;
        }
        .score-block {
            border-left: 1px solid rgba(148, 163, 184, 0.2);
            padding-left: 0.9rem;
        }
        .score-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.6rem;
            font-size: 0.82rem;
            color: #cbd5e1;
        }
        .score-track {
            width: 100%;
            height: 0.42rem;
            background: rgba(148, 163, 184, 0.18);
            border-radius: 999px;
            overflow: hidden;
            margin: 0.28rem 0 0.55rem;
        }
        .score-fill {
            height: 100%;
            background: linear-gradient(90deg, #14b8a6, #60a5fa);
            border-radius: 999px;
        }
        .mini-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
            margin-bottom: 0.45rem;
        }
        .mini-grid span {
            display: block;
            color: #94a3b8;
            font-size: 0.72rem;
        }
        .mini-grid strong {
            display: block;
            font-size: 0.9rem;
        }
        .sequence-row {
            margin: 0.7rem 0 0.55rem;
            padding: 0.65rem 0.75rem;
            border-radius: 8px;
            background: rgba(2, 6, 23, 0.34);
            border: 1px solid rgba(148, 163, 184, 0.18);
        }
        .sequence-row code {
            display: block;
            white-space: normal;
            overflow-wrap: anywhere;
            font-size: 0.9rem;
            line-height: 1.45;
            color: #e2e8f0;
            background: transparent;
            padding: 0;
        }
        .sequence-label {
            display: block;
            color: #94a3b8;
            font-size: 0.72rem;
            margin-bottom: 0.25rem;
        }
        .evidence-panel {
            padding: 0.65rem 0.75rem;
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.34);
            border: 1px solid rgba(148, 163, 184, 0.18);
            color: #dbeafe;
            font-size: 0.84rem;
            line-height: 1.5;
        }
        .evidence-label {
            color: #94a3b8;
            font-size: 0.72rem;
            margin-bottom: 0.22rem;
        }
        .pagination-status {
            min-height: 2.35rem;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #cbd5e1;
            font-size: 0.86rem;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(15, 23, 42, 0.24);
            border-radius: 8px;
            margin-top: 1.72rem;
            white-space: nowrap;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _local_screening_service() -> SignalPeptideScreeningService:
    return SignalPeptideScreeningService(
        PATHS.opn_screening_output_dir,
        library_service=SignalPeptideLibraryService(candidate_prefix="PICHIA_UNIPROT"),
        uspnet_adapter=USPNetAdapter(repo_dir=PATHS.uspnet_repo),
        target_key="pichia_signal_peptide_library",
        target_label="毕赤酵母信号肽库",
    )


def _example_screening_service() -> SignalPeptideScreeningService:
    return SignalPeptideScreeningService(
        PATHS.opn_saved_screening_dir,
        library_service=SignalPeptideLibraryService(candidate_prefix="PICHIA_UNIPROT"),
        uspnet_adapter=USPNetAdapter(repo_dir=PATHS.uspnet_repo),
        target_key="pichia_signal_peptide_library",
        target_label="毕赤酵母信号肽库",
    )


def _load_result() -> SignalPeptideScreeningResult | None:
    local = _local_screening_service().load_persisted_screening_result()
    if local is not None:
        return local
    return _example_screening_service().load_persisted_screening_result()


def _load_representative_frames() -> tuple[SignalPeptideScreeningResult, pd.DataFrame, pd.DataFrame] | None:
    result = _load_result()
    if result is None:
        st.warning("没有可展示的筛选结果。请先刷新毕赤酵母信号肽。")
        return None
    rows = _ensure_display_columns(pd.DataFrame(result.rows))
    if rows.empty:
        st.info("结果为空。")
        return None
    recommended = rows[rows["recommended_for_draft_library"] == True].copy()
    representatives = recommended[recommended["is_representative"] == True].copy()
    if representatives.empty:
        st.info("当前没有代表序列。")
        return None
    return result, rows, _ensure_display_columns(representatives)


def _ensure_display_columns(frame: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "source_protein_route": "未评估",
        "source_protein_route_confidence": "",
        "source_protein_evidence_level": "",
        "source_protein_route_basis": "",
        "source_protein_evidence_summary": "",
        "source_protein_location": "",
        "source_protein_location_ids": "",
        "source_protein_location_evidence_codes": "",
        "source_protein_keywords": "",
        "source_protein_keyword_ids": "",
        "source_protein_keyword_evidence_codes": "",
        "source_protein_go_terms": "",
        "source_protein_go_ids": "",
        "source_protein_go_evidence": "",
        "source_protein_feature_types": "",
        "source_protein_feature_evidence_codes": "",
        "source_protein_uniprot_location_json": "[]",
        "source_protein_uniprot_keyword_json": "[]",
        "source_protein_uniprot_go_json": "[]",
        "source_protein_uniprot_feature_json": "[]",
        "source_protein_quickgo_json": "[]",
        "source_protein_quickgo_count": 0,
        "source_protein_quickgo_query_at": "",
        "source_protein_annotation_status": "未评估",
        "source_protein_route_note": "尚未运行来源蛋白定位辅助评估。",
        "uspnet_completed": False,
        "uspnet_prediction": "",
        "uspnet_prediction_label": "未运行",
        "uspnet_interpretation": "尚未得到 USPNet 预测结果。",
        "uspnet_cleavage_sequence": "",
        "uspnet_pass": False,
    }
    updated = frame.copy()
    for column, value in defaults.items():
        if column not in updated.columns:
            updated[column] = value
    return updated


def _sorted_unique(series: pd.Series) -> list[str]:
    values = [str(value).strip() for value in series.fillna("").tolist() if str(value).strip()]
    preferred = ["分泌/胞外倾向", "膜/锚定倾向", "分泌通路腔室倾向", "胞内或非典型", "未知", "未评估"]
    seen = set(values)
    ordered = [value for value in preferred if value in seen]
    ordered.extend(sorted(value for value in seen if value not in preferred))
    return ordered


def _render_pagination_controls(
    *,
    total_items: int,
    page_size: int,
    page_key: str,
    key_prefix: str,
) -> tuple[int, int, int, int]:
    total_pages = max(1, (max(total_items, 1) + max(page_size, 1) - 1) // max(page_size, 1))
    current_page = _clamp_page(st.session_state.get(page_key, 1), total_pages)
    st.session_state[page_key] = current_page
    start = ((current_page - 1) * page_size) + 1 if total_items else 0
    end = min(current_page * page_size, total_items)

    cols = st.columns([0.9, 0.9, 1.1, 1.5, 0.8, 0.9, 0.9])
    cols[0].button(
        "第一页",
        key=f"{key_prefix}_first",
        disabled=current_page <= 1,
        on_click=_set_page,
        args=(page_key, 1),
    )
    cols[1].button(
        "上一页",
        key=f"{key_prefix}_previous",
        disabled=current_page <= 1,
        on_click=_set_page,
        args=(page_key, current_page - 1),
    )
    cols[2].markdown(
        f"<div class='pagination-status'>第 {current_page} / {total_pages} 页</div>",
        unsafe_allow_html=True,
    )
    jump_key = f"{key_prefix}_jump"
    cols[3].number_input(
        "跳转页",
        min_value=1,
        max_value=total_pages,
        value=current_page,
        step=1,
        key=jump_key,
    )
    cols[4].button(
        "跳转",
        key=f"{key_prefix}_go",
        on_click=_set_page_from_widget,
        args=(page_key, jump_key, total_pages),
    )
    cols[5].button(
        "下一页",
        key=f"{key_prefix}_next",
        disabled=current_page >= total_pages,
        on_click=_set_page,
        args=(page_key, current_page + 1),
    )
    cols[6].button(
        "最后一页",
        key=f"{key_prefix}_last",
        disabled=current_page >= total_pages,
        on_click=_set_page,
        args=(page_key, total_pages),
    )
    return current_page, total_pages, start, end


def _set_page(page_key: str, page: int) -> None:
    st.session_state[page_key] = int(page)


def _set_page_from_widget(page_key: str, widget_key: str, total_pages: int) -> None:
    st.session_state[page_key] = _clamp_page(st.session_state.get(widget_key, 1), total_pages)


def _clamp_page(value: object, total_pages: int) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError):
        page = 1
    return max(1, min(page, max(1, total_pages)))
