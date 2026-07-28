import pandas as pd

from sigscout.ui.experimental_browser import _experimental_decision

from sigscout.services.experimental_evidence import (
    annotate_candidate_experimental_evidence,
    annotate_construct_experimental_evidence,
    build_target_experimental_candidates,
)


def _feedback() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "target_key": "opn", "batch_id": "r1", "signal_peptide_id": "alpha-factor",
            "signal_peptide_sequence": "MKAAA", "signal_peptide_nucleotide_sequence": "ATGAAA",
            "target_protein_sequence": "CCC", "construct_variant": "wild_type",
            "measurement_status": "measured", "batch_relative_to_best": 0.5,
        },
        {
            "target_key": "opn", "batch_id": "r2", "signal_peptide_id": "alpha-factor",
            "signal_peptide_sequence": "MKAAA", "signal_peptide_nucleotide_sequence": "ATGAAG",
            "target_protein_sequence": "CCC", "construct_variant": "wild_type",
            "measurement_status": "measured", "batch_relative_to_best": 1.0,
        },
        {
            "target_key": "opn", "batch_id": "r1", "signal_peptide_id": "alpha-factor",
            "signal_peptide_sequence": "MKAAV", "signal_peptide_nucleotide_sequence": "ATGGTT",
            "target_protein_sequence": "CCC", "construct_variant": "V50A",
            "measurement_status": "measured", "batch_relative_to_best": 0.8,
        },
        {
            "target_key": "opn", "batch_id": "r3", "signal_peptide_id": "SCW10",
            "signal_peptide_sequence": "MSSS", "signal_peptide_nucleotide_sequence": "ATGTCC",
            "target_protein_sequence": "CCC", "construct_variant": "wild_type",
            "measurement_status": "result_missing", "batch_relative_to_best": float("nan"),
        },
    ])


def test_build_candidates_deduplicates_aa_and_aggregates_variants() -> None:
    rows = build_target_experimental_candidates(_feedback(), "opn")
    assert len(rows) == 3
    alpha = rows.loc[rows["signal_peptide_sequence"] == "MKAAA"].iloc[0]
    assert alpha["experimental_unit_type"] == "full_leader"
    assert alpha["experimental_relative_median"] == 0.75
    assert alpha["experimental_record_count"] == 2
    assert alpha["experimental_batch_count"] == 2
    assert alpha["experimental_nucleotide_variant_count"] == 2
    variant = rows.loc[rows["signal_peptide_sequence"] == "MKAAV"].iloc[0]
    assert variant["experimental_unit_type"] == "leader_variant"


def test_candidate_annotation_is_exact_sequence_only() -> None:
    candidates = pd.DataFrame([
        {"candidate_id": "shared", "signal_peptide_sequence": "MKAAA", "rules_score": 99},
        {"candidate_id": "near", "signal_peptide_sequence": "MKAAT", "rules_score": 98},
    ])
    annotated = annotate_candidate_experimental_evidence(candidates, _feedback(), "opn")
    assert annotated.iloc[0]["experimental_status"] == "measured"
    assert annotated.iloc[1]["experimental_status"] == "untested"
    assert annotated["rules_score"].tolist() == [99, 98]


def test_construct_annotation_separates_exact_ac_a_only_and_missing() -> None:
    constructs = pd.DataFrame([
        {"construct_id": "ac", "construct_type": "AC", "a_signal_peptide": "MKAAA", "construct_sequence": "MKAAACCC", "overall_score": 11},
        {"construct_id": "abc", "construct_type": "ABC", "a_signal_peptide": "MKAAA", "construct_sequence": "MKAAABBBCCC", "overall_score": 12},
        {"construct_id": "changed-c", "construct_type": "AC", "a_signal_peptide": "MKAAA", "construct_sequence": "MKAAACCD", "overall_score": 13},
        {"construct_id": "missing", "construct_type": "AC", "a_signal_peptide": "MSSS", "construct_sequence": "MSSSCCC", "overall_score": 14},
    ])
    annotated = annotate_construct_experimental_evidence(constructs, _feedback(), "opn")
    assert annotated["experimental_match_type"].tolist() == [
        "exact_construct", "a_sequence_only", "a_sequence_only", "result_missing"
    ]
    assert annotated["overall_score"].tolist() == [11, 12, 13, 14]


def test_hlf_never_loads_opn_evidence() -> None:
    constructs = pd.DataFrame([
        {"construct_id": "hlf", "construct_type": "AC", "a_signal_peptide": "MKAAA", "construct_sequence": "MKAAACCC"}
    ])
    annotated = annotate_construct_experimental_evidence(constructs, _feedback(), "hlf")
    assert annotated.iloc[0]["experimental_match_type"] == "none"
    assert annotated.iloc[0]["experimental_status"] == "untested"

def test_experimental_decision_thresholds_are_explicit() -> None:
    assert _experimental_decision(0.80) == "优先复验"
    assert _experimental_decision(0.50) == "中等优先"
    assert _experimental_decision(0.499) == "暂缓"
    assert _experimental_decision(float("nan")) == "证据不足"

