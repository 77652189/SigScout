from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sigscout.adapters.uspnet import USPNetAdapter  # noqa: E402
from sigscout.core.paths import ProjectPaths  # noqa: E402
from sigscout.presets.opn import DEFAULT_TAXON_ID, MATURE_OPN, OPN_SHORTLIST, opn_library_service  # noqa: E402
from sigscout.services.screening import SignalPeptideScreeningResult, SignalPeptideScreeningService  # noqa: E402


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
        ["项目总览", "候选库", "外部发现与筛选", "代表序列与下载", "帮助说明"],
    )
    st.sidebar.divider()
    st.sidebar.caption("默认演示项目：人骨桥蛋白 OPN 在毕赤酵母中的分泌构建。")
    st.sidebar.caption("SigScout 不需要 MATLAB，不做 pcSec 模型比较，也不做密码子优化。")

    if page == "项目总览":
        render_overview()
    elif page == "候选库":
        render_library()
    elif page == "外部发现与筛选":
        render_screening()
    elif page == "代表序列与下载":
        render_representatives()
    else:
        render_help()


def render_overview() -> None:
    st.subheader("这个工具能做什么")
    st.markdown(
        """
        SigScout 用来把“可能适合分泌目标蛋白的信号肽”整理成可讨论的实验候选。
        它从 UniProt、文献或手动导入候选开始，检查信号肽典型三段结构，再用 USPNet 做可选机器学习复核。
        最后把高度相似的序列折叠成代表序列，方便首轮湿实验讨论。
        """
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("默认目标", "OPN")
    m2.metric("成熟 OPN 长度", f"{len(MATURE_OPN)} aa")
    m3.metric("默认 UniProt taxon", str(DEFAULT_TAXON_ID))
    m4.metric("首轮预设候选", str(len(opn_library_service().list_candidates())))

    st.markdown("**推荐的首轮逻辑**")
    st.write("先看代表序列和 N/H/C 质控，再选少量构建进入 PichiaCLM 密码子优化和湿实验。")
    st.info("模型分数、规则分数和 USPNet 结果都不是实际发酵产量；真实效果必须由小试验证。")


def render_library() -> None:
    st.subheader("候选库")
    st.write("这里展示人工整理的 OPN 基线候选。它们不会因为 UniProt 扩库或相似聚类而被删除。")
    service = opn_library_service()
    frame = pd.DataFrame(service.library_rows())
    if frame.empty:
        st.warning("当前没有候选。")
        return
    columns = [
        "candidate_id",
        "library_stage",
        "source_type",
        "category_label",
        "processing_route",
        "signal_peptide_sequence",
        "signal_peptide_length",
        "rationale",
        "caution",
    ]
    st.dataframe(
        frame[[column for column in columns if column in frame.columns]].rename(
            columns={
                "candidate_id": "候选 ID",
                "library_stage": "库内状态",
                "source_type": "来源类型",
                "category_label": "类别",
                "processing_route": "加工路线",
                "signal_peptide_sequence": "信号肽序列",
                "signal_peptide_length": "长度",
                "rationale": "为什么保留",
                "caution": "风险提示",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.download_button(
        "下载导入模板 CSV",
        service.template_csv(),
        file_name="signal_peptide_candidate_import_template.csv",
        mime="text/csv",
    )


def render_screening() -> None:
    st.subheader("外部发现与筛选")
    st.write("这一步从 UniProt 发现候选，然后用可解释规则检查 N 区正电、H 区疏水核心和 C 区切割位点；USPNet 安装后会作为外部复核。")
    with st.form("screening_form"):
        taxon_id = st.number_input("UniProt taxon ID", min_value=1, value=DEFAULT_TAXON_ID, step=1)
        max_records = st.number_input("最多拉取记录数", min_value=1, max_value=500, value=300, step=25)
        reviewed_only = st.checkbox("只看 reviewed 条目", value=False)
        submitted = st.form_submit_button("建立候选库并比较方法", type="primary")
    if submitted:
        with st.spinner("正在查询/复用 UniProt 候选，并运行规则与 USPNet 比较..."):
            result = _local_screening_service().screen_uniprot_candidates(
                taxon_id=int(taxon_id),
                max_records=int(max_records),
                reviewed_only=bool(reviewed_only),
            )
        st.success(result.message if result.success else "筛选未完成")
    result = _load_result()
    if result is None:
        st.warning("没有可展示的筛选结果。请点击上方按钮运行，或确认 examples/opn/saved_screening 中存在示例结果。")
        return
    _render_summary(result)
    st.caption(f"当前展示目录：{result.output_dir}")
    if result.errors:
        with st.expander("运行提示 / 错误信息", expanded=False):
            st.write(result.errors)


def render_representatives() -> None:
    st.subheader("代表序列与下载")
    st.write("默认表格只展示代表序列。相似序列没有被删除，可以在每个代表序列下面展开查看。")
    result = _load_result()
    if result is None:
        st.warning("没有可展示的筛选结果。")
        return
    rows = pd.DataFrame(result.rows)
    if rows.empty:
        st.info("结果为空。")
        return
    recommended = rows[rows["recommended_for_draft_library"] == True].copy()
    representatives = recommended[recommended["is_representative"] == True].copy()
    if representatives.empty:
        st.info("当前没有代表序列。")
        return
    st.dataframe(
        representatives[
            [
                "candidate_id",
                "accession",
                "protein_name",
                "signal_peptide_sequence",
                "similarity_group_id",
                "similar_group_size",
                "rules_n_region_positive_count",
                "rules_h_region_max_hydrophobicity",
                "rules_c_region_small_neutral",
                "rules_score",
                "uspnet_prediction_label",
                "screening_status",
            ]
        ].rename(
            columns={
                "candidate_id": "候选 ID",
                "accession": "UniProt accession",
                "protein_name": "来源蛋白",
                "signal_peptide_sequence": "信号肽序列",
                "similarity_group_id": "相似分组",
                "similar_group_size": "同组序列数",
                "rules_n_region_positive_count": "N区正电残基数",
                "rules_h_region_max_hydrophobicity": "H区最大疏水性",
                "rules_c_region_small_neutral": "C区切割规则",
                "rules_score": "规则分数",
                "uspnet_prediction_label": "USPNet 预测",
                "screening_status": "综合状态",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    _render_similar_sequence_details(rows, representatives)
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
    with st.expander("规则分数和 USPNet 预测怎么读", expanded=True):
        st.markdown(
            """
            规则分数检查长度、N 区电荷、H 区疏水核心、C 区切割位点和低复杂度风险。
            UniProt 已注释信号肽通常分数会很高，这只说明它像标准信号肽，不代表 OPN 产量更高。
            USPNet=SP 表示机器学习模型也支持它是信号肽；NO_SP 表示需要降级或人工复核。
            """
        )


def _render_similar_sequence_details(rows: pd.DataFrame, representatives: pd.DataFrame) -> None:
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
                        "signal_peptide_sequence",
                        "similarity_percent",
                        "rules_priority",
                        "uspnet_prediction_label",
                        "screening_status",
                    ]
                ].rename(
                    columns={
                        "candidate_id": "候选 ID",
                        "is_representative": "代表序列",
                        "accession": "UniProt accession",
                        "protein_name": "来源蛋白",
                        "signal_peptide_sequence": "信号肽序列",
                        "similarity_percent": "与代表序列相似度%",
                        "rules_priority": "规则优先级",
                        "uspnet_prediction_label": "USPNet 预测",
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


def _load_result() -> SignalPeptideScreeningResult | None:
    local = _local_screening_service().load_persisted_screening_result()
    if local is not None:
        return local
    return _example_screening_service().load_persisted_screening_result()


def _local_screening_service() -> SignalPeptideScreeningService:
    return SignalPeptideScreeningService(
        PATHS.opn_screening_output_dir,
        library_service=opn_library_service(),
        uspnet_adapter=USPNetAdapter(repo_dir=PATHS.uspnet_repo),
    )


def _example_screening_service() -> SignalPeptideScreeningService:
    return SignalPeptideScreeningService(
        PATHS.opn_saved_screening_dir,
        library_service=opn_library_service(),
        uspnet_adapter=USPNetAdapter(repo_dir=PATHS.uspnet_repo),
    )


def _css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }
        [data-testid="stMetricValue"] { font-size: 1.25rem; }
        h1, h2, h3 { letter-spacing: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

