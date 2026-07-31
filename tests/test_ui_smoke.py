"""基本冒烟测试：确认每个 Streamlit 页面能渲染且不抛异常。

用 Streamlit 自带的 AppTest 框架（不开浏览器）。AppTest.from_function 要求传入的
函数必须“自包含”——它会提取函数源码单独执行，脱离原模块的 import 上下文，所以
每个页面都配一个只做“import + 调用”的薄包装函数，不能直接把 view 模块里定义的
page_* 函数传进去（那样会因为找不到它引用的模块级名字而 NameError）。

这些测试只断言“页面渲染无异常”，不断言具体展示内容——具体数值/交互行为仍然靠
手动 Streamlit 走查验证（见 docs/CURRENT_GOALS.md 已知的坑）。页面在没有本地筛选
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


def test_page_import_localization_smoke() -> None:
    at = AppTest.from_function(_run_page_import_localization)
    at.run()
    assert not at.exception
    assert at.subheader or at.markdown or at.metric or at.info or at.warning or at.error


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
