from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st  # noqa: E402

from sigscout.ui._shared import _css  # noqa: E402
from sigscout.ui.views.experimental_feedback import render_experimental_feedback  # noqa: E402
from sigscout.ui.views.fusion_localization import render_fusion_localization  # noqa: E402
from sigscout.ui.views.representatives import render_representatives  # noqa: E402
from sigscout.ui.views.screening import render_screening  # noqa: E402


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


if __name__ == "__main__":
    main()
