from __future__ import annotations

from pathlib import Path

from sigscout.adapters.uspnet import USPNetAdapter, parse_uspnet_results


def test_parse_uspnet_results_maps_rows_to_fasta_ids(tmp_path: Path) -> None:
    results = tmp_path / "results.csv"
    results.write_text(
        "sequence,predicted_type,predicted_cleavage\n"
        "MKALLLALLALAAASAGA,SP,MKALLLALLALAAASAGA\n"
        "MNNNNNNNNNNNNNNNNN,LIPO,MNNNNNNNNNN\n",
        encoding="utf-8",
    )

    predictions = parse_uspnet_results(results, ["A", "B"])

    assert predictions[0].candidate_id == "A"
    assert predictions[0].predicted_type == "SP"
    assert predictions[0].passed is True
    assert predictions[1].candidate_id == "B"
    assert predictions[1].predicted_type == "LIPO"
    assert predictions[1].predicted_cleavage == "MNNNNNNNNNN"
    assert predictions[1].passed is False


def test_uspnet_missing_returns_chinese_message(tmp_path: Path) -> None:
    adapter = USPNetAdapter(repo_dir=tmp_path / "missing")
    status = adapter.status()

    assert status.available is False
    assert "未检测到 USPNet" in status.message
