from __future__ import annotations

from sigscout.core.coercion import safe_int_from_float


SIMILARITY_IDENTITY_THRESHOLD = 0.80


def cluster_similar_signal_peptides(
    rows: list[dict[str, object]],
    identity_threshold: float = SIMILARITY_IDENTITY_THRESHOLD,
) -> list[dict[str, object]]:
    groups: list[list[dict[str, object]]] = []
    seen_exact_sequences: set[str] = set()
    for row in rows:
        sequence = str(row.get("signal_peptide_sequence", "")).strip().upper()
        row_copy = dict(row)
        if sequence and sequence in seen_exact_sequences:
            groups.append([row_copy])
            continue
        placed = False
        for group in groups:
            if any(
                _is_similar_but_not_identical(sequence, str(member.get("signal_peptide_sequence", "")), identity_threshold)
                for member in group
            ):
                group.append(row_copy)
                placed = True
                break
        if not placed:
            groups.append([row_copy])
        if sequence:
            seen_exact_sequences.add(sequence)

    clustered_rows: list[dict[str, object]] = []
    for index, group in enumerate(groups, start=1):
        representative = choose_representative(group)
        representative_id = str(representative.get("candidate_id", ""))
        group_id = f"SPG_{index:03d}"
        for row in group:
            similarity = signal_peptide_identity(
                str(row.get("signal_peptide_sequence", "")),
                str(representative.get("signal_peptide_sequence", "")),
            )
            clustered_rows.append(
                {
                    **row,
                    "similarity_group_id": group_id,
                    "is_representative": str(row.get("candidate_id", "")) == representative_id,
                    "representative_id": representative_id,
                    "similarity_to_representative": round(similarity, 3),
                    "similar_group_size": len(group),
                }
            )
    return clustered_rows


def choose_representative(group_rows: list[dict[str, object]]) -> dict[str, object]:
    if not group_rows:
        return {}
    return sorted(group_rows, key=_representative_sort_key)[0]


def signal_peptide_identity(seq_a: str, seq_b: str) -> float:
    a = seq_a.strip().upper()
    b = seq_b.strip().upper()
    if not a or not b:
        return 0.0
    distance = _levenshtein_distance(a, b)
    return max(0.0, 1.0 - (distance / max(len(a), len(b))))


def _is_similar_but_not_identical(seq_a: str, seq_b: str, identity_threshold: float) -> bool:
    if not seq_a or not seq_b or seq_a.strip().upper() == seq_b.strip().upper():
        return False
    return signal_peptide_identity(seq_a, seq_b) >= identity_threshold


def _representative_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    return (
        not bool(row.get("consensus_pass")),
        not _uspnet_supports_signal_peptide(row),
        not bool(row.get("rules_high_priority")),
        -safe_int_from_float(row.get("rules_score")),
        not _reviewed_or_strong_evidence(row),
        len(str(row.get("signal_peptide_sequence", ""))),
        str(row.get("candidate_id", "")),
    )


def _uspnet_supports_signal_peptide(row: dict[str, object]) -> bool:
    return bool(row.get("uspnet_pass")) or str(row.get("uspnet_prediction", "")).strip().upper() == "SP"


def _reviewed_or_strong_evidence(row: dict[str, object]) -> bool:
    if bool(row.get("uniprot_reviewed")):
        return True
    text = " ".join(
        str(row.get(key, ""))
        for key in ("source_note", "rationale", "protein_existence", "evidence_level")
    ).lower()
    return "reviewed" in text or "evidence at protein level" in text


def _levenshtein_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for index_a, char_a in enumerate(a, start=1):
        current = [index_a]
        for index_b, char_b in enumerate(b, start=1):
            substitution = previous[index_b - 1] + (0 if char_a == char_b else 1)
            insertion = current[index_b - 1] + 1
            deletion = previous[index_b] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]
