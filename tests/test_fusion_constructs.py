from __future__ import annotations

from sigscout.services.fusion_constructs import (
    DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
    DEFAULT_HLF_REFERENCE_SEQUENCE,
    DEFAULT_HLF_TARGET_SEQUENCE,
    DEFAULT_OPN_TARGET_SEQUENCE,
    FUSION_TARGET_PRESETS,
    build_fusion_constructs,
    fusion_constructs_to_fasta,
    load_fusion_construct_manifest,
    save_fusion_construct_manifest,
)
from sigscout.services.fusion_scoring import score_construct, summarize_localization
from sigscout.services.localization_import import import_localization_results


def test_build_fusion_constructs_exports_ac_and_abc() -> None:
    result = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
    )

    assert result.errors == []
    by_kind = {(row["candidate_id"], row["construct_type"]): row for row in result.rows}
    assert set(by_kind) == {("CONTROL", "C_ONLY"), ("CONTROL", "BC"), ("SP_A", "AC"), ("SP_A", "ABC")}
    assert by_kind[("CONTROL", "C_ONLY")]["construct_sequence"] == "QWERTY"
    assert by_kind[("SP_A", "AC")]["construct_sequence"] == "MKAALLQWERTY"
    assert by_kind[("SP_A", "ABC")]["construct_sequence"] == "MKAALLEAEAQWERTY"
    assert by_kind[("SP_A", "ABC")]["b_length"] == 4
    assert by_kind[("SP_A", "AC")]["overall_priority"] == "待外部定位"

    fasta = fusion_constructs_to_fasta(result.rows)

    assert f">{by_kind[('SP_A', 'AC')]['construct_id']}|source=SP_A|type=AC|target=custom|len=12" in fasta
    assert "MKAALLEAEAQWERTY" in fasta


def test_construct_identity_is_scoped_by_target_and_full_sequence() -> None:
    common = {
        "signal_rows": [_signal_row("SP A/1", "MKAALL")],
        "b_sequence": "EAEA",
        "include_abc": False,
        "include_controls": False,
    }
    opn = build_fusion_constructs(c_sequence="QWERTY", target_key="opn", **common).rows[0]
    hlf = build_fusion_constructs(c_sequence="QWERTY", target_key="hlf", **common).rows[0]
    changed_a = build_fusion_constructs(
        [_signal_row("SP A/1", "MKAALM")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        target_key="opn",
        include_abc=False,
        include_controls=False,
    ).rows[0]
    changed_c = build_fusion_constructs(c_sequence="QWERTA", target_key="opn", **common).rows[0]
    abc = build_fusion_constructs(
        [_signal_row("SP A/1", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        target_key="opn",
        include_ac=False,
        include_controls=False,
    ).rows[0]
    changed_b = build_fusion_constructs(
        [_signal_row("SP A/1", "MKAALL")],
        b_sequence="EAEV",
        c_sequence="QWERTY",
        target_key="opn",
        include_ac=False,
        include_controls=False,
    ).rows[0]

    assert opn["construct_id"].startswith("opn__SP_A_1__AC__")
    assert hlf["construct_id"].startswith("hlf__SP_A_1__AC__")
    assert len(opn["construct_sequence_sha1"]) == 40
    assert opn["construct_schema_version"] == 2
    assert len({opn["construct_id"], hlf["construct_id"], changed_a["construct_id"], changed_c["construct_id"]}) == 4
    assert abc["construct_id"] != changed_b["construct_id"]


def test_build_fusion_constructs_rejects_invalid_fixed_sequence() -> None:
    result = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEAX",
        c_sequence="QWERTY",
    )

    assert result.rows == []
    assert "B 序列含有非标准氨基酸字符" in result.errors[0]


def test_default_alpha_factor_b_sequence_is_treated_as_pro_region() -> None:
    result = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence=DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
        c_sequence="QWERTY",
        include_ac=False,
    )

    assert result.errors == []
    row = next(row for row in result.rows if row["candidate_id"] == "SP_A" and row["construct_type"] == "ABC")
    assert row["b_ends_with_kex2_site"] is True
    assert row["b_pre_region_like"] is False
    assert "pro 区片段" in row["processing_site_note"]
    assert row["b_c_junction"] == "VSLEKR|QWERTY"


def test_default_b_and_c_sequences_generate_expected_opn_constructs() -> None:
    result = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence=DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
        c_sequence=DEFAULT_OPN_TARGET_SEQUENCE,
    )

    assert result.errors == []
    by_type = {row["construct_type"]: row for row in result.rows}
    assert by_type["AC"]["c_length"] == 298
    assert by_type["AC"]["construct_length"] == 304
    assert by_type["ABC"]["b_length"] == 66
    assert by_type["ABC"]["construct_length"] == 370
    assert by_type["ABC"]["b_c_junction"] == "VSLEKR|IPVKQA"

