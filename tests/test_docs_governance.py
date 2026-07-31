from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
ACTIVE_DOCS = {"REQUIREMENTS.md", "ARCHITECTURE.md", "EXECUTION_PLAN.md", "HANDOFF.md"}
HANDOFF_SECTIONS = {"## 当前目标", "## 下一步", "## 必读材料", "## 验证方式", "## 硬约束"}
ADR_SECTIONS = {"## 背景", "## 决策", "## 后果", "## 替代关系"}
HARD_BOUNDARIES = {
    "公开 README 与受跟踪工程文档不得出现具体目标蛋白名称、其 accession 或点名该目标的文献引用。",
    "实验引导结果不得表述为真实分泌产量预测、跨批次比较或统计显著性结论。",
    "短信号肽与完整 leader 不得在同一实验引导评分中直接混合比较。",
    "实验反馈只按精确氨基酸序列关联；仅 A 段一致不得表述为完整构建已经验证。",
    "目标专属实验反馈、融合构建和定位缓存不得跨目标复用。",
    "未经明确授权，不提交、不推送、不改变远端可见性。",
}


def test_docs_root_has_exactly_the_active_document_set() -> None:
    assert DOCS.is_dir()
    assert {path.name for path in DOCS.glob("*.md") if path.is_file()} == ACTIVE_DOCS
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "!docs/HANDOFF.md" in ignored


def test_obsolete_status_and_changelog_docs_stay_deleted() -> None:
    names = {path.name for path in DOCS.rglob("*.md") if path.is_file()}
    assert {"CURRENT_GOALS.md", "ARCHITECTURE_CHANGES.md"}.isdisjoint(names)


def test_handoff_has_required_structure_and_stable_boundaries() -> None:
    handoff = (DOCS / "HANDOFF.md").read_text(encoding="utf-8")
    headings = {line.strip() for line in handoff.splitlines()}
    assert HANDOFF_SECTIONS <= headings
    assert HARD_BOUNDARIES <= set(handoff.splitlines())
    assert re.search(r"^slice_status: (awaiting_authorization|in_progress|blocked|complete)$", handoff, re.M)
    assert re.search(r"^current_slice: [a-z_]+$", handoff, re.M)
    assert re.search(r"^next_action: [a-z_]+$", handoff, re.M)


def test_adr_index_points_to_the_full_accepted_set() -> None:
    adr_dir = DOCS / "adr"
    assert adr_dir.is_dir()
    index = (adr_dir / "README.md").read_text(encoding="utf-8")
    expected = {
        "001-confidential-document-scope.md",
        "002-direct-service-imports.md",
        "003-streamlit-native-navigation.md",
        "004-shared-library-target-overlays.md",
        "005-experimental-evidence-boundary.md",
        "006-guided-exploration-not-yield-model.md",
        "007-source-annotation-lifecycle.md",
    }
    assert {path.name for path in adr_dir.glob("[0-9][0-9][0-9]-*.md")} == expected
    for name in expected:
        assert name in index
        assert re.search(rf"\[{name[:3]}\]\({re.escape(name)}\) \| (accepted|superseded by \d{{3}}) \|", index)
        headings = {
            line.strip()
            for line in (adr_dir / name).read_text(encoding="utf-8").splitlines()
        }
        assert ADR_SECTIONS <= headings
