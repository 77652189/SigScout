from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from sigscout.services.experimental_evidence import (
    annotate_candidate_experimental_evidence,
    build_target_experimental_candidates,
)
from sigscout.services.experimental_feedback import load_experimental_feedback
from sigscout.services.experimental_exploration import build_experiment_guided_exploration
from sigscout.ui.target_state import target_state_key


def render_experimental_browser(representatives: pd.DataFrame, local_runs_dir: Path, target_key: str) -> None:
    result = load_experimental_feedback(
        local_runs_dir / "experimental_feedback" / f"{target_key}_measurements.csv", target_key=target_key
    )
    if not result.valid:
        st.warning(f"{target_key.upper()} 实验反馈暂时无法读取，通用候选不受影响。")
        return
    shared = annotate_candidate_experimental_evidence(representatives, result.rows, target_key)
    additions = build_target_experimental_candidates(result.rows, target_key)
    if not additions.empty:
        known = set(shared["signal_peptide_sequence"].astype(str).str.upper())
        additions = additions[~additions["signal_peptide_sequence"].astype(str).str.upper().isin(known)]
        shared = pd.concat([shared, additions], ignore_index=True, sort=False)
    st.caption("精确序列去重；目标专属候选不会写入共享库，实验结果不改变通用预测分。")
    _render_experimental_decision_summary(shared, target_key)
    _render_guided_exploration(shared, target_key)
    frame = _filter_and_sort(shared)
    _selection_bar("top", target_key)
    if frame.empty:
        st.info("没有符合当前条件的候选。")
        return
    page_size_key = target_state_key("experimental_browser_page_size", target_key)
    page_size = st.slider("每页展示数量", 1, min(50, len(frame)), min(12, len(frame)), key=page_size_key)
    total_pages = max(1, (len(frame) + page_size - 1) // page_size)
    page_key = target_state_key("experimental_browser_page", target_key)
    page = min(int(st.session_state.get(page_key, 1)), total_pages)
    _pager(page, total_pages, "top", target_key)
    start = (page - 1) * page_size
    visible = frame.iloc[start:start + page_size]
    for status, label in (("measured", "已测得候选"), ("result_missing", "结果缺失"), ("untested", "未测试候选")):
        rows = visible[visible["experimental_status"].astype(str).eq(status)]
        if rows.empty:
            continue
        st.markdown(f"**{label}**")
        _cards(rows, target_key)
    _pager(page, total_pages, "bottom", target_key)
    _selection_bar("bottom", target_key)


def _render_experimental_decision_summary(frame: pd.DataFrame, target_key: str) -> None:
    measured = frame[frame["experimental_status"].astype(str).eq("measured")].copy()
    missing = frame[frame["experimental_status"].astype(str).eq("result_missing")].copy()
    untested = frame[frame["experimental_status"].astype(str).eq("untested")].copy()
    if measured.empty:
        st.info(f"当前没有可用于候选决策的 {target_key.upper()} 产量结果。")
        return
    measured["_relative"] = pd.to_numeric(
        measured["experimental_relative_median"], errors="coerce"
    )
    measured["实验建议"] = measured["_relative"].map(_experimental_decision)
    measured = measured.sort_values(["_relative", "candidate_id"], ascending=[False, True])

    st.markdown("**实验反馈如何改变候选决策**")
    cols = st.columns(4)
    cols[0].metric("优先复验", int(measured["实验建议"].eq("优先复验").sum()))
    cols[1].metric("中等优先", int(measured["实验建议"].eq("中等优先").sum()))
    cols[2].metric("暂缓", int(measured["实验建议"].eq("暂缓").sum()))
    cols[3].metric("未测试候选", len(untested))
    best = measured.iloc[0]
    st.success(
        f"当前实验锚点：{best.get('source_note', best.get('candidate_id', ''))}；"
        f"批内相对最佳中位数 {_number(best.get('experimental_relative_median'))}。"
        "建议优先进入融合定位比较和下一轮复验。"
    )
    st.caption(
        f"实验反馈只重排 {len(measured)} 个已测蛋白序列；"
        f"{len(untested)} 个未测试候选仍按通用预测探索。"
        f"{len(missing)} 个结果缺失候选不进入实验排名。"
    )

    ranking = measured[[
        "source_note",
        "experimental_unit_type",
        "experimental_relative_median",
        "experimental_relative_min",
        "experimental_relative_max",
        "experimental_batch_count",
        "experimental_record_count",
        "experimental_nucleotide_variant_count",
        "实验建议",
    ]].copy()
    ranking = ranking.rename(columns={
        "source_note": "实验候选",
        "experimental_unit_type": "测试单元",
        "experimental_relative_median": "批内相对最佳中位数",
        "experimental_relative_min": "最小值",
        "experimental_relative_max": "最大值",
        "experimental_batch_count": "轮次",
        "experimental_record_count": "记录数",
        "experimental_nucleotide_variant_count": "核苷酸版本",
    })
    with st.expander("查看实验优先级排名与使用边界", expanded=False):
        st.dataframe(
            ranking,
            hide_index=True,
            use_container_width=True,
            column_config={
                "批内相对最佳中位数": st.column_config.ProgressColumn(
                    min_value=0.0, max_value=1.0, format="%.3f"
                ),
                "最小值": st.column_config.NumberColumn(format="%.3f"),
                "最大值": st.column_config.NumberColumn(format="%.3f"),
            },
        )
        st.caption(
            "判定规则：中位数 ≥0.80 为优先复验，0.50-0.80 为中等优先，<0.50 为暂缓。"
            "这是候选分层规则，不是跨轮次绝对产量比较，也不表示统计显著性。"
        )


def _render_guided_exploration(frame: pd.DataFrame, target_key: str) -> None:
    st.markdown("**实验引导探索**")
    cols = st.columns([1.2, 2.3])
    panel_size = cols[0].segmented_control(
        "探索池规模",
        [20, 40, 60],
        default=40,
        key=target_state_key("experimental_exploration_panel_size", target_key),
    )
    cols[1].caption(
        "用短信号肽实验锚点压缩未测试范围；完整 leader 不与短信号肽混算。"
        "面板兼顾正向邻域、通用高分、多样性和低表现机制对照。"
    )
    panel = build_experiment_guided_exploration(frame, panel_size=int(panel_size or 40))
    if panel.empty:
        st.info("当前实验锚点不足，暂时无法生成实验引导探索池。")
        return
    channel_counts = panel["exploration_channel"].value_counts()
    metrics = st.columns(5)
    metrics[0].metric("未测试候选", int(frame["experimental_status"].astype(str).eq("untested").sum()))
    metrics[1].metric("探索池", len(panel))
    metrics[2].metric("正向邻域", int(channel_counts.get("正向锚点邻域", 0)))
    metrics[3].metric("多样性保留", int(channel_counts.get("多样性保留", 0)))
    metrics[4].metric("机制对照", int(channel_counts.get("低表现邻域对照", 0)))

    selection_key = target_state_key("fusion_selected_candidate_ids", target_key)
    selected = set(st.session_state.get(selection_key, []))
    panel_ids = set(panel["candidate_id"].astype(str))
    action_cols = st.columns([2.4, 1.2])
    action_cols[0].caption(
        f"已将 {int(frame['experimental_status'].astype(str).eq('untested').sum())} 个未测试候选"
        f"压缩为 {len(panel)} 个可讨论面板。该面板用于决定下一轮测试，不是产量预测。"
    )
    if action_cols[1].button(
        "将探索池加入融合评估",
        key=target_state_key(f"add_exploration_panel_{len(panel)}", target_key),
        type="primary",
    ):
        st.session_state[selection_key] = sorted(selected | panel_ids)
        st.success(f"已加入 {len(panel_ids)} 个探索候选。")
        st.rerun()

    display = panel[[
        "candidate_id",
        "exploration_channel",
        "exploration_reason",
        "exploration_positive_anchor",
        "exploration_positive_identity",
        "exploration_low_anchor",
        "exploration_low_identity",
        "exploration_generic_support",
        "exploration_guided_score",
        "source_protein_route",
    ]].copy()
    display = display.rename(columns={
        "candidate_id": "候选 ID",
        "exploration_channel": "入选通道",
        "exploration_reason": "为什么入选",
        "exploration_positive_anchor": "最近正向锚点",
        "exploration_positive_identity": "正向相似度",
        "exploration_low_anchor": "最近低表现锚点",
        "exploration_low_identity": "低表现相似度",
        "exploration_generic_support": "通用证据",
        "exploration_guided_score": "探索优先度",
        "source_protein_route": "来源分类",
    })
    with st.expander(f"查看 {len(panel)} 个实验引导探索候选", expanded=True):
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "正向相似度": st.column_config.NumberColumn(format="%.3f"),
                "低表现相似度": st.column_config.NumberColumn(format="%.3f"),
                "通用证据": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.3f"),
                "探索优先度": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.3f"),
            },
        )
        st.caption(
            "探索优先度仅用于本面板内部排序。相似度采用短信号肽氨基酸序列编辑距离；"
            "接近低表现锚点的候选被保留为机制对照，不代表推荐生产。"
        )