def test_hlf_target_preset_uses_mature_lactoferrin_sequence() -> None:
    preset = FUSION_TARGET_PRESETS["hlf"]

    assert len(DEFAULT_HLF_REFERENCE_SEQUENCE) == 710
    assert DEFAULT_HLF_REFERENCE_SEQUENCE.startswith("MKLVFLVLLFLGALGLCLA")
    assert preset.sequence == DEFAULT_HLF_TARGET_SEQUENCE
    assert preset.sequence == DEFAULT_HLF_REFERENCE_SEQUENCE[19:]
    assert preset.sequence.startswith("GRRRSV")
    assert not preset.sequence.startswith("MKLVFL")
    assert len(preset.sequence) == 691


def test_hlf_constructs_include_target_metadata() -> None:
    result = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence=DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
        c_sequence=DEFAULT_HLF_TARGET_SEQUENCE,
        target_key="hlf",
        target_label=FUSION_TARGET_PRESETS["hlf"].label,
        include_abc=False,
        include_controls=False,
    )

    assert result.errors == []
    row = result.rows[0]
    assert row["construct_id"].startswith("hlf__SP_A__AC__")
    assert row["target_key"] == "hlf"
    assert row["target_label"] == "hLF / 人乳铁蛋白"
    assert row["c_length"] == 691
    assert row["construct_length"] == 697


def test_positive_control_leader_generates_control_construct() -> None:
    result = build_fusion_constructs(
        [],
        b_sequence=DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
        c_sequence="QWERTY",
        include_ac=False,
        include_abc=False,
        positive_control_leader_sequence="MKAIL",
    )

    positive = next(row for row in result.rows if row["construct_type"] == "POSITIVE_CONTROL_C")
    assert positive["construct_sequence"] == "MKAILQWERTY"
    assert positive["overall_priority"] == "待外部定位"
    assert "ABC 未提供 B 序列" not in positive["processing_site_note"]
    c_only = next(row for row in result.rows if row["construct_type"] == "C_ONLY")
    assert "ABC 未提供 B 序列" not in c_only["processing_site_note"]


def test_import_localization_results_merges_by_construct_id() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
    ).rows
    ids = {(row["candidate_id"], row["construct_type"]): row["construct_id"] for row in constructs}
    deeploc_csv = (
        "construct_id,Localization,Probability\n"
        f"{ids[('SP_A', 'AC')]},Extracellular,0.91\n"
        f"{ids[('SP_A', 'ABC')]},Endoplasmic reticulum,0.72\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc", target_key="custom")

    assert imported.errors == []
    assert imported.imported_count == 2
    by_kind = {(row["candidate_id"], row["construct_type"]): row for row in imported.rows}
    assert by_kind[("SP_A", "AC")]["deeploc_localization"] == "Extracellular"
    assert by_kind[("SP_A", "ABC")]["deeploc_score"] == "0.72"
    assert summarize_localization(by_kind[("SP_A", "AC")])["external_secreted_signal"] is True
    assert summarize_localization(by_kind[("SP_A", "ABC")])["external_er_golgi_signal"] is True


