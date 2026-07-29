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
from sigscout.core.coercion import safe_float, safe_int_from_float  # noqa: E402
from sigscout.core.paths import ProjectPaths  # noqa: E402
from sigscout.services.fusion_constructs import (  # noqa: E402
    DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
    FUSION_TARGET_PRESETS,
    build_fusion_constructs,
    fusion_constructs_to_csv,
    fusion_constructs_to_fasta,
    import_localization_results,
    score_construct,
    summarize_localization,
)
from sigscout.services.experimental_evidence import (  # noqa: E402
    annotate_candidate_experimental_evidence,
    annotate_construct_experimental_evidence,
    build_target_experimental_candidates,
)
from sigscout.services.experimental_feedback import (  # noqa: E402
    experimental_feedback_template,
    load_experimental_feedback,
    parse_experimental_feedback_csv,
    save_experimental_feedback,
    summarize_experimental_feedback,
)
from sigscout.services.library import SignalPeptideLibraryService  # noqa: E402
from sigscout.ui.experimental_browser import render_opn_experimental_browser  # noqa: E402
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
    st.caption("蛋白层面的信号肽候选发现、来源证据解释、代表序列整理和融合蛋白定位评估。")
    category = st.sidebar.radio(
        "功能导航",
        ["毕赤酵母信号肽筛选", "代表序列与下载", "融合定位", "实验反馈"],
    )
    if category == "毕赤酵母信号肽筛选":
        subpage = st.sidebar.radio(
            "子功能",
            ["刷新并筛选毕赤酵母信号肽", "评估来源蛋白定位"],
        )
    elif category == "代表序列与下载":
        subpage = st.sidebar.radio(
            "子功能",
            ["候选浏览", "证据分布", "相似序列", "原始数据"],
        )
    elif category == "融合定位":
        subpage = st.sidebar.radio(
            "子功能",
            ["生成定位评估文件", "导入 DeepLoc 结果"],
        )
    else:
        subpage = st.sidebar.radio("子功能", ["OPN 实验结果", "导入与模板"])
    st.sidebar.divider()
    st.sidebar.caption("候选来源：UniProt 中带 signal peptide 注释的毕赤酵母/Komagataella 蛋白。")
    st.sidebar.caption("SigScout 不做目标蛋白适配性预测，也不做密码子优化。")

    if category == "毕赤酵母信号肽筛选":
        render_screening(subpage)
    elif category == "代表序列与下载":
        render_representatives(subpage)
    elif category == "融合定位":
        render_fusion_localization(subpage)
    else:
        render_experimental_feedback(subpage)


def render_screening(subpage: str = "刷新并筛选毕赤酵母信号肽") -> None:
    st.subheader("毕赤酵母信号肽筛选")
    if subpage == "刷新并筛选毕赤酵母信号肽":
        st.write("从 UniProt 刷新毕赤酵母/Komagataella 中带 signal peptide 注释的候选，并运行规则与 USPNet 信号肽筛选。")
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
    else:
        render_source_protein_annotation()

    result = _load_result()
    if result is None:
        st.warning("没有可展示的筛选结果。请先刷新毕赤酵母信号肽。")
        return
    _render_summary(result)
    st.caption(f"当前展示目录：{result.output_dir}")
    if result.errors:
        with st.expander("运行提示 / 错误信息", expanded=False):
            st.write(result.errors)
    render_help()


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


def render_fusion_localization(subpage: str = "生成定位评估文件") -> None:
    st.subheader("融合定位")
    if subpage == "生成定位评估文件":
        loaded = _load_representative_frames()
        if loaded is None:
            return
        _, _, representatives = loaded
        _render_fusion_generation_panel(representatives)
    else:
        _render_localization_import_panel()

def render_experimental_feedback(subpage: str = "OPN 实验结果") -> None:
    st.subheader("实验反馈")
    st.info("当前实验反馈仅来自 OPN（骨桥蛋白）实验，不会自动外推到 hLF，也不会改写通用信号肽候选分数。")
    path = PATHS.local_runs_dir / "experimental_feedback" / "opn_measurements.csv"
    if subpage == "导入与模板":
        _render_experimental_feedback_import(path)
        return
    result = load_experimental_feedback(path, target_key="opn")
    if result.errors:
        for error in result.errors:
            st.error(error)
        return
    if result.rows.empty:
        st.warning("尚未导入 OPN 实验反馈。请进入“导入与模板”上传标准 CSV。")
        return
    _render_experimental_feedback_results(result.rows, result.warnings)


