from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = (
    "experiment_id",
    "target_key",
    "target_variant",
    "batch_id",
    "signal_peptide_id",
    "construct_name",
    "yield_value",
    "yield_unit",
    "strain_background",
    "integration_locus",
)
OPTIONAL_COLUMNS = (
    "source_construct_name",
    "measurement_status",
    "signal_peptide_sequence",
    "signal_peptide_nucleotide_sequence",
    "target_protein_sequence",
    "target_nucleotide_sequence",
    "promoter",
    "copy_number",
    "construct_variant",
    "is_reference_baseline",
    "reference_basis",
    "measurement_method",
    "biological_replicates",
    "notes",
)
TEMPLATE_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
MEASURED = "measured"
RESULT_MISSING = "result_missing"


@dataclass(frozen=True)
class ExperimentalFeedbackResult:
    rows: pd.DataFrame
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


def experimental_feedback_template() -> str:
    return pd.DataFrame(columns=TEMPLATE_COLUMNS).to_csv(index=False)


def load_experimental_feedback(path: Path, target_key: str | None = None) -> ExperimentalFeedbackResult:
    if not path.exists():
        return ExperimentalFeedbackResult(pd.DataFrame(columns=TEMPLATE_COLUMNS))
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:
        return ExperimentalFeedbackResult(pd.DataFrame(), errors=(f"无法读取实验反馈文件：{exc}",))
    return prepare_experimental_feedback(frame, target_key=target_key)


def parse_experimental_feedback_csv(data: bytes, target_key: str | None = None) -> ExperimentalFeedbackResult:
    try:
        frame = pd.read_csv(StringIO(data.decode("utf-8-sig")), dtype=str, keep_default_na=False)
    except Exception as exc:
        return ExperimentalFeedbackResult(pd.DataFrame(), errors=(f"无法解析 CSV：{exc}",))
    return prepare_experimental_feedback(frame, target_key=target_key)


def prepare_experimental_feedback(
    frame: pd.DataFrame, target_key: str | None = None
) -> ExperimentalFeedbackResult:
    rows = frame.copy()
    missing = [column for column in REQUIRED_COLUMNS if column not in rows.columns]
    if missing:
        return ExperimentalFeedbackResult(rows, errors=(f"缺少必要列：{', '.join(missing)}",))

    rows = _migrate_legacy_columns(rows)
    for column in OPTIONAL_COLUMNS:
        if column not in rows.columns:
            rows[column] = ""
    rows = rows.loc[:, list(TEMPLATE_COLUMNS)].copy()
    for column in rows.columns:
        rows[column] = rows[column].astype(str).str.strip()

    errors: list[str] = []
    warnings: list[str] = []
    if rows["experiment_id"].eq("").any():
        errors.append("experiment_id 不能为空。")
    duplicate_ids = rows.loc[rows["experiment_id"].duplicated(keep=False), "experiment_id"].unique()
    if len(duplicate_ids):
        errors.append(f"experiment_id 重复：{', '.join(duplicate_ids)}")

    valid_statuses = {MEASURED, RESULT_MISSING}
    invalid_statuses = sorted(set(rows["measurement_status"]) - valid_statuses)
    if invalid_statuses:
        errors.append(f"measurement_status 仅支持 measured/result_missing：{', '.join(invalid_statuses)}")

    rows["yield_ug_l"] = [
        _measurement_to_ug_l(status, value, unit, experiment_id, errors)
        for status, value, unit, experiment_id in zip(
            rows["measurement_status"],
            rows["yield_value"],
            rows["yield_unit"],
            rows["experiment_id"],
            strict=False,
        )
    ]
    rows["is_reference_baseline"] = rows["is_reference_baseline"].str.lower().isin(
        {"1", "true", "yes", "y", "是"}
    )

    normalized_target = (target_key or "").strip().lower()
    if normalized_target:
        unexpected = sorted(
            set(rows.loc[rows["target_key"].str.lower() != normalized_target, "target_key"]) - {""}
        )
        if unexpected:
            errors.append(f"当前目标为 {normalized_target}，文件中还包含：{', '.join(unexpected)}")
        rows = rows.loc[rows["target_key"].str.lower() == normalized_target].copy()

    measured = rows["measurement_status"].eq(MEASURED)
    if measured.any() and rows.loc[measured, "biological_replicates"].eq("").all():
        warnings.append("报告未提供生物学重复数和误差，当前只能比较报告值，不能估计显著性。")
    if rows["measurement_status"].eq(RESULT_MISSING).any():
        warnings.append("存在报告提及但未给出产量的构建；这些记录仅用于追溯，不参与排名。")
    context_counts = rows.groupby("batch_id", dropna=False)[
        ["strain_background", "integration_locus", "target_variant"]
    ].nunique()
    if (context_counts > 1).any(axis=None):
        warnings.append("同一 batch_id 内存在不同宿主、位点或目标版本，批内排名可能混杂。")
    if rows["batch_id"].nunique() > 1:
        warnings.append("不同轮次的宿主、整合位点或目标蛋白版本不同；跨轮次绝对产量不能归因于信号肽。")
    return ExperimentalFeedbackResult(_add_batch_metrics(rows), tuple(errors), tuple(warnings))


