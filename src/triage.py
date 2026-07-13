"""
triage.py — Failure triage report.

``build_triage`` aggregates diff records and groups them by failure reason
and by file name for quick triage.  ``write_triage`` writes the result as
a JSON file.

The input file name is read from ``cfg`` so it stays in sync with the
rest of the pipeline configuration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from src.config import cfg


@dataclass
class TriageReport:
    """Aggregated diff information for failure triage."""
    diffs_by_reason: Dict[str, int]
    diffs_by_name:   Dict[str, int]
    samples:         List[dict]


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _count_by_key(rows: List[dict], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_triage(results_dir: Path, sample_limit: int = 10) -> TriageReport:
    """
    Read the diffs log and produce a :class:`TriageReport`.

    Parameters
    ----------
    results_dir:  directory containing the ``diffs.jsonl`` file
    sample_limit: maximum number of raw diff records to include as samples
    """
    diffs_file = cfg.reporting.files["diffs"]
    diffs      = _load_jsonl(results_dir / diffs_file)

    return TriageReport(
        diffs_by_reason = _count_by_key(diffs, "reason"),
        diffs_by_name   = _count_by_key(diffs, "name"),
        samples         = diffs[:sample_limit],
    )


def write_triage(report: TriageReport, output_path: Path) -> None:
    """Write *report* as a pretty-printed JSON file."""
    payload = {
        "diffs_by_reason": report.diffs_by_reason,
        "diffs_by_name":   report.diffs_by_name,
        "samples":         report.samples,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
