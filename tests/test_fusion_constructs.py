from __future__ import annotations

from sigscout.services.fusion_constructs import (
    DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
    DEFAULT_OPN_TARGET_SEQUENCE,
    build_fusion_constructs,
    fusion_constructs_to_fasta,
    import_localization_results,
    score_construct,
    summarize_localization,
)


def test_build_fusion_constructs_exports_ac_and_abc() -> None:
    result = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
    )

    assert result.errors == []
    by_id = {row["construct_id"]: row for row in result.rows}
    assert set(by_id) == {"CONTROL_C_ONLY", "CONTROL_BC", "SP_A_AC", "SP_A_ABC"}
    assert by_id["CONTROL_C_ONLY"]["construct_sequence"] == "QWERTY"
    assert by_id["SP_A_AC"]["construct_sequence"] == "MKAALLQWERTY"
    assert by_id["SP_A_ABC"]["construct_sequence"] == "MKAALLEAEAQWERTY"
    assert by_id["SP_A_ABC"]["b_length"] == 4
    assert by_id["SP_A_AC"]["overall_priority"] == "待外部定位"

    fasta = fusion_constructs_to_fasta(result.rows)

    assert ">SP_A_AC|source=SP_A|type=AC|len=12" in fasta
    assert "MKAALLEAEAQWERTY" in fasta


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
    row = {row["construct_id"]: row for row in result.rows}["SP_A_ABC"]
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


def test_positive_control_leader_generates_control_construct() -> None:
    result = build_fusion_constructs(
        [],
        b_sequence=DEFAULT_ALPHA_FACTOR_PRO_SEQUENCE,
        c_sequence="QWERTY",
        include_ac=False,
        include_abc=False,
        positive_control_leader_sequence="MKAIL",
    )

    by_id = {row["construct_id"]: row for row in result.rows}
    assert "CONTROL_POSITIVE_CONTROL_C" in by_id
    assert by_id["CONTROL_POSITIVE_CONTROL_C"]["construct_sequence"] == "MKAILQWERTY"
    assert by_id["CONTROL_POSITIVE_CONTROL_C"]["overall_priority"] == "待外部定位"


def test_import_localization_results_merges_by_construct_id() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
    ).rows
    deeploc_csv = (
        "construct_id,Localization,Probability\n"
        "SP_A_AC,Extracellular,0.91\n"
        "SP_A_ABC,Endoplasmic reticulum,0.72\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc")

    assert imported.errors == []
    assert imported.imported_count == 2
    by_id = {row["construct_id"]: row for row in imported.rows}
    assert by_id["SP_A_AC"]["deeploc_localization"] == "Extracellular"
    assert by_id["SP_A_ABC"]["deeploc_score"] == "0.72"
    assert summarize_localization(by_id["SP_A_AC"])["external_secreted_signal"] is True
    assert summarize_localization(by_id["SP_A_ABC"])["external_er_golgi_signal"] is True


def test_import_localization_results_reads_deeploc_flattened_fasta_header() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("PICHIA_UNIPROT_O74702", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
    ).rows
    deeploc_csv = (
        "Protein_ID,Localizations,Signals,Membrane types,Extracellular\n"
        "PICHIA_UNIPROT_O74702_AC_source_PICHIA_UNIPROT_O74702_type_AC_len_314,Extracellular,Signal peptide,Soluble,0.92\n"
        "PICHIA_UNIPROT_O74702_ABC_source_PICHIA_UNIPROT_O74702_type_ABC_len_380,Endoplasmic reticulum,Signal peptide,Soluble,0.71\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc")

    assert imported.errors == []
    assert imported.imported_count == 2
    by_id = {row["construct_id"]: row for row in imported.rows}
    assert by_id["PICHIA_UNIPROT_O74702_AC"]["deeploc_localization"] == "Extracellular"
    assert by_id["PICHIA_UNIPROT_O74702_ABC"]["deeploc_score"] == "0.71"
    assert summarize_localization(by_id["PICHIA_UNIPROT_O74702_AC"])["external_membrane_risk"] is False
    assert summarize_localization(by_id["PICHIA_UNIPROT_O74702_AC"])["external_vacuole_risk"] is False
    assert by_id["PICHIA_UNIPROT_O74702_AC"]["localization_probability_score"] > 70
    assert by_id["PICHIA_UNIPROT_O74702_AC"]["fine_priority_score"] > 0


def test_deeploc_risk_uses_probabilities_not_column_names() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        include_abc=False,
    ).rows
    deeploc_csv = (
        "Protein_ID,Localizations,Membrane types,Extracellular,Cell membrane,Lysosome/Vacuole,Transmembrane,Lipid anchor\n"
        "SP_A_AC,Extracellular,Soluble,0.95,0.08,0.04,0.02,0.03\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc")

    by_id = {row["construct_id"]: row for row in imported.rows}
    summary = summarize_localization(by_id["SP_A_AC"])
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
    deeploc_csv = (
        "Protein_ID,Localizations,Membrane types,Extracellular,Soluble,Cell membrane,Lysosome/Vacuole,Transmembrane,Lipid anchor\n"
        "SP_GOOD_AC,Extracellular,Soluble,0.96,0.94,0.04,0.03,0.02,0.02\n"
        "SP_WEAK_AC,Extracellular,Soluble,0.58,0.52,0.42,0.22,0.18,0.12\n"
    )

    imported = import_localization_results(constructs, deeploc_csv, tool_name="deeploc")

    by_id = {row["construct_id"]: row for row in imported.rows}
    assert by_id["SP_GOOD_AC"]["fine_priority_score"] > by_id["SP_WEAK_AC"]["fine_priority_score"]
    assert by_id["SP_GOOD_AC"]["localization_probability_score"] > by_id["SP_WEAK_AC"]["localization_probability_score"]


def test_import_localization_results_reads_tsv_and_busca_prediction() -> None:
    constructs = build_fusion_constructs(
        [_signal_row("SP_A", "MKAALL")],
        b_sequence="EAEA",
        c_sequence="QWERTY",
        include_ac=False,
    ).rows
    busca_tsv = "Sequence Name\tPrediction\tReliability\nSP_A_ABC\tPlasma membrane\tHigh\n"

    imported = import_localization_results(constructs, busca_tsv, tool_name="busca")

    assert imported.imported_count == 1
    by_id = {row["construct_id"]: row for row in imported.rows}
    assert by_id["SP_A_ABC"]["busca_localization"] == "Plasma membrane"
    assert summarize_localization(by_id["SP_A_ABC"])["external_membrane_risk"] is True
    assert by_id["SP_A_ABC"]["overall_priority"] == "低"


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