def _experimental_decision(value: object) -> str:
    try:
        relative = float(value)
    except (TypeError, ValueError):
        return "证据不足"
    if pd.isna(relative):
        return "证据不足"
    if relative >= 0.80:
        return "优先复验"
    if relative >= 0.50:
        return "中等优先"
    return "暂缓"


def _filter_and_sort(frame: pd.DataFrame) -> pd.DataFrame:
    cols = st.columns([1, 1, 2])
    status = cols[0].selectbox("实验状态", ["全部", "已测得", "结果缺失", "未测试"])
    units = cols[1].multiselect(
        "测试单元类型", ["signal_peptide", "full_leader", "leader_variant"],
        default=["signal_peptide", "full_leader", "leader_variant"],
    )
    search = cols[2].text_input("搜索实验候选", placeholder="候选 ID / 序列 / 来源")
    status_map = {"已测得": "measured", "结果缺失": "result_missing", "未测试": "untested"}
    if status != "全部":
        frame = frame[frame["experimental_status"].astype(str).eq(status_map[status])]
    if units:
        tested = frame["experimental_status"].astype(str).ne("untested")
        frame = frame[~tested | frame["experimental_unit_type"].astype(str).isin(units)]
    if search.strip():
        columns = [name for name in ("candidate_id", "signal_peptide_sequence", "source_note") if name in frame]
        text = frame[columns].astype(str).agg(" ".join, axis=1)
        frame = frame[text.str.contains(search.strip(), case=False, regex=False, na=False)]
    frame = frame.copy()
    frame["_tested_rank"] = frame["experimental_status"].map({"measured": 0, "result_missing": 1}).fillna(2)
    frame["_relative"] = pd.to_numeric(frame["experimental_relative_median"], errors="coerce").fillna(-1)
    frame["_rules"] = pd.to_numeric(frame.get("rules_score", 0), errors="coerce").fillna(-1)
    return frame.sort_values(
        ["_tested_rank", "_relative", "_rules", "candidate_id"],
        ascending=[True, False, False, True],
    ).drop(columns=["_tested_rank", "_relative", "_rules"])