def save_experimental_feedback(rows: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, list(TEMPLATE_COLUMNS)].to_csv(path, index=False, encoding="utf-8-sig")


def summarize_experimental_feedback(rows: pd.DataFrame) -> dict[str, object]:
    if rows.empty:
        return {
            "records": 0,
            "measurements": 0,
            "missing_results": 0,
            "batches": 0,
            "signal_peptides": 0,
            "best_batch_winners": 0,
        }
    measured = rows["measurement_status"].eq(MEASURED)
    return {
        "records": len(rows),
        "measurements": int(measured.sum()),
        "missing_results": int(rows["measurement_status"].eq(RESULT_MISSING).sum()),
        "batches": rows["batch_id"].nunique(),
        "signal_peptides": rows["signal_peptide_id"].nunique(),
        "best_batch_winners": int(rows.loc[measured, "batch_rank"].eq(1).sum()),
    }


def _migrate_legacy_columns(rows: pd.DataFrame) -> pd.DataFrame:
    migrated = rows.copy()
    if "source_construct_name" not in migrated.columns:
        migrated["source_construct_name"] = migrated["construct_name"]
    if "measurement_status" not in migrated.columns:
        migrated["measurement_status"] = migrated["yield_value"].astype(str).str.strip().map(
            lambda value: MEASURED if value else RESULT_MISSING
        )
    if "is_reference_baseline" not in migrated.columns:
        legacy = migrated.get("is_batch_control", pd.Series("", index=migrated.index))
        migrated["is_reference_baseline"] = legacy
    if "reference_basis" not in migrated.columns:
        migrated["reference_basis"] = ""
        legacy_true = migrated["is_reference_baseline"].astype(str).str.lower().isin(
            {"1", "true", "yes", "y", "是"}
        )
        migrated.loc[legacy_true, "reference_basis"] = "由旧 is_batch_control 字段迁移，需人工确认"
    return migrated


def _measurement_to_ug_l(
    status: str, value: str, unit: str, experiment_id: str, errors: list[str]
) -> float:
    if status == RESULT_MISSING:
        if value or unit:
            errors.append(f"{experiment_id or '未知记录'} 标记为 result_missing 时产量和单位必须留空。")
        return float("nan")
    if status != MEASURED:
        return float("nan")
    if not value or not unit:
        errors.append(f"{experiment_id or '未知记录'} 标记为 measured 时必须填写产量和单位。")
        return float("nan")
    return _to_ug_l(value, unit, experiment_id, errors)


def _to_ug_l(value: str, unit: str, experiment_id: str, errors: list[str]) -> float:
    try:
        numeric = float(value)
    except ValueError:
        errors.append(f"{experiment_id or '未知记录'} 的 yield_value 不是数字：{value}")
        return float("nan")
    normalized = unit.lower().replace("μ", "u").replace("µ", "u").replace(" ", "")
    factors = {"ug/l": 1.0, "mg/l": 1000.0, "ng/ml": 1.0, "mg/ml": 1_000_000.0}
    if normalized not in factors:
        errors.append(f"{experiment_id or '未知记录'} 使用了不支持的单位：{unit}")
        return float("nan")
    return numeric * factors[normalized]


def _add_batch_metrics(rows: pd.DataFrame) -> pd.DataFrame:
    rows["batch_rank"] = pd.Series(pd.NA, index=rows.index, dtype="Int64")
    rows["batch_relative_to_best"] = float("nan")
    rows["batch_fold_vs_reference"] = float("nan")
    if rows.empty:
        return rows

    measured = rows["measurement_status"].eq(MEASURED) & rows["yield_ug_l"].notna()
    measured_rows = rows.loc[measured]
    ranks = measured_rows.groupby("batch_id")["yield_ug_l"].rank(method="min", ascending=False)
    rows.loc[measured, "batch_rank"] = ranks.astype("Int64")
    batch_best = measured_rows.groupby("batch_id")["yield_ug_l"].transform("max")
    rows.loc[measured, "batch_relative_to_best"] = measured_rows["yield_ug_l"] / batch_best

    references = (
        measured_rows.loc[measured_rows["is_reference_baseline"]]
        .groupby("batch_id")["yield_ug_l"]
        .first()
        .to_dict()
    )
    rows.loc[measured, "batch_fold_vs_reference"] = [
        value / references[batch] if batch in references and references[batch] > 0 else float("nan")
        for batch, value in zip(
            measured_rows["batch_id"], measured_rows["yield_ug_l"], strict=False
        )
    ]
    return rows
