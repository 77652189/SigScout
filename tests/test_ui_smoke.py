"""基本冒烟测试：确认每个 Streamlit 页面能渲染且不抛异常。

用 Streamlit 自带的 AppTest 框架（不开浏览器）。AppTest.from_function 要求传入的
函数必须“自包含”——它会提取函数源码单独执行，脱离原模块的 import 上下文，所以
每个页面都配一个只做“import + 调用”的薄包装函数，不能直接把 view 模块里定义的
page_* 函数传进去（那样会因为找不到它引用的模块级名字而 NameError）。

这些测试只断言“页面渲染无异常”，不断言具体展示内容——具体数值/交互行为仍然靠
手动 Streamlit 走查验证（见 docs/HANDOFF.md 的验证方式）。页面在没有本地筛选
结果/实验数据时会优雅降级成提示信息而不是报错，所以这些测试在全新 checkout（没有
local_runs/、examples/opn/saved_screening/）上也应该能通过。
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _run_page_screening() -> None:
    from sigscout.ui.views.screening import page_screening

    page_screening()


def _run_page_source_annotation() -> None:
    from sigscout.ui.views.screening import page_source_annotation

    page_source_annotation()


def _run_page_candidate_browser() -> None:
    from sigscout.ui.views.representatives import page_candidate_browser

    page_candidate_browser()


def _run_page_evidence_distribution() -> None:
    from sigscout.ui.views.representatives import page_evidence_distribution

    page_evidence_distribution()


def _run_page_similar_sequences() -> None:
    from sigscout.ui.views.representatives import page_similar_sequences

    page_similar_sequences()


def _run_page_raw_data() -> None:
    from sigscout.ui.views.representatives import page_raw_data

    page_raw_data()


def _run_page_generate_constructs() -> None:
    from sigscout.ui.views.fusion_localization import page_generate_constructs

    page_generate_constructs()


def _run_page_import_localization() -> None:
    from sigscout.ui.views.fusion_localization import page_import_localization

    page_import_localization()


def _run_page_import_localization_with_hlf_construct() -> None:
    import streamlit as st

    from sigscout.services.fusion_constructs import build_fusion_constructs
    from sigscout.ui.target_state import target_state_key
    from sigscout.ui.views.fusion_localization import page_import_localization

    st.session_state["fusion_target_key"] = "hlf"
    st.session_state[target_state_key("fusion_construct_rows", "hlf")] = build_fusion_constructs(
        [{"candidate_id": "TEST", "signal_peptide_sequence": "MKTLLA"}],
        b_sequence="",
        c_sequence="QWERTY",
        target_key="hlf",
        include_abc=False,
        include_controls=False,
    ).rows
    page_import_localization()


def _run_page_import_localization_from_manifest() -> None:
    import os
    from pathlib import Path

    import sigscout.ui.views.fusion_localization as view
    from sigscout.core.paths import ProjectPaths

    original_paths = view.PATHS
    view.PATHS = ProjectPaths(Path(os.environ["SIGSCOUT_TEST_PROJECT_ROOT"]))
    try:
        view.page_import_localization()
    finally:
        view.PATHS = original_paths


def _run_generation_lookup_without_manifest_restore() -> None:
    import os
    from pathlib import Path

    import streamlit as st

    import sigscout.ui.views.fusion_localization as view
    from sigscout.core.paths import ProjectPaths

    original_paths = view.PATHS
    view.PATHS = ProjectPaths(Path(os.environ["SIGSCOUT_TEST_PROJECT_ROOT"]))
    try:
        rows = view._target_construct_rows("hlf", load_manifest=False)
        st.caption(f"rows={len(rows)}")
    finally:
        view.PATHS = original_paths


def _run_batch_processing_notes_with_csv_booleans() -> None:
    import pandas as pd

    from sigscout.ui.views.fusion_localization import _render_batch_processing_notes

    _render_batch_processing_notes(
        pd.DataFrame(
            [
                {
                    "construct_type": "C_ONLY",
                    "has_er_retention_motif": "False",
                    "processing_site_note": "ABC 未提供 B 序列。",
                },
                {
                    "construct_type": "AC",
                    "has_er_retention_motif": "False",
                    "processing_site_note": "A 直接连接 C。",
                }
            ]
        )
    )


def _run_scoped_fusion_target_selector() -> None:
    import streamlit as st

    from sigscout.ui.views.fusion_localization import _select_fusion_target

    scope = str(st.session_state.get("test_target_selector_scope", "generation"))
    selected, _ = _select_fusion_target(scope)
    st.caption(f"selected={selected}")


def _run_page_experimental_results() -> None:
    from sigscout.ui.views.experimental_feedback import page_experimental_results

    page_experimental_results()


def _run_page_experimental_import() -> None:
    from sigscout.ui.views.experimental_feedback import page_experimental_import

    page_experimental_import()


def test_page_screening_smoke() -> None:
    at = AppTest.from_function(_run_page_screening)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_page_source_annotation_smoke() -> None:
    at = AppTest.from_function(_run_page_source_annotation)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_page_candidate_browser_smoke() -> None:
    at = AppTest.from_function(_run_page_candidate_browser)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_page_evidence_distribution_smoke() -> None:
    at = AppTest.from_function(_run_page_evidence_distribution)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_page_similar_sequences_smoke() -> None:
    at = AppTest.from_function(_run_page_similar_sequences)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_page_raw_data_smoke() -> None:
    at = AppTest.from_function(_run_page_raw_data)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_page_generate_constructs_smoke() -> None:
    at = AppTest.from_function(_run_page_generate_constructs)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_fusion_target_switch_restores_target_specific_inputs() -> None:
    at = AppTest.from_function(_run_page_generate_constructs)
    at.session_state["fusion_target_key"] = "hlf"
    at.session_state["fusion_b_sequence_hlf"] = "HLFB"
    at.session_state["fusion_b_sequence_opn"] = "OPNB"

    at.run()
    assert at.text_area[0].key == "fusion_b_sequence_hlf"
    assert at.text_area[0].value == "HLFB"

    at.selectbox[0].set_value("opn")
    at.run()
    assert at.text_area[0].key == "fusion_b_sequence_opn"
    assert at.text_area[0].value == "OPNB"

    at.selectbox[0].set_value("hlf")
    at.run()
    assert at.text_area[0].value == "HLFB"


def test_fusion_target_survives_selector_scope_change() -> None:
    at = AppTest.from_function(_run_scoped_fusion_target_selector)
    at.run()

    at.selectbox[0].set_value("hlf")
    at.run()
    assert at.session_state["fusion_target_key"] == "hlf"

    at.session_state["test_target_selector_scope"] = "import"
    at.run()

    assert not at.exception
    assert at.session_state["fusion_target_key"] == "hlf"
    assert at.selectbox[0].value == "hlf"
    assert any(caption.value == "selected=hlf" for caption in at.caption)


def test_page_import_localization_smoke() -> None:
    at = AppTest.from_function(_run_page_import_localization)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error
    assert len(at.get("file_uploader")) == 1


def test_page_import_localization_keeps_hlf_constructs() -> None:
    at = AppTest.from_function(_run_page_import_localization_with_hlf_construct)
    at.run()
    assert not at.exception
    assert any("当前可匹配 1 条融合构建" in caption.value for caption in at.caption)


def test_import_page_restores_target_manifest_after_session_loss(tmp_path, monkeypatch) -> None:
    from sigscout.services.fusion_constructs import (
        build_fusion_constructs,
        save_fusion_construct_manifest,
    )

    project_root = tmp_path / "project"
    output_dir = project_root / "local_runs" / "opn_signal_peptides"
    rows = build_fusion_constructs(
        [{"candidate_id": "TEST", "signal_peptide_sequence": "MKTLLA"}],
        b_sequence="",
        c_sequence="QWERTY",
        target_key="hlf",
        include_abc=False,
        include_controls=False,
    ).rows
    save_fusion_construct_manifest(rows, output_dir, "hlf")
    monkeypatch.setenv("SIGSCOUT_TEST_PROJECT_ROOT", str(project_root))

    at = AppTest.from_function(_run_page_import_localization_from_manifest)
    at.session_state["fusion_target_key"] = "hlf"
    at.run()

    assert not at.exception
    assert any("当前可匹配 1 条融合构建" in caption.value for caption in at.caption)

    generation = AppTest.from_function(_run_generation_lookup_without_manifest_restore)
    generation.run()
    assert not generation.exception
    assert any(caption.value == "rows=0" for caption in generation.caption)


def test_batch_processing_notes_parse_csv_false_as_false() -> None:
    at = AppTest.from_function(_run_batch_processing_notes_with_csv_booleans)
    at.run()

    assert not at.exception
    assert not any("ER 保留 motif" in markdown.value for markdown in at.markdown)
    assert not any("ABC 未提供 B 序列" in markdown.value for markdown in at.markdown)


def test_page_experimental_results_smoke() -> None:
    at = AppTest.from_function(_run_page_experimental_results)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_page_experimental_import_smoke() -> None:
    at = AppTest.from_function(_run_page_experimental_import)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


def test_pages_degrade_gracefully_without_local_data(tmp_path, monkeypatch) -> None:
    """模拟全新 checkout（没有 local_runs/、examples/opn/saved_screening/）：

    这几个页面应该走各自的“没有可展示的筛选结果”提示分支返回，而不是抛异常。
    验证的是这份代码库里已经存在的优雅降级逻辑，不是新增行为。
    """
    import sigscout.ui._shared as shared
    from sigscout.core.paths import ProjectPaths

    empty_root = tmp_path / "empty_project"
    (empty_root / "src" / "sigscout").mkdir(parents=True)
    (empty_root / "pyproject.toml").touch()
    monkeypatch.setattr(shared, "PATHS", ProjectPaths(empty_root))

    for run_page in (
        _run_page_screening,
        _run_page_candidate_browser,
        _run_page_generate_constructs,
    ):
        at = AppTest.from_function(run_page)
        at.run()
        assert not at.exception
        assert at.warning


def test_pages_degrade_gracefully_for_target_without_data() -> None:
    """目标切到 hlf（占位目标，尚无实测数据）：候选浏览的目标实验视图和实验反馈页面
    应该走"当前目标暂无数据"的通用空态分支，而不是抛异常或残留旧的硬编码占位文案。

    验证的是 hLF 泛化改动新增的"目标有效、但没有该目标的数据"路径，区别于上面
    test_pages_degrade_gracefully_without_local_data 验证的"完全没有 local_runs 目录"场景。
    """
    at = AppTest.from_function(_run_page_candidate_browser)
    at.session_state["candidate_browser_mode"] = "目标实验视图"
    at.session_state["fusion_target_key"] = "hlf"
    at.run()
    assert not at.exception

    at = AppTest.from_function(_run_page_experimental_results)
    at.session_state["fusion_target_key"] = "hlf"
    at.run()
    assert not at.exception