def _render_experimental_feedback_results(rows: pd.DataFrame, warnings: tuple[str, ...]) -> None:
    summary = summarize_experimental_feedback(rows)
    cols = st.columns(5)
    cols[0].metric("报告记录", int(summary["records"]))
    cols[1].metric("有效测量", int(summary["measurements"]))
    cols[2].metric("结果缺失", int(summary["missing_results"]))
    cols[3].metric("实验轮次", int(summary["batches"]))
    cols[4].metric("信号肽名称", int(summary["signal_peptides"]))
    for warning in warnings:
        st.warning(warning)

    batch_options = rows["batch_id"].drop_duplicates().tolist()
    selected_batch = st.selectbox("实验轮次", batch_options, key="experimental_feedback_batch")
    batch = rows.loc[rows["batch_id"] == selected_batch].copy()
    batch = batch.sort_values(["measurement_status", "batch_rank"], na_position="last")
    context = batch.iloc[0]
    st.caption(
        f"目标：{context['target_variant']} · 宿主：{context['strain_background']} · "
        f"整合位点：{context['integration_locus']}。排名仅在本轮条件内有效。"
    )

    measured = batch.loc[batch["measurement_status"] == "measured"].copy()
    if not measured.empty:
        chart = measured.set_index("source_construct_name")[["yield_ug_l"]].rename(
            columns={"yield_ug_l": "产量（μg/L）"}
        )
        st.bar_chart(chart, horizontal=True)

    display = batch[[
        "batch_rank",
        "source_construct_name",
        "measurement_status",
        "yield_ug_l",
        "batch_relative_to_best",
        "is_reference_baseline",
        "batch_fold_vs_reference",
        "reference_basis",
    ]].copy()
    display["measurement_status"] = display["measurement_status"].map({
        "measured": "已测得",
        "result_missing": "报告未给产量",
    })
    display = display.rename(columns={
        "batch_rank": "批内排名",
        "source_construct_name": "报告原始构建名",
        "measurement_status": "结果状态",
        "yield_ug_l": "产量（μg/L）",
        "batch_relative_to_best": "相对本轮最佳",
        "is_reference_baseline": "推定参考基线",
        "batch_fold_vs_reference": "相对参考基线倍数",
        "reference_basis": "参考依据",
    })
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "相对本轮最佳": st.column_config.ProgressColumn(
                min_value=0.0, max_value=1.0, format="percent"
            ),
            "相对参考基线倍数": st.column_config.NumberColumn(format="%.2f×"),
            "产量（μg/L）": st.column_config.NumberColumn(format="%.0f"),
            "推定参考基线": st.column_config.CheckboxColumn(),
        },
    )
    st.caption("“推定参考基线”用于轮内倍率验算，并非实验报告明确标注的正式对照。")
    _render_experimental_sequence_details(batch)
    with st.expander("查看完整结构化原始数据"):
        st.dataframe(batch, hide_index=True, use_container_width=True)


def _render_experimental_sequence_details(batch: pd.DataFrame) -> None:
    with st.expander("查看报告原始名称与完整序列", expanded=False):
        choices = batch["experiment_id"].tolist()
        labels = batch.set_index("experiment_id")["source_construct_name"].to_dict()
        selected_id = st.selectbox(
            "构建记录",
            choices,
            format_func=lambda value: labels.get(value, value),
            key=f"experimental_sequence_{batch['batch_id'].iloc[0]}",
        )
        row = batch.loc[batch["experiment_id"] == selected_id].iloc[0]
        st.text_input("报告原始构建名", value=str(row["source_construct_name"]), disabled=True)
        st.text_input("内部规范化 ID", value=str(row["construct_name"]), disabled=True)
        st.text_area(
            "信号肽氨基酸序列",
            value=str(row["signal_peptide_sequence"]),
            height=100,
            key=f"experimental_sp_aa_{selected_id}",
        )
        st.text_area(
            "信号肽核苷酸序列",
            value=str(row["signal_peptide_nucleotide_sequence"]),
            height=120,
            key=f"experimental_sp_nt_{selected_id}",
        )
        st.text_area(
            "OPN 氨基酸序列",
            value=str(row["target_protein_sequence"]),
            height=150,
            key=f"experimental_target_aa_{selected_id}",
        )
        st.text_area(
            f"{row['target_variant']} 核苷酸序列",
            value=str(row["target_nucleotide_sequence"]),
            height=180,
            key=f"experimental_target_nt_{selected_id}",
        )