def test_localization_import_rejects_wrong_target_and_legacy_constructs() -> None:
    opn_constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        target_key="opn",
        include_abc=False,
        include_controls=False,
    ).rows
    hlf_constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        target_key="hlf",
        include_abc=False,
        include_controls=False,
    ).rows
    opn_id = str(opn_constructs[0]["construct_id"])
    result_csv = f"construct_id,Localization\n{opn_id},Extracellular\n"

    wrong_target = import_localization_results(
        hlf_constructs,
        result_csv,
        tool_name="deeploc",
        target_key="hlf",
    )
    legacy = import_localization_results(
        [{"construct_id": "SP_A_AC", "target_key": "opn", "construct_sequence": "MKAALLQWERTY"}],
        "construct_id,Localization\nSP_A_AC,Extracellular\n",
        tool_name="deeploc",
        target_key="opn",
    )

    assert wrong_target.imported_count == 0
    assert any("目标" in error and "重新生成" in error for error in wrong_target.errors)
    assert legacy.imported_count == 0
    assert any("旧版" in error and "重新生成" in error for error in legacy.errors)


def test_target_manifest_restores_constructs_after_session_loss(tmp_path) -> None:
    rows = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        target_key="hlf",
        include_abc=False,
        include_controls=False,
    ).rows

    path = save_fusion_construct_manifest(rows, tmp_path, "hlf")
    restored = load_fusion_construct_manifest(tmp_path, "hlf")

    assert path == tmp_path / "fusion_constructs_hlf.csv"
    assert restored.errors == []
    assert restored.rows[0]["construct_id"] == rows[0]["construct_id"]
    assert restored.rows[0]["construct_sequence_sha1"] == rows[0]["construct_sequence_sha1"]


def test_import_localization_results_reads_deeploc_flattened_fasta_header() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("PICHIA_UNIPROT_O74702", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
    ).rows
    ids = {(row["candidate_id"], row["construct_type"]): row["construct_id"] for row in constructs}
    deeploc_csv = (
        "Protein_ID,Localizations,Signals,Membrane types,Extracellular\n"
        f"{ids[('PICHIA_UNIPROT_O74702', 'AC')]}_source_PICHIA_UNIPROT_O74702_type_AC_len_314,Extracellular,Signal peptide,Soluble,0.92\n"
        f"{ids[('PICHIA_UNIPROT_O74702', 'ABC')]}_source_PICHIA_UNIPROT_O74702_type_ABC_len_380,Endoplasmic reticulum,Signal peptide,Soluble,0.71\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc", target_key="custom")

    assert imported.errors == []
    assert imported.imported_count == 2
    by_kind = {(row["candidate_id"], row["construct_type"]): row for row in imported.rows}
    ac = by_kind[("PICHIA_UNIPROT_O74702", "AC")]
    abc = by_kind[("PICHIA_UNIPROT_O74702", "ABC")]
    assert ac["deeploc_localization"] == "Extracellular"
    assert abc["deeploc_score"] == "0.71"
    assert summarize_localization(ac)["external_membrane_risk"] is False
    assert summarize_localization(ac)["external_vacuole_risk"] is False
    assert ac["localization_probability_score"] > 70
    assert ac["fine_priority_score"] > 0


def test_deeploc_risk_uses_probabilities_not_column_names() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        include_abc=False,
    ).rows
    construct_id = next(row["construct_id"] for row in constructs if row["construct_type"] == "AC")
    deeploc_csv = (
        "Protein_ID,Localizations,Membrane types,Extracellular,Cell membrane,Lysosome/Vacuole,Transmembrane,Lipid anchor\n"
        f"{construct_id},Extracellular,Soluble,0.95,0.08,0.04,0.02,0.03\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc", target_key="custom")

    summary = summarize_localization(next(row for row in imported.rows if row["construct_type"] == "AC"))
    assert summary["external_secreted_signal"] is True
    assert summary["external_membrane_risk"] is False
    assert summary["external_vacuole_risk"] is False


def test_cached_false_strings_do_not_create_design_risk() -> None:
    row = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence=DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
        c_sequence="QWERTY",
        include_ac=False,
        include_controls=False,
    ).rows[0]
    row.update(
        {
            "has_er_retention_motif": "False",
            "has_vacuolar_sorting_motif": "False",
            "gpi_anchor_like_risk": "False",
            "b_pre_region_like": "False",
            "b_ends_with_kex2_site": "True",
            "deeploc_localization": "Extracellular",
            "deeploc_extracellular": "0.92",
            "deeploc_soluble": "0.91",
            "deeploc_cell_membrane": "0.32",
            "deeploc_transmembrane": "0.03",
            "deeploc_lipid_anchor": "0.28",
            "deeploc_lysosome_vacuole": "0.10",
        }
    )

    scored = score_construct(row)

    assert scored["processing_quality"] == 80
    assert scored["membrane_or_vacuole_risk"] == 0
    assert scored["overall_score"] > 60


