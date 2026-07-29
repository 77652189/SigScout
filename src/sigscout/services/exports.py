from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Iterable


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write(_csv_body(rows, lineterminator="\r\n"))


def rows_to_csv(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""
    return _csv_body(rows, lineterminator="\n")


def _csv_body(rows: list[dict[str, object]], *, lineterminator: str) -> str:
    output = io.StringIO()
    fieldnames = _fieldnames(rows)
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator=lineterminator)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def write_candidate_fasta(path: Path, rows: Iterable[dict[str, object]]) -> None:
    records = []
    for row in rows:
        header = f"{row.get('candidate_id')}|accession={row.get('accession')}|source=UniProt"
        sequence = str(row.get("leader_sequence") or row.get("signal_peptide_sequence") or "")
        if sequence:
            records.append((header, sequence))
    write_fasta(path, records)


def write_signal_peptide_fasta(path: Path, rows: Iterable[dict[str, object]]) -> None:
    records = []
    for row in rows:
        header = f"{row.get('candidate_id')}|accession={row.get('accession')}|role={row.get('screening_status', '')}"
        sequence = str(row.get("signal_peptide_sequence", ""))
        if sequence:
            records.append((header, sequence))
    write_fasta(path, records)


def write_fasta(path: Path, records: Iterable[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(records_to_fasta(records), encoding="utf-8")


def records_to_fasta(records: Iterable[tuple[str, str]]) -> str:
    lines: list[str] = []
    for header, sequence in records:
        lines.append(f">{header}")
        for index in range(0, len(sequence), 80):
            lines.append(sequence[index : index + 80])
    return "\n".join(lines) + ("\n" if lines else "")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fieldnames(rows: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    return names