def _render_experimental_feedback_import(path: Path) -> None:
    st.markdown("**导入 OPN 实验反馈**")
    st.caption(f"数据保存在本地忽略目录：{path}。上传会替换当前 OPN 实验反馈文件，不会修改候选库。")
    st.download_button(
        "下载实验反馈 CSV 模板",
        experimental_feedback_template().encode("utf-8-sig"),
        file_name="experimental_feedback_template.csv",
        mime="text/csv",
    )
    uploaded = st.file_uploader("上传填写后的 CSV", type=["csv"], key="experimental_feedback_upload")
    if uploaded is None:
        return
    result = parse_experimental_feedback_csv(uploaded.getvalue(), target_key="opn")
    if result.errors:
        for error in result.errors:
            st.error(error)
        return
    st.dataframe(result.rows, hide_index=True, use_container_width=True)
    if st.button("保存为当前 OPN 实验反馈", type="primary", key="save_experimental_feedback"):
        save_experimental_feedback(result.rows, path)
        st.success(f"已保存 {len(result.rows)} 条 OPN 实验记录（含结果缺失记录）。")


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
    score = safe_float(row.get("rules_score", 0))
    hydrophobicity = safe_float(row.get("rules_h_region_max_hydrophobicity", 0))
    n_positive = safe_int_from_float(row.get("rules_n_region_positive_count", 0))
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


def _select_fusion_target() -> tuple[str, object]:
    options = list(FUSION_TARGET_PRESETS.keys())
    current = str(st.session_state.get("fusion_target_key", "opn"))
    index = options.index(current) if current in options else 0
    selected = st.selectbox(
        "C 目标蛋白",
        options,
        index=index,
        format_func=lambda key: FUSION_TARGET_PRESETS[key].label,
        key="fusion_target_key",
        help="切换目标后会自动替换 C 固定序列，并清空当前会话中的旧 AC/ABC 构建，避免跨目标混用。",
    )
    preset = FUSION_TARGET_PRESETS[selected]
    applied = st.session_state.get("fusion_target_applied_key")
    if applied != selected:
        st.session_state["fusion_c_sequence"] = preset.sequence
        st.session_state["fusion_target_applied_key"] = selected
        if applied is not None:
            _clear_fusion_session_rows()
    st.caption(f"{preset.note} 来源：{preset.source}；C 长度 {len(preset.sequence)} aa。")
    return selected, preset


def _clear_fusion_session_rows() -> None:
    for key in list(st.session_state.keys()):
        if key in {"fusion_construct_rows", "fusion_construct_errors", "fusion_localization_rows"} or key.startswith("fusion_localization_rows_"):
            st.session_state.pop(key, None)

def _opn_feedback_rows() -> pd.DataFrame:
    result = load_experimental_feedback(
        PATHS.local_runs_dir / "experimental_feedback" / "opn_measurements.csv",
        target_key="opn",
    )
    return result.rows if result.valid else pd.DataFrame()


def _render_fusion_generation_panel(representatives: pd.DataFrame) -> None:
    st.markdown("**AC / ABC 融合蛋白定位评估文件**")
    st.caption("SigScout 只生成 FASTA 和导入外部结果；DeepLoc/BUSCA 请手动上传运行，避免把第三方网页服务当作 API 自动调用。")
    _render_deeploc_manual_workflow()
    target_key, target_preset = _select_fusion_target()
    candidate_rows = representatives.copy()
    selected_ids = set(st.session_state.get(f"fusion_selected_candidate_ids_{target_key}", []))
    source_options = ["使用全部代表候选"]
    if target_key == "opn":
        source_options.insert(0, "使用候选浏览已选项")
        feedback = _opn_feedback_rows()
        experimental = build_target_experimental_candidates(feedback, "opn")
        if not experimental.empty:
            known = set(candidate_rows["signal_peptide_sequence"].astype(str).str.upper())
            experimental = experimental[
                ~experimental["signal_peptide_sequence"].astype(str).str.upper().isin(known)
            ]
            candidate_rows = pd.concat([candidate_rows, experimental], ignore_index=True, sort=False)
    source_mode = st.radio(
        "候选来源",
        source_options,
        index=0 if selected_ids and target_key == "opn" else len(source_options) - 1,
        horizontal=True,
        key=f"fusion_candidate_source_{target_key}",
    )
    if source_mode == "使用候选浏览已选项":
        candidate_rows = candidate_rows[
            candidate_rows["candidate_id"].astype(str).isin(selected_ids)
        ]
        st.caption(f"当前使用 {len(candidate_rows)} 个 OPN 已选候选。")
        if candidate_rows.empty:
            st.warning("当前没有可用的 OPN 已选候选，请先在候选浏览中加入融合评估。")
    input_cols = st.columns(2)
    b_sequence = input_cols[0].text_area(
        "B 固定序列（例如 α-factor pro 区）",
        value=DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
        height=150,
        placeholder="粘贴氨基酸序列；支持带空格或换行",
        key="fusion_b_sequence",
        help="当前默认值为去除明显 pre-region 的 α-factor pro 区候选片段，末端保留 LEKR/Kex2 加工位点。",
    )
    c_sequence = input_cols[1].text_area(
        "C 固定序列（目标蛋白）",
        value=target_preset.sequence,
        height=150,
        placeholder="粘贴目标蛋白氨基酸序列；支持带空格或换行",
        key="fusion_c_sequence",
        help="可用目标下拉自动填入，也可以临时手动编辑；切换目标会恢复该目标的默认 C 序列。",
    )
    option_cols = st.columns([1.2, 1.2])
    construct_types = option_cols[0].multiselect(
        "构建类型",
        ["AC", "ABC"],
        default=["AC", "ABC"],
        key="fusion_construct_types",
    )
    include_controls = option_cols[1].checkbox("加入对照构建", value=True, key="fusion_include_controls")
    positive_control = st.text_area(
        "阳性对照 leader（可选，例如完整 α-factor prepro）",
        height=90,
        placeholder="留空则只生成 C_ONLY 和 BC 对照；粘贴序列后会额外生成 POSITIVE_CONTROL_C。",
        key="fusion_positive_control",
    )
    build_clicked = st.button("生成 AC/ABC 定位评估文件", type="secondary")

    if build_clicked or st.session_state.get("fusion_construct_rows"):
        if build_clicked:
            result = build_fusion_constructs(
                candidate_rows.to_dict(orient="records"),
                b_sequence=b_sequence,
                c_sequence=c_sequence,
                target_key=target_key,
                target_label=target_preset.label,
                include_ac="AC" in construct_types,
                include_abc="ABC" in construct_types,
                include_controls=include_controls,
                positive_control_leader_sequence=positive_control,
            )
            st.session_state["fusion_construct_rows"] = result.rows
            st.session_state["fusion_construct_errors"] = result.errors
            st.session_state["fusion_localization_rows"] = result.rows
            st.session_state[f"fusion_localization_rows_{target_key}_deeploc"] = result.rows
            st.session_state[f"fusion_localization_rows_{target_key}_busca"] = result.rows
        errors = list(st.session_state.get("fusion_construct_errors", []))
        construct_rows = list(st.session_state.get("fusion_construct_rows", []))
        if errors:
            for error in errors:
                st.warning(error)
        if construct_rows:
            st.success(f"已生成 {len(construct_rows)} 条融合构建。")
            _render_fusion_downloads(construct_rows)


