from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from sigscout.core.coercion import safe_float, safe_int_from_float
from sigscout.services.screening import SignalPeptideScreeningResult
from sigscout.ui._shared import (
    PATHS,
    _ensure_display_columns,
    _load_representative_frames,
    _render_pagination_controls,
    _sorted_unique,
)
from sigscout.ui.experimental_browser import render_opn_experimental_browser


def page_candidate_browser() -> None:
    render_representatives("候选浏览")


def page_evidence_distribution() -> None:
    render_representatives("证据分布")


def page_similar_sequences() -> None:
    render_representatives("相似序列")


def page_raw_data() -> None:
    render_representatives("原始数据")


def render_representatives(subpage: str = "候选浏览") -> None:
    st.subheader("代表序列与下载")
    loaded = _load_representative_frames()
    if loaded is None:
        return
    result, rows, representatives = loaded
    _render_representative_overview(rows, representatives)
    if subpage == "候选浏览":
        _render_candidate_browser(representatives)
    elif subpage == "证据分布":
        _render_distribution_panel(rows, representatives)
    elif subpage == "相似序列":
        _render_similar_sequence_details(rows, representatives)
    else:
        _render_raw_representative_table(representatives)
    st.divider()
    _render_downloads(result)


def _render_representative_table(representatives: pd.DataFrame) -> None:
    representatives = _ensure_display_columns(representatives)
    st.dataframe(
        representatives[
            [
                "candidate_id",
                "accession",
                "protein_name",
                "source_protein_route",
                "source_protein_evidence_level",
                "source_protein_route_basis",
                "signal_peptide_sequence",
                "similarity_group_id",
                "similar_group_size",
                "rules_n_region_positive_count",
                "rules_h_region_max_hydrophobicity",
                "rules_c_region_small_neutral",
                "rules_score",
                "uspnet_prediction",
                "uspnet_prediction_label",
                "uspnet_cleavage_sequence",
                "screening_status",
            ]
        ].rename(
            columns={
                "candidate_id": "候选 ID",
                "accession": "UniProt accession",
                "protein_name": "来源蛋白",
                "source_protein_route": "来源蛋白分类",
                "source_protein_evidence_level": "证据等级",
                "source_protein_route_basis": "依据说明",
                "signal_peptide_sequence": "信号肽序列",
                "similarity_group_id": "相似分组",
                "similar_group_size": "同组序列数",
                "rules_n_region_positive_count": "N区正电残基数",
                "rules_h_region_max_hydrophobicity": "H区最大疏水性",
                "rules_c_region_small_neutral": "C区切割规则",
                "rules_score": "规则分数",
                "uspnet_prediction": "USPNet 类型",
                "uspnet_prediction_label": "USPNet 预测",
                "uspnet_cleavage_sequence": "USPNet 切割片段",
                "screening_status": "综合状态",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


def _render_representative_workbench(rows: pd.DataFrame, representatives: pd.DataFrame) -> None:
    _render_representative_overview(rows, representatives)
    browser_tab, distribution_tab, similar_tab, raw_tab = st.tabs(
        ["候选浏览", "证据分布", "相似序列", "原始数据"]
    )
    with browser_tab:
        _render_candidate_browser(representatives)
    with distribution_tab:
        _render_distribution_panel(rows, representatives)
    with similar_tab:
        _render_similar_sequence_details(rows, representatives)
    with raw_tab:
        _render_raw_representative_table(representatives)


def _render_candidate_browser(representatives: pd.DataFrame) -> None:
    mode = st.segmented_control(
        "浏览模式", ["通用候选", "OPN 实验视图"],
        default="通用候选", key="candidate_browser_mode",
    )
    if mode == "OPN 实验视图":
        render_opn_experimental_browser(representatives, PATHS.local_runs_dir)
        return
    filtered = _render_candidate_filters(representatives)
    if filtered.empty:
        st.info("没有符合当前筛选条件的代表序列。")
        return
    max_cards = min(50, len(filtered))
    page_size = st.slider(
        "每页展示数量",
        min_value=1,
        max_value=max_cards,
        value=min(12, max_cards),
        step=1,
        key="candidate_browser_page_size",
    )
    page, total_pages, start, end = _render_pagination_controls(
        total_items=len(filtered),
        page_size=int(page_size),
        page_key="candidate_browser_page",
        key_prefix="candidate_browser_top",
    )
    st.caption(f"第 {start}-{end} 条，共 {len(filtered)} 条代表序列")
    _render_candidate_cards(filtered.iloc[start - 1 : end])
    _render_pagination_controls(
        total_items=len(filtered),
        page_size=int(page_size),
        page_key="candidate_browser_page",
        key_prefix="candidate_browser_bottom",
    )


def _render_representative_overview(rows: pd.DataFrame, representatives: pd.DataFrame) -> None:
    route_counts = representatives["source_protein_route"].astype(str).value_counts()
    evidence_counts = representatives["source_protein_evidence_level"].astype(str).value_counts()
    cols = st.columns(5)
    cols[0].metric("代表序列", len(representatives))
    cols[1].metric("推荐候选", int(rows["recommended_for_draft_library"].astype(bool).sum()))
    cols[2].metric("来源分类", int(route_counts[route_counts.index != "未评估"].shape[0]))
    cols[3].metric("自动证据", int(evidence_counts.get("自动/预测证据", 0)))
    cols[4].metric("未知来源", int(route_counts.get("未知", 0)))


def _render_candidate_filters(representatives: pd.DataFrame) -> pd.DataFrame:
    filter_cols = st.columns([1.2, 1.2, 1.6, 1.0])
    route_options = _sorted_unique(representatives["source_protein_route"])
    evidence_options = _sorted_unique(representatives["source_protein_evidence_level"])
    selected_routes = filter_cols[0].multiselect("来源分类", route_options, default=route_options)
    selected_evidence = filter_cols[1].multiselect("证据等级", evidence_options, default=evidence_options)
    search = filter_cols[2].text_input("搜索", placeholder="候选 ID / accession / 来源蛋白 / 证据")
    sort_by = filter_cols[3].selectbox(
        "排序",
        ["综合推荐优先", "证据较强优先", "规则分数高优先", "相似分组大优先"],
        index=0,
    )

    filtered = representatives.copy()
    if selected_routes:
        filtered = filtered[filtered["source_protein_route"].astype(str).isin(selected_routes)]
    if selected_evidence:
        filtered = filtered[filtered["source_protein_evidence_level"].astype(str).isin(selected_evidence)]
    if search.strip():
        pattern = search.strip()
        searchable = filtered[
            [
                "candidate_id",
                "accession",
                "protein_name",
                "source_protein_route_basis",
                "signal_peptide_sequence",
                "uspnet_prediction",
                "uspnet_prediction_label",
                "uspnet_cleavage_sequence",
            ]
        ].astype(str).agg(" ".join, axis=1)
        filtered = filtered[searchable.str.contains(pattern, case=False, regex=False, na=False)]
    filtered = _sort_representatives(filtered, sort_by)
    st.caption(f"当前筛选：{len(filtered)} 条代表序列")
    return filtered


def _render_candidate_cards(frame: pd.DataFrame) -> None:
    for _, row in frame.iterrows():
        with st.container(border=True):
            header_cols = st.columns([3.8, 1.2, 1.2])
            header_cols[0].markdown(
                f"<div class='candidate-title'>{escape(str(row.get('candidate_id', '')))}</div>",
                unsafe_allow_html=True,
            )
            header_cols[1].markdown(_route_badge(str(row.get("source_protein_route", ""))), unsafe_allow_html=True)
            header_cols[2].markdown(_evidence_badge(str(row.get("source_protein_evidence_level", ""))), unsafe_allow_html=True)

            body_cols = st.columns([2.1, 1.2])
            body_cols[0].markdown(
                _candidate_identity_html(row),
                unsafe_allow_html=True,
            )
            body_cols[1].markdown(_candidate_score_html(row), unsafe_allow_html=True)

            st.markdown(_sequence_html(str(row.get("signal_peptide_sequence", ""))), unsafe_allow_html=True)
            basis = str(row.get("source_protein_route_basis", "")).strip()
            summary = str(row.get("source_protein_evidence_summary", "")).strip()
            with st.expander("评分细节与依据说明"):
                st.markdown(_candidate_score_detail_html(row), unsafe_allow_html=True)
                st.markdown(
                    "<div class='evidence-panel'>"
                    f"<div class='evidence-label'>依据说明</div><div>{escape(basis or summary or '未记录明确依据')}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )


def _render_distribution_panel(rows: pd.DataFrame, representatives: pd.DataFrame) -> None:
    chart_cols = st.columns(3)
    with chart_cols[0]:
        st.markdown("**来源蛋白分类分布**")
        route_counts = representatives["source_protein_route"].astype(str).value_counts()
        st.bar_chart(pd.DataFrame({"数量": route_counts}))
    with chart_cols[1]:
        st.markdown("**证据等级分布**")
        evidence_counts = representatives["source_protein_evidence_level"].astype(str).value_counts()
        st.bar_chart(pd.DataFrame({"数量": evidence_counts}))
    with chart_cols[2]:
        st.markdown("**USPNet 类型分布**")
        uspnet_counts = representatives["uspnet_prediction"].replace("", "未运行").astype(str).value_counts()
        st.bar_chart(pd.DataFrame({"数量": uspnet_counts}))

    st.markdown("**规则分数与来源分类**")
    score_frame = representatives[["source_protein_route", "rules_score"]].copy()
    score_frame["rules_score"] = pd.to_numeric(score_frame["rules_score"], errors="coerce").fillna(0)
    grouped = score_frame.groupby("source_protein_route", dropna=False)["rules_score"].mean().sort_values(ascending=False)
    st.bar_chart(pd.DataFrame({"平均规则分数": grouped}))


def _render_raw_representative_table(representatives: pd.DataFrame) -> None:
    representatives = _ensure_display_columns(representatives)
    columns = [
        "candidate_id",
        "accession",
        "protein_name",
        "source_protein_route",
        "source_protein_evidence_level",
        "source_protein_route_basis",
        "signal_peptide_sequence",
        "similarity_group_id",
        "similar_group_size",
        "rules_score",
        "uspnet_prediction",
        "uspnet_prediction_label",
        "uspnet_cleavage_sequence",
        "uspnet_interpretation",
        "screening_status",
    ]
    st.dataframe(
        representatives[[column for column in columns if column in representatives.columns]].rename(
            columns={
                "candidate_id": "候选 ID",
                "accession": "UniProt accession",
                "protein_name": "来源蛋白",
                "source_protein_route": "来源蛋白分类",
                "source_protein_evidence_level": "证据等级",
                "source_protein_route_basis": "依据说明",
                "signal_peptide_sequence": "信号肽序列",
                "similarity_group_id": "相似分组",
                "similar_group_size": "同组序列数",
                "rules_score": "规则分数",
                "uspnet_prediction": "USPNet 类型",
                "uspnet_prediction_label": "USPNet 预测",
                "uspnet_cleavage_sequence": "USPNet 切割片段",
                "uspnet_interpretation": "USPNet 解释",
                "screening_status": "综合状态",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


def _sort_representatives(frame: pd.DataFrame, sort_by: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    sorted_frame = frame.copy()
    sorted_frame["_rules_score_numeric"] = pd.to_numeric(sorted_frame.get("rules_score", 0), errors="coerce").fillna(0)
    sorted_frame["_similar_group_size_numeric"] = pd.to_numeric(
        sorted_frame.get("similar_group_size", 1),
        errors="coerce",
    ).fillna(1)
    sorted_frame["_evidence_rank"] = sorted_frame["source_protein_evidence_level"].map(_evidence_rank).fillna(9)
    sorted_frame["_consensus_rank"] = sorted_frame.get("consensus_pass", False).astype(bool).astype(int)
    if sort_by == "证据较强优先":
        keys = ["_evidence_rank", "_rules_score_numeric", "candidate_id"]
        ascending = [True, False, True]
    elif sort_by == "规则分数高优先":
        keys = ["_rules_score_numeric", "_evidence_rank", "candidate_id"]
        ascending = [False, True, True]
    elif sort_by == "相似分组大优先":
        keys = ["_similar_group_size_numeric", "_rules_score_numeric", "candidate_id"]
        ascending = [False, False, True]
    else:
        keys = ["_consensus_rank", "_rules_score_numeric", "_evidence_rank", "candidate_id"]
        ascending = [False, False, True, True]
    return sorted_frame.sort_values(keys, ascending=ascending).drop(
        columns=["_rules_score_numeric", "_similar_group_size_numeric", "_evidence_rank", "_consensus_rank"],
        errors="ignore",
    )


def _evidence_rank(value: object) -> int:
    order = {
        "实验支持": 0,
        "人工/同源推断": 1,
        "自动/预测证据": 2,
        "无明确证据": 3,
        "": 4,
    }
    return order.get(str(value).strip(), 4)


def _route_badge(route: str) -> str:
    css_class = {
        "分泌/胞外倾向": "route-secreted",
        "膜/锚定倾向": "route-membrane",
        "分泌通路腔室倾向": "route-compartment",
        "胞内或非典型": "route-intracellular",
        "未知": "route-unknown",
    }.get(route, "route-unknown")
    return f"<span class='sig-badge {css_class}'>{escape(route or '未评估')}</span>"


def _evidence_badge(evidence: str) -> str:
    css_class = {
        "实验支持": "evidence-strong",
        "人工/同源推断": "evidence-curated",
        "自动/预测证据": "evidence-auto",
        "无明确证据": "evidence-none",
    }.get(evidence, "evidence-none")
    return f"<span class='sig-badge {css_class}'>{escape(evidence or '未评估')}</span>"


def _candidate_identity_html(row: pd.Series) -> str:
    protein = escape(str(row.get("protein_name", "")) or "未记录来源蛋白")
    accession = escape(str(row.get("accession", "")))
    status = escape(str(row.get("screening_status", "")))
    group_id = escape(str(row.get("similarity_group_id", "")))
    group_size = escape(str(row.get("similar_group_size", "")))
    return (
        "<div class='identity-block'>"
        f"<div class='source-protein'>{protein}</div>"
        f"<div class='muted-line'>UniProt {accession} · {status}</div>"
        f"<div class='muted-line'>相似分组 {group_id} · 同组 {group_size} 条</div>"
        "</div>"
    )


def _candidate_score_html(row: pd.Series) -> str:
    score = safe_float(row.get("rules_score", 0))
    uspnet = escape(str(row.get("uspnet_prediction_label", "")) or "未运行")
    cleavage = escape(str(row.get("uspnet_cleavage_sequence", "")) or "未给出切割片段")
    score_width = max(0, min(100, score))
    return (
        "<div class='score-block'>"
        "<div class='score-row'><span>规则分数</span><strong>"
        f"{score:.0f}</strong></div><div class='score-track'><div class='score-fill' style='width:{score_width:.0f}%;'></div></div>"
        f"<div class='muted-line'>{uspnet}</div>"
        f"<div class='muted-line'>切割片段：{cleavage}</div>"
        "</div>"
    )


def _candidate_score_detail_html(row: pd.Series) -> str:
    hydrophobicity = safe_float(row.get("rules_h_region_max_hydrophobicity", 0))
    n_positive = safe_int_from_float(row.get("rules_n_region_positive_count", 0))
    return (
        f"<div class='mini-grid'><div><span>N 区正电</span><strong>{n_positive}</strong></div>"
        f"<div><span>H 区疏水</span><strong>{hydrophobicity:.2f}</strong></div></div>"
    )


def _sequence_html(sequence: str) -> str:
    clean = escape(sequence)
    length = len(sequence)
    return (
        "<div class='sequence-row'>"
        f"<span class='sequence-label'>信号肽序列 · {length} aa</span>"
        f"<code>{clean}</code>"
        "</div>"
    )


def _render_similar_sequence_details(rows: pd.DataFrame, representatives: pd.DataFrame) -> None:
    rows = _ensure_display_columns(rows)
    representatives = _ensure_display_columns(representatives)
    grouped = representatives[representatives["similar_group_size"].astype(int) > 1].copy()
    if grouped.empty:
        st.info("当前代表序列没有折叠其他相似候选；每个代表序列都是独立分组。")
        return
    st.markdown("**查看相似序列**")
    for _, representative in grouped.sort_values(["similar_group_size", "candidate_id"], ascending=[False, True]).iterrows():
        representative_id = str(representative["candidate_id"])
        group_rows = rows[rows["representative_id"] == representative_id].copy()
        with st.expander(f"查看相似序列：{representative_id}（同组 {len(group_rows)} 条）", expanded=False):
            group_rows["similarity_percent"] = (group_rows["similarity_to_representative"].astype(float) * 100).round(1)
            st.dataframe(
                group_rows[
                    [
                        "candidate_id",
                        "is_representative",
                        "accession",
                        "protein_name",
                        "source_protein_route",
                        "source_protein_evidence_level",
                        "source_protein_route_basis",
                        "signal_peptide_sequence",
                        "similarity_percent",
                        "rules_priority",
                        "uspnet_prediction",
                        "uspnet_prediction_label",
                        "uspnet_cleavage_sequence",
                        "screening_status",
                    ]
                ].rename(
                    columns={
                        "candidate_id": "候选 ID",
                        "is_representative": "代表序列",
                        "accession": "UniProt accession",
                        "protein_name": "来源蛋白",
                        "source_protein_route": "来源蛋白分类",
                        "source_protein_evidence_level": "证据等级",
                        "source_protein_route_basis": "依据说明",
                        "signal_peptide_sequence": "信号肽序列",
                        "similarity_percent": "与代表序列相似度%",
                        "rules_priority": "规则优先级",
                        "uspnet_prediction": "USPNet 类型",
                        "uspnet_prediction_label": "USPNet 预测",
                        "uspnet_cleavage_sequence": "USPNet 切割片段",
                        "screening_status": "综合状态",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )


def _render_downloads(result: SignalPeptideScreeningResult) -> None:
    st.markdown("**下载文件**")
    cols = st.columns(3)
    _download_file_button(cols[0], result.uniprot_csv, "下载 UniProt 初始候选 CSV", "text/csv")
    _download_file_button(cols[1], result.comparison_csv, "下载完整方法对比 CSV", "text/csv")
    _download_file_button(cols[2], result.representatives_csv, "下载代表序列 CSV", "text/csv")
    cols2 = st.columns(3)
    _download_file_button(cols2[0], result.duplicate_csv, "下载重复记录 CSV", "text/csv")
    _download_file_button(cols2[1], result.representatives_fasta, "下载代表序列 FASTA", "text/plain")
    _download_file_button(cols2[2], result.recommended_fasta, "下载全部推荐候选 FASTA", "text/plain")


def _download_file_button(column, path: Path | None, label: str, mime: str) -> None:
    if path is not None and path.exists():
        column.download_button(label, path.read_bytes(), file_name=path.name, mime=mime)
    else:
        column.button(label, disabled=True)
