from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from sigscout.services.experimental_feedback import (
    experimental_feedback_template,
    load_experimental_feedback,
    parse_experimental_feedback_csv,
    save_experimental_feedback,
    summarize_experimental_feedback,
)
from sigscout.ui._shared import PATHS


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
        "result_missing": "结果缺失",
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
    st.caption("数据保存在本地忽略目录。上传会替换当前 OPN 实验反馈文件，不会修改候选库。")
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