def _cards(frame: pd.DataFrame, target_key: str) -> None:
    selection_key = target_state_key("fusion_selected_candidate_ids", target_key)
    selected = set(st.session_state.get(selection_key, []))
    for _, row in frame.iterrows():
        candidate_id = str(row.get("candidate_id", ""))
        with st.container(border=True):
            cols = st.columns([3, 1])
            cols[0].markdown(f"**{candidate_id}**")
            cols[0].caption(f"{row.get('experimental_unit_type', '')} · {row.get('source_note', '')}")
            if cols[1].button(
                "移出融合评估" if candidate_id in selected else "加入融合评估",
                key=target_state_key(f"experimental_select_{candidate_id}", target_key),
                type="secondary" if candidate_id in selected else "primary",
            ):
                selected.remove(candidate_id) if candidate_id in selected else selected.add(candidate_id)
                st.session_state[selection_key] = sorted(selected)
                st.rerun()
            st.code(str(row.get("signal_peptide_sequence", "")), language=None)
            status = str(row.get("experimental_status", ""))
            if status == "measured":
                decision = _experimental_decision(row.get("experimental_relative_median"))
                if decision == "优先复验":
                    st.success("实验建议：优先复验，并加入融合定位比较。")
                elif decision == "中等优先":
                    st.info("实验建议：中等优先，可作为第二梯队复验。")
                else:
                    st.warning("实验建议：当前暂缓，除非需要机制对照或扩大序列多样性。")
                st.write(
                    f"批内相对最佳：中位数 {_number(row.get('experimental_relative_median'))}，"
                    f"范围 {_number(row.get('experimental_relative_min'))}-{_number(row.get('experimental_relative_max'))}；"
                    f"{row.get('experimental_batch_count', 0)} 轮 / {row.get('experimental_record_count', 0)} 条记录；"
                    f"{row.get('experimental_nucleotide_variant_count', 0)} 个核苷酸版本。"
                )
            elif status == "result_missing":
                st.warning("报告提及该序列，但未提供产量，不参与实验排序。")
            else:
                st.caption(f"尚无 {target_key.upper()} 实验结果，保留通用预测次序。")
            st.caption(str(row.get("experimental_note", "")))


def _selection_bar(position: str, target_key: str) -> None:
    selection_key = target_state_key("fusion_selected_candidate_ids", target_key)
    selected = set(st.session_state.get(selection_key, []))
    cols = st.columns([2, 1, 1])
    cols[0].metric("已选融合候选", len(selected))
    with cols[1].popover("查看已选", disabled=not selected):
        for candidate_id in sorted(selected):
            st.write(candidate_id)
    if cols[2].button(
        "清空",
        key=target_state_key(f"experimental_clear_{position}", target_key),
        disabled=not selected,
    ):
        st.session_state[selection_key] = []
        st.rerun()


def _pager(page: int, total_pages: int, position: str, target_key: str) -> None:
    page_key = target_state_key("experimental_browser_page", target_key)
    cols = st.columns([1, 1, 2, 1, 1])
    if cols[0].button("首页", key=target_state_key(f"experimental_first_{position}", target_key), disabled=page == 1):
        st.session_state[page_key] = 1
        st.rerun()
    if cols[1].button("上一页", key=target_state_key(f"experimental_prev_{position}", target_key), disabled=page == 1):
        st.session_state[page_key] = page - 1
        st.rerun()
    jump = cols[2].number_input(
        "页码",
        1,
        total_pages,
        page,
        key=target_state_key(f"experimental_jump_{position}", target_key),
    )
    if cols[3].button("跳转", key=target_state_key(f"experimental_go_{position}", target_key)):
        st.session_state[page_key] = int(jump)
        st.rerun()
    if cols[4].button(
        "下一页",
        key=target_state_key(f"experimental_next_{position}", target_key),
        disabled=page == total_pages,
    ):
        st.session_state[page_key] = page + 1
        st.rerun()
    st.caption(f"第 {page} / {total_pages} 页")


def _number(value: object) -> str:
    try:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "-"
