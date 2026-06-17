from __future__ import annotations

from sigscout.services.rules import score_signal_peptide


def test_rule_screening_accepts_typical_secretory_signal_peptide() -> None:
    result = score_signal_peptide("MKALLLALLALAAASAGA")

    assert result.passed is True
    assert result.n_region_positive_count >= 1
    assert result.n_region_pass is True
    assert result.h_region_max_hydrophobicity >= 1.8
    assert result.h_region_pass is True
    assert result.c_region_small_neutral_rule is True


def test_rule_screening_rejects_low_complexity_non_hydrophobic_sequence() -> None:
    result = score_signal_peptide("MNNNNNNNNNNNNNNNNN")

    assert result.passed is False
    assert result.h_region_pass is False
    assert any("疏水核心" in risk for risk in result.risks)

