from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from sigscout.services.fusion_scoring import score_construct


LOCALIZATION_ID_COLUMNS = (
    "construct_id",
    "id",
    "protein_id",
    "protein",
    "entry",
    "name",
    "sequence_name",
    "sequence id",
    "sequence name",
)
LOCALIZATION_COLUMNS = (
    "localization",
    "localizations",
    "location",
    "prediction",
    "predicted_location",
    "deeploc_location",
    "busca_prediction",
    "subcellular_location",
    "main location",
    "final localization",
)
LOCALIZATION_SCORE_COLUMNS = (
    "score",
    "probability",
    "confidence",
    "reliability",
    "extracellular",
    "extracellular_score",
    "secreted_score",
)


@dataclass(frozen=True)
class LocalizationImportResult:
    rows: list[dict[str, object]]
    errors: list[str]
    imported_count: int


def import_localization_results(
    construct_rows: list[dict[str, object]],
    content: bytes | str,
    *,
    tool_name: str,
) -> LocalizationImportResult:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else str(content)
    table, errors = _read_delimited_table(text)
    if errors:
        return LocalizationImportResult(construct_rows, errors, 0)
    indexed = {_normalize_id(row.get("construct_id", "")): dict(row) for row in construct_rows}
    imported = 0
    for row in table:
        construct_id = _extract_first(row, LOCALIZATION_ID_COLUMNS)
        key = _find_construct_key(construct_id, indexed)
        if not key:
            continue
        localization = _extract_first(row, LOCALIZATION_COLUMNS)
        score = _extract_first(row, LOCALIZATION_SCORE_COLUMNS)
        raw = {f"{tool_name}_{_safe_column_name(k)}": v for k, v in row.items() if str(v).strip()}
        indexed[key].update(
            {
                f"{tool_name}_localization": localization,
                f"{tool_name}_score": score,
                f"{tool_name}_raw": "; ".join(f"{k}={v}" for k, v in raw.items()),
                **raw,
            }
        )
        indexed[key].update(score_construct(indexed[key]))
        imported += 1
    merged = [indexed[_normalize_id(row.get("construct_id", ""))] for row in construct_rows]
    errors = [] if imported else [f"没有在 {tool_name} 结果中匹配到 construct_id。"]
    return LocalizationImportResult(merged, errors, imported)


def _read_delimited_table(text: str) -> tuple[list[dict[str, str]], list[str]]:
    if not text.strip():
        return [], ["导入文件为空。"]
    sample = text[:2048]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]
    except csv.Error as exc:
        return [], [f"定位结果读取失败：{exc}"]
    if not reader.fieldnames:
        return [], ["导入文件没有表头。"]
    return rows, []


def _extract_first(row: dict[str, str], candidates: tuple[str, ...]) -> str:
    normalized = {_safe_column_name(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalized.get(_safe_column_name(candidate), "")
        if str(value).strip():
            return str(value).strip()
    return ""


def _safe_column_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _normalize_id(value: object) -> str:
    return str(value or "").strip().split("|", 1)[0]


def _find_construct_key(value: object, indexed: dict[str, dict[str, object]]) -> str:
    for key in _localization_id_candidates(value):
        if key in indexed:
            return key
    return ""


def _localization_id_candidates(value: object) -> list[str]:
    normalized = _normalize_id(value)
    if not normalized:
        return []
    candidates = [normalized]
    flattened = re.split(r"_source_", normalized, maxsplit=1, flags=re.IGNORECASE)[0]
    if flattened and flattened not in candidates:
        candidates.append(flattened)
    return candidates
