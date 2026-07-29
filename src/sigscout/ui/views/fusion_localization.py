from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from sigscout.core.coercion import safe_float
from sigscout.services.experimental_evidence import (
    annotate_construct_experimental_evidence,
    build_target_experimental_candidates,
)
from sigscout.services.experimental_feedback import load_experimental_feedback
from sigscout.services.fusion_constructs import (
    DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
    FUSION_TARGET_PRESETS,
    build_fusion_constructs,
    fusion_constructs_to_csv,
    fusion_constructs_to_fasta,
)
from sigscout.services.fusion_scoring import score_construct, summarize_localization
from sigscout.services.localization_import import import_localization_results
from sigscout.ui._shared import PATHS, _load_representative_frames, _render_pagination_controls, _sorted_unique


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
    source_options = ["使用全部代表序列"]
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
        "internal_hydrophobic_run_max",
        "signal_peptide_quality",
        "construct_design_risk",
        "overall_score",
        "overall_priority",
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
                "internal_hydrophobic_run_max": "最长内部疏水连续段",
                "signal_peptide_quality": "信号肽质量",
                "construct_design_risk": "设计风险",
                "overall_score": "综合分",
                "overall_priority": "优先级",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    _render_batch_processing_notes(preview)


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
            cache_cols[0].success(f"已自动加载 {cached_count} 条 {tool_name.upper()} 缓存结果。")
        else:
            cache_cols[0].success(f"已直接展示 {cached_count} 条 {tool_name.upper()} 缓存结果。")
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
        "external_localization_support",
        "localization_probability_score",
        "source_context_score",
        "membrane_or_vacuole_risk",
        "fine_priority_score",
        "overall_score",
        "overall_priority",
        "construct_length",
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
                "external_localization_support": "外部定位支持",
                "localization_probability_score": "定位概率分",
                "source_context_score": "来源证据分",
                "membrane_or_vacuole_risk": "膜/液泡风险",
                "fine_priority_score": "细化优先分",
                "overall_score": "综合分",
                "overall_priority": "优先级",
                "construct_length": "长度",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    _render_batch_processing_notes(frame)
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


def _render_batch_processing_notes(frame: pd.DataFrame) -> None:
    if frame.empty or "processing_site_note" not in frame.columns:
        return
    lines: list[str] = []
    if "has_er_retention_motif" in frame.columns and bool(frame["has_er_retention_motif"].iloc[0]):
        lines.append("C 末端存在 ER 保留 motif（KDEL/HDEL），可能影响分泌效率，建议复核。")
    seen_notes: set[str] = set()
    for note in frame["processing_site_note"].astype(str):
        note = note.strip()
        if note and note not in seen_notes:
            seen_notes.add(note)
            lines.append(note)
    if not lines:
        return
    with st.container(border=True):
        st.caption("关于当前 B/C 序列（同批次所有构建共用，不随信号肽候选变化）")
        for line in lines:
            st.markdown(f"- {line}")


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

        with st.expander("评分细节"):
            st.markdown(_fusion_score_strip(row), unsafe_allow_html=True)

        st.text_area(
            "融合蛋白序列",
            value=sequence,
            height=110,
            key=f"fusion_sequence_{construct_id}",
            label_visibility="collapsed",
        )
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
