from io import StringIO

import pandas as pd

from sigscout.services.experimental_feedback import (
    experimental_feedback_template,
    prepare_experimental_feedback,
    summarize_experimental_feedback,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "experiment_id": "opn-r1-a",
            "target_key": "opn",
            "target_variant": "hOPN-1",
            "batch_id": "round-1",
            "signal_peptide_id": "reference",
            "construct_name": "reference-opn",
            "source_construct_name": "reference-α-opn",
            "yield_value": "0.5",
            "yield_unit": "mg/L",
            "strain_background": "X33",
            "integration_locus": "int1",
            "measurement_status": "measured",
            "is_reference_baseline": "true",
            "reference_basis": "上一轮入选构建，需人工确认",
        },
        {
            "experiment_id": "opn-r1-b",
            "target_key": "opn",
            "target_variant": "hOPN-1",
            "batch_id": "round-1",
            "signal_peptide_id": "candidate",
            "construct_name": "candidate-opn",
            "source_construct_name": "candidate-opn",
            "yield_value": "750",
            "yield_unit": "ug/L",
            "strain_background": "X33",
            "integration_locus": "int1",
            "measurement_status": "measured",
            "is_reference_baseline": "false",
        },
        {
            "experiment_id": "opn-r1-missing",
            "target_key": "opn",
            "target_variant": "hOPN-1",
            "batch_id": "round-1",
            "signal_peptide_id": "SCW10",
            "construct_name": "scw10-opn",
            "source_construct_name": "SCW10-opn",
            "yield_value": "",
            "yield_unit": "",
            "strain_background": "X33",
            "integration_locus": "int1",
            "measurement_status": "result_missing",
            "is_reference_baseline": "false",
        },
    ])


def test_feedback_normalizes_units_and_excludes_missing_result_from_metrics() -> None:
    result = prepare_experimental_feedback(_frame(), target_key="opn")
    assert result.valid
    assert result.rows["yield_ug_l"].iloc[:2].tolist() == [500.0, 750.0]
    missing = result.rows.loc[result.rows["measurement_status"] == "result_missing"].iloc[0]
    assert pd.isna(missing["yield_ug_l"])
    assert pd.isna(missing["batch_rank"])
    candidate = result.rows.loc[result.rows["signal_peptide_id"] == "candidate"].iloc[0]
    assert candidate["batch_rank"] == 1
    assert candidate["batch_fold_vs_reference"] == 1.5


def test_feedback_summary_separates_records_measurements_and_missing_results() -> None:
    result = prepare_experimental_feedback(_frame(), target_key="opn")
    summary = summarize_experimental_feedback(result.rows)
    assert summary["records"] == 3
    assert summary["measurements"] == 2
    assert summary["missing_results"] == 1


def test_feedback_rejects_other_target_in_opn_view() -> None:
    frame = _frame()
    frame.loc[1, "target_key"] = "hlf"
    result = prepare_experimental_feedback(frame, target_key="opn")
    assert not result.valid
    assert "hlf" in result.errors[0]


def test_legacy_control_column_migrates_to_reference_with_warning_basis() -> None:
    frame = _frame().drop(
        columns=["source_construct_name", "measurement_status", "is_reference_baseline", "reference_basis"]
    )
    frame["is_batch_control"] = ["true", "false", "false"]
    result = prepare_experimental_feedback(frame, target_key="opn")
    assert result.valid
    reference = result.rows.loc[result.rows["experiment_id"] == "opn-r1-a"].iloc[0]
    assert bool(reference["is_reference_baseline"])
    assert "旧 is_batch_control" in reference["reference_basis"]


def test_template_contains_traceability_and_sequence_columns() -> None:
    template = pd.read_csv(StringIO(experimental_feedback_template()))
    assert {
        "source_construct_name",
        "measurement_status",
        "signal_peptide_nucleotide_sequence",
        "target_protein_sequence",
        "target_nucleotide_sequence",
        "is_reference_baseline",
        "reference_basis",
    }.issubset(template.columns)
