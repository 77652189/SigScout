from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
    lines: list[str] = []
    for header, sequence in records:
        lines.append(f">{header}")
        for index in range(0, len(sequence), 80):
            lines.append(sequence[index : index + 80])
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


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

