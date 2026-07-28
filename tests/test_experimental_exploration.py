import pandas as pd

from sigscout.services.experimental_exploration import (
    CHANNEL_CONTROL,
    CHANNEL_DIVERSITY,
    CHANNEL_GENERIC,
    CHANNEL_POSITIVE,
    build_experiment_guided_exploration,
)


def test_guided_exploration_excludes_tested_and_fills_channels() -> None:
    rows = [
        _row("positive", "MKAALLLL", "measured", relative=1.0),
        _row("medium", "MKTLLLLL", "measured", relative=0.6),
        _row("low", "MNNNNNNN", "measured", relative=0.2),
    ]
    rows.extend(
        _row(f"candidate-{index}", sequence, "untested", rules=90 + index)
        for index, sequence in enumerate(
            ["MKAALLLA", "MKAALLAA", "MKTLLLLA", "MNNNNNNA", "MFFFFFFF", "MSSSSSSS", "MVVVVVVV", "MIIIIIII"]
        )
    )

    panel = build_experiment_guided_exploration(pd.DataFrame(rows), panel_size=8)

    assert len(panel) == 8
    assert not {"positive", "medium", "low"} & set(panel["candidate_id"])
    assert set(panel["exploration_channel"]) == {
        CHANNEL_POSITIVE,
        CHANNEL_GENERIC,
        CHANNEL_DIVERSITY,
        CHANNEL_CONTROL,
    }
    positive_neighbor = panel.loc[panel["candidate_id"] == "candidate-0"].iloc[0]
    assert positive_neighbor["exploration_positive_anchor"] == "positive"
    assert positive_neighbor["exploration_positive_identity"] > 0.8


def test_guided_exploration_requires_signal_peptide_experimental_anchor() -> None:
    rows = pd.DataFrame([
        {
            **_row("leader", "MKAALLLL", "measured", relative=1.0),
            "experimental_unit_type": "full_leader",
        },
        _row("candidate", "MKAALLLA", "untested"),
    ])

    assert build_experiment_guided_exploration(rows, panel_size=1).empty


def _row(
    candidate_id: str,
    sequence: str,
    status: str,
    *,
    relative: float | None = None,
    rules: int = 95,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "source_note": candidate_id,
        "signal_peptide_sequence": sequence,
        "experimental_status": status,
        "experimental_unit_type": "signal_peptide" if status == "measured" else "",
        "experimental_relative_median": relative,
        "rules_score": rules,
        "consensus_pass": True,
        "uspnet_pass": True,
        "uspnet_prediction": "SP",
        "source_protein_route": "未知",
    }
