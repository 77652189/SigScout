from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sigscout.adapters.uspnet import USPNetAdapter  # noqa: E402
from sigscout.core.paths import ProjectPaths  # noqa: E402
from sigscout.services.library import SignalPeptideLibraryService  # noqa: E402
from sigscout.services.screening import SignalPeptideScreeningResult, SignalPeptideScreeningService  # noqa: E402


DEFAULT_TAXON_ID = 4922


st.set_page_config(
    page_title="SigScout",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

PATHS = ProjectPaths.discover(Path(__file__))


def main() -> None:
    _css()
    st.title("SigScout 信号肽筛选工作台")
    st.caption("蛋白层面的信号肽候选发现、N/H/C 三段结构质控、USPNet 复核、相似序列聚类和实验候选导出。")
    page = st.sidebar.radio(
        "功能导航",
        ["毕赤酵母信号肽筛选"],
    )
    st.sidebar.divider()
    st.sidebar.caption("候选来源：UniProt 中带 signal peptide 注释的毕赤酵母/Komagataella 蛋白。")
    st.sidebar.caption("SigScout 不做目标蛋白适配性预测，也不做密码子优化。")

    render_screening_and_exports()


def render_screening_and_exports() -> None:
    render_screening()
    st.divider()
    render_representatives()
    st.divider()
    render_help()


def render_screening() -> None:
    st.subheader("毕赤酵母信号肽筛选")
    st.write("这一步从 UniProt 刷新毕赤酵母/Komagataella 中带 signal peptide 注释的候选，并运行规则与 USPNet 信号肽筛选。来源蛋白分类评估在下方单独执行。")
    with st.form("screening_form"):
        taxon_id = st.number_input(
            "候选信号肽来源 taxon ID",
            min_value=1,
            value=DEFAULT_TAXON_ID,
            step=1,
            help="默认 4922 表示从 Komagataella/Pichia 中寻找带 signal peptide 注释的候选。",
        )
        max_records = st.number_input("最多拉取记录数", min_value=1, max_value=500, value=300, step=25)
        reviewed_only = st.checkbox("只看 reviewed 条目", value=False)
        submitted = st.form_submit_button("刷新并筛选毕赤酵母信号肽", type="primary")
    if submitted:
        with st.spinner("正在刷新毕赤酵母信号肽候选，并运行规则与 USPNet 筛选..."):
            result = _local_screening_service().screen_uniprot_candidates(
                taxon_id=int(taxon_id),
                max_records=int(max_records),
                reviewed_only=bool(reviewed_only),
                refresh_uniprot=True,
            )
        st.success(result.message if result.success else "筛选未完成")
    result = _load_result()
    if result is None:
        st.warning("没有可展示的筛选结果。请点击上方按钮刷新毕赤酵母信号肽。")
        return
    _render_summary(result)
    st.caption(f"当前展示目录：{result.output_dir}")
    if result.errors:
        with st.expander("运行提示 / 错误信息", expanded=False):
            st.write(result.errors)
    render_source_protein_annotation()


def render_source_protein_annotation() -> None:
    st.markdown("**来源蛋白辅助评估**")
    st.caption("该步骤基于 UniProt 受控定位词表、GO cellular component 和 feature 证据做辅助评估；不会重新拉取信号肽序列，也不会删除候选。")
    use_quickgo = st.checkbox(
        "同时查询 QuickGO/GOA cellular component 证据",
        value=True,
        help="QuickGO/GOA 可补充 GO ID、evidence code、reference 与 assignedBy；无网络时可取消勾选，仅使用已保存的 UniProt 证据。",
    )
    if st.button("评估来源蛋白定位", type="secondary"):
        with st.spinner("正在评估来源蛋白定位证据..."):
            annotation = _local_screening_service().annotate_persisted_source_proteins(use_quickgo=use_quickgo)
        if annotation.get("success"):
            st.success(str(annotation.get("message", "已完成来源蛋白辅助评估。")))
            if annotation.get("source_protein_quickgo_errors"):
                st.warning("QuickGO/GOA 查询有部分失败，已使用可用证据继续评估。")
        else:
            st.warning(str(annotation.get("message", "来源蛋白辅助评估未完成。")))


def render_representatives() -> None:
    st.subheader("代表序列与下载")
    result = _load_result()
    if result is None:
        st.warning("没有可展示的筛选结果。请先在上方刷新毕赤酵母信号肽。")
        return
    rows = _ensure_display_columns(pd.DataFrame(result.rows))
    if rows.empty:
        st.info("结果为空。")
        return
    recommended = rows[rows["recommended_for_draft_library"] == True].copy()
    representatives = recommended[recommended["is_representative"] == True].copy()
    if representatives.empty:
        st.info("当前没有代表序列。")
        return
    representatives = _ensure_display_columns(representatives)
    _render_representative_workbench(rows, representatives)
    _render_downloads(result)


def render_help() -> None:
    st.subheader("怎么读这些结果")
    st.markdown(
        """
        - **N 区正电**：许多经典分泌信号肽在 N 端带有 K/R/H 等正电残基，有助于形成正确拓扑。
        - **H 区疏水核心**：中间疏水段是信号肽识别和膜定位的关键特征，是首轮筛选最重要的指标之一。
        - **C 区切割位点**：信号肽酶切割位点附近常偏好小型中性残基，但这个规则比 N/H 区更需要人工复核。
        - **USPNet**：机器学习复核工具；它支持一条序列像信号肽，并不等于预测真实表达量。
        - **代表序列**：把高度相似的候选折叠成一条默认讨论对象；同组序列仍保留，可用于后续扩展。
        """
    )
    st.info("SigScout 输出的是实验讨论版候选，不是最终可下单合成序列。密码子优化、标签、酶切位点和载体设计应在下游确认。")


def _render_summary(result: SignalPeptideScreeningResult) -> None:
    summary = result.summary
    cols = st.columns(7)
    cols[0].metric("UniProt 初始命中", int(summary.get("uniprot_initial_hits", 0)))
    cols[1].metric("去重候选", int(summary.get("deduplicated_candidates", 0)))
    cols[2].metric("重复记录", int(summary.get("uniprot_duplicate_count", 0)))
    cols[3].metric("规则高优先", int(summary.get("rules_high_priority", 0)))
    cols[4].metric("USPNet 通过", int(summary.get("uspnet_passed", 0)))
    cols[5].metric("相似分组", int(summary.get("similarity_group_count", 0)))
    cols[6].metric("代表序列", int(summary.get("representative_candidate_count", 0)))
    query_at = str(summary.get("uniprot_query_at") or summary.get("query_at") or "").strip()
    if query_at:
        st.caption(f"UniProt 查询时间：{query_at}")
    else:
        st.caption("UniProt 查询时间：未记录；点击“刷新并筛选毕赤酵母信号肽”后会写入。")
    annotation_status = str(summary.get("source_protein_annotation_status", "")).strip()
    annotation_run_at = str(summary.get("source_protein_annotation_run_at", "")).strip()
    if annotation_status == "已评估" and annotation_run_at:
        st.caption(f"来源蛋白辅助评估时间：{annotation_run_at}")
        _render_source_annotation_interpretation(summary)
    else:
        st.caption("来源蛋白辅助评估：未评估；可点击“评估来源蛋白定位”单独执行。")
    with st.expander("规则分数和 USPNet 预测怎么读", expanded=True):
        st.markdown(
            """
            规则分数检查长度、N 区电荷、H 区疏水核心、C 区切割位点和低复杂度风险。
            UniProt 已注释信号肽通常分数会很高，这只说明它像标准信号肽，不代表目标蛋白产量更高。
            USPNet=SP 表示经典 Sec/SPI 信号肽，是本项目默认正向支持；LIPO、TAT、TATLIPO、PILIN 属于信号相关但非默认目标类型；NO_SP 表示需要降级或人工复核。
            """
        )


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
    browser_tab, distribution_tab, similar_tab, raw_tab = st.tabs(["候选浏览", "证据分布", "相似序列", "原始数据"])
    with browser_tab:
        filtered = _render_candidate_filters(representatives)
        if filtered.empty:
            st.info("没有符合当前筛选条件的代表序列。")
        else:
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
    with distribution_tab:
        _render_distribution_panel(rows, representatives)
    with similar_tab:
        _render_similar_sequence_details(rows, representatives)
    with raw_tab:
        _render_raw_representative_table(representatives)


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
        ["综合推荐优先", "证据较强优先", "规则分数高优先", "相似组大优先"],
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
            st.markdown(
                "<div class='evidence-panel'>"
                f"<div class='evidence-label'>依据说明</div><div>{escape(basis or summary or '未记录明确依据')}</div>"
                "</div>",
                unsafe_allow_html=True,
            )


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


def _sorted_unique(series: pd.Series) -> list[str]:
    values = [str(value).strip() for value in series.fillna("").tolist() if str(value).strip()]
    preferred = ["分泌/胞外倾向", "膜/锚定倾向", "分泌通路腔室倾向", "胞内或非典型", "未知", "未评估"]
    seen = set(values)
    ordered = [value for value in preferred if value in seen]
    ordered.extend(sorted(value for value in seen if value not in preferred))
    return ordered


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
    elif sort_by == "相似组大优先":
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
    score = _safe_float(row.get("rules_score", 0))
    hydrophobicity = _safe_float(row.get("rules_h_region_max_hydrophobicity", 0))
    n_positive = _safe_int(row.get("rules_n_region_positive_count", 0))
    uspnet = escape(str(row.get("uspnet_prediction_label", "")) or "未运行")
    cleavage = escape(str(row.get("uspnet_cleavage_sequence", "")) or "未给出切割片段")
    score_width = max(0, min(100, score))
    return (
        "<div class='score-block'>"
        "<div class='score-row'><span>规则分数</span><strong>"
        f"{score:.0f}</strong></div><div class='score-track'><div class='score-fill' style='width:{score_width:.0f}%;'></div></div>"
        f"<div class='mini-grid'><div><span>N 区正电</span><strong>{n_positive}</strong></div>"
        f"<div><span>H 区疏水</span><strong>{hydrophobicity:.2f}</strong></div></div>"
        f"<div class='muted-line'>{uspnet}</div>"
        f"<div class='muted-line'>切割片段：{cleavage}</div>"
        "</div>"
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


def _safe_float(value: object) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


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


def _render_source_annotation_interpretation(summary: dict[str, object]) -> None:
    route_counts = summary.get("source_protein_route_counts", {})
    evidence_counts = summary.get("source_protein_evidence_level_counts", {})
    if not isinstance(route_counts, dict):
        route_counts = {}
    if not isinstance(evidence_counts, dict):
        evidence_counts = {}
    unknown_count = int(route_counts.get("未知", 0) or 0)
    automatic_count = int(evidence_counts.get("自动/预测证据", 0) or 0)
    no_evidence_count = int(evidence_counts.get("无明确证据", 0) or 0)
    with st.expander("来源蛋白评估怎么读", expanded=False):
        st.markdown(
            f"""
            - **依据说明**：显示哪条 UniProt/GO 受控证据命中了哪个分类，例如 GO cellular component 属于 membrane 或 extracellular region。
            - **证据等级**：`实验支持` > `人工/同源推断` > `自动/预测证据` > `无明确证据`。`自动/预测证据` 不是说分类一定错，而是说证据主要来自 IEA、ARBA、RuleBase、TreeGrafter 等自动注释。
            - **未知较多**：当前有 `{unknown_count}` 条未命中分类映射，通常是 QuickGO/UniProt 没有 cellular component 证据、只有过于泛化的 GO 位置，或证据没有落到当前四类映射。
            - **低证据较多**：当前有 `{automatic_count}` 条为自动/预测证据，`{no_evidence_count}` 条无明确证据；这些更适合保留为候选但靠后人工复核。
            """
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


def _load_result() -> SignalPeptideScreeningResult | None:
    local = _local_screening_service().load_persisted_screening_result()
    if local is not None:
        return local
    return _example_screening_service().load_persisted_screening_result()


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


if __name__ == "__main__":
    main()