def test_deeploc_official_thresholds_are_used_for_risk_flags() -> None:
    below = {
        "deeploc_localization": "Extracellular",
        "deeploc_extracellular": "0.6172",
        "deeploc_cell_membrane": "0.5645",
        "deeploc_transmembrane": "0.5099",
        "deeploc_lipid_anchor": "0.8199",
        "deeploc_lysosome_vacuole": "0.5847",
    }
    above = {
        "deeploc_localization": "",
        "deeploc_extracellular": "0.6173",
        "deeploc_cell_membrane": "0.5646",
        "deeploc_transmembrane": "0.51",
        "deeploc_lipid_anchor": "0.82",
        "deeploc_lysosome_vacuole": "0.5848",
    }

    assert summarize_localization(below)["external_membrane_risk"] is False
    assert summarize_localization(below)["external_vacuole_risk"] is False
    assert summarize_localization(above)["external_secreted_signal"] is True
    assert summarize_localization(above)["external_membrane_risk"] is True
    assert summarize_localization(above)["external_vacuole_risk"] is True


def test_fine_priority_score_uses_deeploc_probability_tie_breakers() -> None:
    constructs = build_fusion_constructs(
        [
            _signal_row("SP_GOOD", "MKAALL"),
            _signal_row("SP_WEAK", "MKAALL"),
        ],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        include_abc=False,
        include_controls=False,
    ).rows
    ids = {row["candidate_id"]: row["construct_id"] for row in constructs}
    deeploc_csv = (
        "Protein_ID,Localizations,Membrane types,Extracellular,Soluble,Cell membrane,Lysosome/Vacuole,Transmembrane,Lipid anchor\n"
        f"{ids['SP_GOOD']},Extracellular,Soluble,0.96,0.94,0.04,0.03,0.02,0.02\n"
        f"{ids['SP_WEAK']},Extracellular,Soluble,0.58,0.52,0.42,0.22,0.18,0.12\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc", target_key="custom")

    by_candidate = {row["candidate_id"]: row for row in imported.rows}
    assert by_candidate["SP_GOOD"]["fine_priority_score"] > by_candidate["SP_WEAK"]["fine_priority_score"]
    assert by_candidate["SP_GOOD"]["localization_probability_score"] > by_candidate["SP_WEAK"]["localization_probability_score"]


def test_import_localization_results_reads_tsv_and_busca_prediction() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        include_ac=False,
    ).rows
    construct_id = next(row["construct_id"] for row in constructs if row["construct_type"] == "ABC")
    busca_tsv = f"Sequence Name\tPrediction\tReliability\n{construct_id}\tPlasma membrane\tHigh\n"

    imported = import_localization_results(constructs, busca_tsv, tool_name="busca", target_key="custom")

    assert imported.imported_count == 1
    abc = next(row for row in imported.rows if row["construct_type"] == "ABC")
    assert abc["busca_localization"] == "Plasma membrane"
    assert summarize_localization(abc)["external_membrane_risk"] is True
    assert abc["overall_priority"] == "低"


def _signal_row(candidate_id: str, sequence: str) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "signal_peptide_sequence": sequence,
        "accession": "P12345",
        "protein_name": "Fixture protein",
        "rules_score": 95,
        "rules_n_region_positive_count": 1,
        "rules_h_region_max_hydrophobicity": 2.6,
        "rules_c_region_small_neutral": True,
        "uspnet_prediction": "SP",
        "uspnet_cleavage_sequence": sequence,
        "screening_status": "多方法一致通过",
        "source_protein_route": "分泌/胞外倾向",
        "source_protein_evidence_level": "自动/预测证据",
        "similar_group_size": 1,
    }
