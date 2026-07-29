from __future__ import annotations

import streamlit as st

from sigscout.services.screening import SignalPeptideScreeningResult
from sigscout.ui._shared import _load_result, _local_screening_service


DEFAULT_TAXON_ID = 4922


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
    st.caption("筛选流程：候选发现与去重 → 规则/USPNet 打分复核 → 相似聚类与代表序列")
    st.caption("候选发现与去重")
    discover_cols = st.columns(3)
    discover_cols[0].metric("UniProt 初始命中", int(summary.get("uniprot_initial_hits", 0)))
    discover_cols[1].metric("去重候选", int(summary.get("deduplicated_candidates", 0)))
    discover_cols[2].metric("重复记录", int(summary.get("uniprot_duplicate_count", 0)))
    st.caption("规则 / USPNet 打分复核")
    score_cols = st.columns(2)
    score_cols[0].metric("规则高优先", int(summary.get("rules_high_priority", 0)))
    score_cols[1].metric("USPNet 通过", int(summary.get("uspnet_passed", 0)))
    st.caption("相似聚类与代表序列")
    cluster_cols = st.columns(2)
    cluster_cols[0].metric("相似分组", int(summary.get("similarity_group_count", 0)))
    cluster_cols[1].metric("代表序列", int(summary.get("representative_candidate_count", 0)))
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
