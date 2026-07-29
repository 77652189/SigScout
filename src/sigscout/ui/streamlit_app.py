from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import streamlit as st  # noqa: E402

from sigscout.ui._shared import _css  # noqa: E402
from sigscout.ui.views.experimental_feedback import (  # noqa: E402
    page_experimental_import,
    page_experimental_results,
)
from sigscout.ui.views.fusion_localization import (  # noqa: E402
    page_generate_constructs,
    page_import_localization,
)
from sigscout.ui.views.representatives import (  # noqa: E402
    page_candidate_browser,
    page_evidence_distribution,
    page_raw_data,
    page_similar_sequences,
)
from sigscout.ui.views.screening import page_screening, page_source_annotation  # noqa: E402


def main() -> None:
    _css()
    st.title("SigScout 信号肽筛选工作台")
    st.caption("蛋白层面的信号肽候选发现、来源证据解释、代表序列整理和融合蛋白定位评估。")
    pg = st.navigation(
        {
            "毕赤酵母信号肽筛选": [
                st.Page(page_screening, title="刷新并筛选毕赤酵母信号肽", icon="🔍", default=True),
                st.Page(page_source_annotation, title="评估来源蛋白定位", icon="📍"),
            ],
            "代表序列与下载": [
                st.Page(page_candidate_browser, title="候选浏览", icon="📋"),
                st.Page(page_evidence_distribution, title="证据分布", icon="📊"),
                st.Page(page_similar_sequences, title="相似序列", icon="🔗"),
                st.Page(page_raw_data, title="原始数据", icon="📄"),
            ],
            "融合定位": [
                st.Page(page_generate_constructs, title="生成定位评估文件", icon="🧩"),
                st.Page(page_import_localization, title="导入 DeepLoc 结果", icon="📥"),
            ],
            "实验反馈": [
                st.Page(page_experimental_results, title="实验结果", icon="🧪"),
                st.Page(page_experimental_import, title="导入与模板", icon="📤"),
            ],
        }
    )
    st.sidebar.divider()
    st.sidebar.caption("候选来源：UniProt 中带 signal peptide 注释的毕赤酵母/Komagataella 蛋白。")
    st.sidebar.caption("SigScout 不做目标蛋白适配性预测，也不做密码子优化。")
    pg.run()


if __name__ == "__main__":
    main()