def _render_localization_import_panel() -> None:
    st.markdown("**导入 DeepLoc / BUSCA 结果**")
    _select_fusion_target()
    _render_deeploc_manual_workflow()
    construct_rows = list(st.session_state.get("fusion_construct_rows", []))
    if not construct_rows:
        st.info("当前会话还没有生成 AC/ABC 构建；如果已有缓存，会先直接展示缓存内容。重新上传外部结果前仍需先生成构建用于匹配。")
    else:
        st.caption(f"当前可匹配 {len(construct_rows)} 条融合构建。")
    _render_localization_import(construct_rows)


def _render_fusion_downloads(construct_rows: list[dict[str, object]]) -> None:
    fasta = fusion_constructs_to_fasta(construct_rows)
    csv_text = fusion_constructs_to_csv(construct_rows)
    cols = st.columns(3)
    cols[0].download_button(
        "下载 AC/ABC FASTA",
        fasta.encode("utf-8"),
        file_name="fusion_constructs_ac_abc.fasta",
        mime="text/plain",
    )
    cols[1].download_button(
        "下载构建索引 CSV",
        csv_text.encode("utf-8-sig"),
        file_name="fusion_constructs_ac_abc.csv",
        mime="text/csv",
    )
    cols[2].metric("构建数量", len(construct_rows))

    preview = pd.DataFrame(construct_rows)
    preview_columns = [
        "construct_id",
        "construct_type",
        "candidate_id",
        "construct_length",
        "a_length",
        "b_length",
        "c_length",
        "has_er_retention_motif",
        "b_ends_with_kex2_site",
        "b_pre_region_like",
        "internal_hydrophobic_run_max",
        "signal_peptide_quality",
        "processing_quality",
        "construct_design_risk",
        "overall_score",
        "overall_priority",
        "processing_site_note",
    ]
    st.dataframe(
        preview[[column for column in preview_columns if column in preview.columns]].rename(
            columns={
                "construct_id": "构建 ID",
                "construct_type": "构建类型",
                "candidate_id": "信号肽候选",
                "construct_length": "融合蛋白长度",
                "a_length": "A 长度",
                "b_length": "B 长度",
                "c_length": "C 长度",
                "has_er_retention_motif": "ER 保留 motif 风险",
                "b_ends_with_kex2_site": "B 末端 Kex2 位点",
                "b_pre_region_like": "B 疑似含 pre-region",
                "internal_hydrophobic_run_max": "最长内部疏水连续段",
                "signal_peptide_quality": "信号肽质量",
                "processing_quality": "加工质量",
                "construct_design_risk": "设计风险",
                "overall_score": "综合分",
                "overall_priority": "优先级",
                "processing_site_note": "加工位点说明",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )



def _render_deeploc_manual_workflow() -> None:
    with st.expander("DeepLoc 手动上传流程", expanded=False):
        st.markdown(
            """
            1. 在本页生成 AC/ABC 构建后，点击 **下载 AC/ABC FASTA**。
            2. 打开 [DeepLoc 2.1](https://services.healthtech.dtu.dk/services/DeepLoc-2.1/)，上传刚下载的 FASTA 文件并运行预测。
            3. 从 DeepLoc 下载结果表，优先使用 CSV/TSV 格式。
            4. 回到左侧 **融合定位 → 导入 DeepLoc 结果**，选择 `DeepLoc`，上传结果表。
            5. SigScout 会按 `construct_id` 合并结果、写入本地缓存，并刷新排序表和可复制序列区。
            """
        )
        st.caption("注意：切换 OPN / hLF 目标后，需要重新生成对应目标的 FASTA；DeepLoc 缓存也会按目标蛋白分开保存。")


def _render_localization_import(construct_rows: list[dict[str, object]]) -> None:
    st.markdown("**导入 DeepLoc / BUSCA 结果**")
    tool_name = st.selectbox("结果来源", ["deeploc", "busca"], format_func=lambda value: value.upper())
    target_key = _current_fusion_target_key()
    session_rows_key = f"fusion_localization_rows_{target_key}_{tool_name}"
    cache_path = _localization_cache_path(tool_name, target_key)
    cached_rows, cached_count = _load_localization_cache(tool_name, construct_rows, target_key)
    cache_cols = st.columns([2.2, 1.0])
    if cached_count:
        if construct_rows:
            cache_cols[0].success(f"已自动加载 {cached_count} 条 {tool_name.upper()} 缓存结果：{cache_path}")
        else:
            cache_cols[0].success(f"已直接展示 {cached_count} 条 {tool_name.upper()} 缓存结果：{cache_path}")
        st.session_state[session_rows_key] = cached_rows
    elif cache_path.exists() and construct_rows:
        cache_cols[0].warning("检测到缓存文件，但当前构建序列已变化，未自动套用旧结果。")
    elif cache_path.exists():
        cache_cols[0].warning("检测到缓存文件，但无法读取有效 construct_id。")
    else:
        cache_cols[0].caption("当前没有可用的本地定位结果缓存。")
    if cache_cols[1].button("清除当前缓存", disabled=not cache_path.exists(), key=f"{target_key}_{tool_name}_clear_localization_cache"):
        cache_path.unlink(missing_ok=True)
        st.session_state[session_rows_key] = construct_rows
        st.success(f"已清除 {tool_name.upper()} 缓存。")

    if construct_rows:
        uploaded = st.file_uploader(
            "上传 CSV/TSV 结果表",
            type=["csv", "tsv", "txt"],
            key=f"{tool_name}_localization_upload",
        )
        if uploaded is not None:
            imported = import_localization_results(construct_rows, uploaded.getvalue(), tool_name=tool_name)
            if imported.errors:
                for error in imported.errors:
                    st.warning(error)
            if imported.imported_count:
                st.session_state[session_rows_key] = imported.rows
                _save_localization_cache(tool_name, imported.rows, target_key)
                st.success(f"已匹配 {imported.imported_count} 条 {tool_name.upper()} 结果。")
    else:
        st.caption("上传新的 DeepLoc/BUSCA 结果需要先生成当前 AC/ABC 构建，以便按 construct_id 匹配。")
    localization_rows = list(st.session_state.get(session_rows_key, construct_rows))
    if not localization_rows:
        return
    feedback = _opn_feedback_rows() if target_key == "opn" else pd.DataFrame()
    annotated_rows = annotate_construct_experimental_evidence(
        localization_rows, feedback, target_key
    ).to_dict(orient="records")
    enriched = []
    for row in annotated_rows:
        updated = {**row, **summarize_localization(row)}
        updated.update(score_construct(updated))
        enriched.append(updated)
    frame = pd.DataFrame(enriched)
    frame = _sort_localization_results(frame)
    _render_localization_summary(frame)
    _render_experimental_match_tabs(frame, target_key)
    columns = [
        "construct_id",
        "construct_type",
        "candidate_id",
        "deeploc_localization",
        "busca_localization",
        "external_secreted_signal",
        "external_er_golgi_signal",
        "external_membrane_risk",
        "external_vacuole_risk",
        "external_extracellular_probability",
        "external_soluble_probability",
        "external_membrane_probability",
        "external_vacuole_probability",
        "signal_peptide_quality",
        "signal_peptide_detail_score",
        "processing_quality",
        "external_localization_support",
        "localization_probability_score",
        "source_context_score",
        "membrane_or_vacuole_risk",
        "fine_priority_score",
        "overall_score",
        "overall_priority",
        "construct_length",
        "processing_site_note",
    ]
    st.markdown("**定位评估排序表**")
    st.dataframe(
        frame[[column for column in columns if column in frame.columns]].rename(
            columns={
                "construct_id": "构建 ID",
                "construct_type": "构建类型",
                "candidate_id": "信号肽候选",
                "deeploc_localization": "DeepLoc 定位",
                "busca_localization": "BUSCA 定位",
                "external_secreted_signal": "胞外倾向",
                "external_er_golgi_signal": "ER/Golgi 倾向",
                "external_membrane_risk": "膜定位风险",
                "external_vacuole_risk": "液泡/溶酶体风险",
                "external_extracellular_probability": "胞外概率",
                "external_soluble_probability": "可溶概率",
                "external_membrane_probability": "膜风险概率",
                "external_vacuole_probability": "液泡概率",
                "signal_peptide_quality": "信号肽质量",
                "signal_peptide_detail_score": "A细节分",
                "processing_quality": "加工质量",
                "external_localization_support": "外部定位支持",
                "localization_probability_score": "定位概率分",
                "source_context_score": "来源证据分",
                "membrane_or_vacuole_risk": "膜/液泡风险",
                "fine_priority_score": "细化优先分",
                "overall_score": "综合分",
                "overall_priority": "优先级",
                "construct_length": "长度",
                "processing_site_note": "加工位点说明",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    _render_fusion_sequence_copy_panel(frame)
    st.download_button(
        "下载合并定位结果 CSV",
        fusion_constructs_to_csv(frame.to_dict(orient="records")).encode("utf-8-sig"),
        file_name="fusion_constructs_with_localization.csv",
        mime="text/csv",
    )


def _render_experimental_match_tabs(frame: pd.DataFrame, target_key: str) -> None:
    ranking_tab, evidence_tab = st.tabs(["定位排序", "OPN 实验匹配"])
    with ranking_tab:
        st.caption("定位排序仅使用 DeepLoc/BUSCA、加工位点和风险扫描；实验反馈不参与总分。")
        st.dataframe(
            frame[[column for column in (
                "construct_id", "construct_type", "candidate_id", "fine_priority_score",
                "overall_score", "overall_priority",
            ) if column in frame.columns]],
            hide_index=True,
            use_container_width=True,
        )
    with evidence_tab:
        if target_key != "opn":
            st.info("暂无 hLF 实验反馈。")
            return
        exact = frame[frame["experimental_match_type"].astype(str).eq("exact_construct")].copy()
        related = frame[frame["experimental_match_type"].astype(str).eq("a_sequence_only")].copy()
        missing = frame[frame["experimental_match_type"].astype(str).eq("result_missing")].copy()
        evidence_columns = [
            "construct_id", "construct_type", "candidate_id", "experimental_match_type",
            "experimental_status", "experimental_unit_type", "experimental_relative_median",
            "experimental_relative_min", "experimental_relative_max", "experimental_record_count",
            "experimental_batch_count", "experimental_nucleotide_variant_count", "experimental_note",
        ]
        if not exact.empty:
            st.markdown("**完整 AC 构建精确匹配**")
            exact["_relative"] = pd.to_numeric(exact["experimental_relative_median"], errors="coerce")
            exact = exact.sort_values("_relative", ascending=False).drop(columns="_relative")
            st.dataframe(exact[[c for c in evidence_columns if c in exact]], hide_index=True, use_container_width=True)
        if not related.empty:
            st.markdown("**仅 A/leader 相关**")
            st.warning("以下构建只匹配 A/leader，不代表当前 AC/ABC 完整构建已被实验验证。")
            st.dataframe(related[[c for c in evidence_columns if c in related]], hide_index=True, use_container_width=True)
        if not missing.empty:
            st.markdown("**报告提及但结果缺失**")
            st.dataframe(missing[[c for c in evidence_columns if c in missing]], hide_index=True, use_container_width=True)
        if exact.empty and related.empty and missing.empty:
            st.info("当前构建没有 OPN 精确序列实验关联；新增候选可能需要重新生成 FASTA 并运行定位评估。")


def _render_localization_summary(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    candidate_frame = frame[~frame["construct_type"].astype(str).isin(["C_ONLY", "BC", "POSITIVE_CONTROL_C"])].copy()
    summary_frame = candidate_frame if not candidate_frame.empty else frame
    best = summary_frame.iloc[0]
    cols = st.columns(5)
    cols[0].metric("可排序构建", len(candidate_frame))
    cols[1].metric("最高细化优先分", _format_number(best.get("fine_priority_score")))
    cols[2].metric("最高综合分", _format_number(best.get("overall_score")))
    cols[3].metric("最佳胞外概率", _format_number(best.get("external_extracellular_probability")))
    cols[4].metric("最佳构建", str(best.get("construct_id", ""))[:28])


def _render_fusion_sequence_copy_panel(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    st.markdown("**融合序列复制区**")
    st.caption("按当前排序展示靠前构建；序列文本框可直接全选复制。")
    candidate_frame = frame[~frame["construct_type"].astype(str).isin(["C_ONLY", "BC", "POSITIVE_CONTROL_C"])].copy()
    if candidate_frame.empty:
        candidate_frame = frame.copy()

    control_cols = st.columns([1.0, 1.0, 2.2])
    type_options = ["全部", *_sorted_unique(candidate_frame["construct_type"])]
    selected_type = control_cols[0].selectbox("构建类型", type_options, key="fusion_copy_type_filter")
    page_size = control_cols[1].number_input(
        "每页数量",
        min_value=1,
        max_value=min(50, len(candidate_frame)),
        value=min(10, len(candidate_frame)),
        step=1,
        key="fusion_copy_page_size",
    )
    search = control_cols[2].text_input(
        "搜索构建",
        placeholder="construct_id / candidate_id",
        key="fusion_copy_search",
    )

    filtered = candidate_frame.copy()
    if selected_type != "全部":
        filtered = filtered[filtered["construct_type"].astype(str) == selected_type]
    if search.strip():
        pattern = search.strip()
        searchable = filtered[["construct_id", "candidate_id"]].astype(str).agg(" ".join, axis=1)
        filtered = filtered[searchable.str.contains(pattern, case=False, regex=False, na=False)]
    if filtered.empty:
        st.info("没有符合当前条件的融合构建。")
        return

    _, _, start, end = _render_pagination_controls(
        total_items=len(filtered),
        page_size=int(page_size),
        page_key="fusion_copy_page",
        key_prefix="fusion_copy_top",
    )
    st.caption(f"第 {start}-{end} 条，共 {len(filtered)} 条融合构建")
    for _, row in filtered.iloc[start - 1 : end].iterrows():
        _render_fusion_sequence_card(row)
    _render_pagination_controls(
        total_items=len(filtered),
        page_size=int(page_size),
        page_key="fusion_copy_page",
        key_prefix="fusion_copy_bottom",
    )


def _render_fusion_sequence_card(row: pd.Series) -> None:
    construct_id = str(row.get("construct_id", "")).strip()
    construct_type = str(row.get("construct_type", "")).strip()
    sequence = _construct_sequence_from_row(row)
    with st.container(border=True):
        header_cols = st.columns([2.4, 0.7, 0.7, 0.7, 0.7])
        header_cols[0].markdown(
            f"<div class='fusion-title'>{escape(construct_id)}</div>"
            f"<div class='muted-line'>{escape(str(row.get('candidate_id', '')))} · {escape(construct_type)} · {len(sequence)} aa</div>",
            unsafe_allow_html=True,
        )
        header_cols[1].metric("细化优先", _format_number(row.get("fine_priority_score")))
        header_cols[2].metric("胞外概率", _format_number(row.get("external_extracellular_probability")))
        header_cols[3].metric("可溶概率", _format_number(row.get("external_soluble_probability")))
        header_cols[4].metric("膜风险", _format_number(row.get("external_membrane_probability")))

        score_html = _fusion_score_strip(row)
        st.markdown(score_html, unsafe_allow_html=True)

        st.text_area(
            "融合蛋白序列",
            value=sequence,
            height=110,
            key=f"fusion_sequence_{construct_id}",
            label_visibility="collapsed",
        )
        st.caption(str(row.get("processing_site_note", "")).strip())
        match_type = str(row.get("experimental_match_type", "none"))
        if match_type != "none":
            st.info(
                f"OPN 实验匹配：{match_type}；批内相对最佳 "
                f"{_format_number(row.get('experimental_relative_median'))}；"
                f"{row.get('experimental_batch_count', 0)} 轮 / "
                f"{row.get('experimental_record_count', 0)} 条记录。"
            )
            st.caption(str(row.get("experimental_note", "")))


def _construct_sequence_from_row(row: pd.Series | dict[str, object]) -> str:
    sequence = str(row.get("construct_sequence", "")).strip()
    if sequence:
        return sequence
    return (
        str(row.get("a_signal_peptide", "")).strip()
        + str(row.get("b_fixed_sequence", "")).strip()
        + str(row.get("c_target_sequence", "")).strip()
    )


def _fusion_score_strip(row: pd.Series) -> str:
    items = [
        ("定位概率分", row.get("localization_probability_score")),
        ("A细节分", row.get("signal_peptide_detail_score")),
        ("加工质量", row.get("processing_quality")),
        ("来源证据", row.get("source_context_score")),
        ("膜/液泡风险", row.get("membrane_or_vacuole_risk")),
    ]
    cells = []
    for label, value in items:
        cells.append(
            "<div class='fusion-mini-cell'>"
            f"<span>{escape(label)}</span><strong>{escape(_format_number(value))}</strong>"
            "</div>"
        )
    return "<div class='fusion-mini-grid'>" + "".join(cells) + "</div>"


def _format_number(value: object) -> str:
    number = safe_float(value)
    if abs(number - round(number)) < 0.05:
        return str(int(round(number)))
    return f"{number:.3f}" if abs(number) < 1 else f"{number:.1f}"



def _current_fusion_target_key() -> str:
    target_key = str(st.session_state.get("fusion_target_key", "opn")).strip().lower()
    return target_key if target_key in FUSION_TARGET_PRESETS else "opn"


def _localization_cache_path(tool_name: str, target_key: str | None = None) -> Path:
    safe_tool = "".join(ch for ch in tool_name.lower() if ch.isalnum() or ch in {"_", "-"}).strip("_-")
    safe_target = "".join(ch for ch in (target_key or _current_fusion_target_key()).lower() if ch.isalnum() or ch in {"_", "-"}).strip("_-")
    if safe_target == "opn":
        return PATHS.opn_screening_output_dir / f"fusion_localization_{safe_tool or 'external'}.csv"
    return PATHS.opn_screening_output_dir / f"fusion_localization_{safe_target or 'target'}_{safe_tool or 'external'}.csv"


def _save_localization_cache(tool_name: str, rows: list[dict[str, object]], target_key: str | None = None) -> None:
    path = _localization_cache_path(tool_name, target_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fusion_constructs_to_csv(rows), encoding="utf-8")


def _load_localization_cache(
    tool_name: str,
    construct_rows: list[dict[str, object]],
    target_key: str | None = None,
) -> tuple[list[dict[str, object]], int]:
    path = _localization_cache_path(tool_name, target_key)
    if not path.exists():
        return construct_rows, 0
    try:
        cached_frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return construct_rows, 0
    if "construct_id" not in cached_frame.columns:
        return construct_rows, 0

    cached_rows = [
        row
        for row in cached_frame.to_dict(orient="records")
        if str(row.get("construct_id", "")).strip()
    ]
    if not construct_rows:
        return cached_rows, len(cached_rows)

    cached_by_id = {
        str(row.get("construct_id", "")).strip(): row
        for row in cached_rows
    }
    merged_rows: list[dict[str, object]] = []
    matched = 0
    for row in construct_rows:
        construct_id = str(row.get("construct_id", "")).strip()
        cached = cached_by_id.get(construct_id)
        if cached and _cached_construct_matches(row, cached):
            merged = dict(row)
            merged.update(cached)
            merged_rows.append(merged)
            matched += 1
        else:
            merged_rows.append(dict(row))
    if not matched:
        return construct_rows, 0
    return merged_rows, matched


def _cached_construct_matches(current: dict[str, object], cached: dict[str, object]) -> bool:
    cached_sequence = str(cached.get("construct_sequence", "")).strip()
    current_sequence = str(current.get("construct_sequence", "")).strip()
    if cached_sequence and current_sequence:
        return cached_sequence == current_sequence
    cached_length = str(cached.get("construct_length", "")).strip()
    current_length = str(current.get("construct_length", "")).strip()
    return bool(cached_length and current_length and cached_length == current_length)


def _sort_localization_results(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    sorted_frame = frame.copy()
    priority_rank = {"高": 0, "中": 1, "低": 2, "待外部定位": 3}
    sorted_frame["_priority_rank"] = sorted_frame.get("overall_priority", "").map(priority_rank).fillna(9)
    sorted_frame["_fine_priority_numeric"] = pd.to_numeric(sorted_frame.get("fine_priority_score", 0), errors="coerce").fillna(0)
    sorted_frame["_overall_score_numeric"] = pd.to_numeric(sorted_frame.get("overall_score", 0), errors="coerce").fillna(0)
    sorted_frame["_risk_numeric"] = pd.to_numeric(sorted_frame.get("membrane_or_vacuole_risk", 0), errors="coerce").fillna(0)
    sorted_frame["_external_support_numeric"] = pd.to_numeric(
        sorted_frame.get("external_localization_support", 0),
        errors="coerce",
    ).fillna(0)
    sorted_frame["_construct_type_rank"] = sorted_frame.get("construct_type", "").map({"ABC": 0, "AC": 1}).fillna(2)
    return sorted_frame.sort_values(
        [
            "_priority_rank",
            "_fine_priority_numeric",
            "_overall_score_numeric",
            "_risk_numeric",
            "_external_support_numeric",
            "_construct_type_rank",
            "construct_id",
        ],
        ascending=[True, False, False, True, False, True, True],
    ).drop(
        columns=[
            "_priority_rank",
            "_fine_priority_numeric",
            "_overall_score_numeric",
            "_risk_numeric",
            "_external_support_numeric",
            "_construct_type_rank",
        ],
        errors="ignore",
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


if __name__ == "__main__":
    main()
