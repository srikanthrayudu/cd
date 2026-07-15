"""
triage.py — Failure triage report.

``build_triage`` aggregates diff records and groups them by failure reason,
file name, and mutation strategy for quick triage.
``write_triage`` writes the result as a JSON file.

The input file names are read from ``cfg`` so they stay in sync with
the rest of the pipeline configuration.
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
    diffs_by_reason:   Dict[str, int]
    diffs_by_name:     Dict[str, int]
    diffs_by_strategy: Dict[str, int]   # strategy → number of diffs it contributed to
    samples:           List[dict]


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


def _build_strategy_counts(
    diff_rows:    List[dict],
    mutation_log: Path,
) -> Dict[str, int]:
    """
    Cross-reference diff names with the mutation audit log to count how many
    diffs each strategy contributed to.

    Each strategy is counted once per diffing file it was applied to —
    not per strategy application — so the numbers reflect distinct
    failures, not total applications.
    """
    if not mutation_log.exists():
        return {}

    # Build stem → strategies mapping from the mutation log
    stem_to_strategies: Dict[str, List[str]] = {}
    for line in mutation_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        output = entry.get("output", "")
        stem   = Path(output).stem if output else ""
        strats = entry.get("strategies", [])
        if stem and isinstance(strats, list):
            stem_to_strategies[stem] = strats

    # Count strategies that appeared in diffing files
    diff_stems = {str(row.get("name", "")) for row in diff_rows}
    counts: Dict[str, int] = {}
    for stem in diff_stems:
        for strategy in stem_to_strategies.get(stem, []):
            counts[strategy] = counts.get(strategy, 0) + 1

    return counts


def build_triage(results_dir: Path, sample_limit: int = 10) -> TriageReport:
    """
    Read the diffs log and optional mutation audit log, and produce a
    :class:`TriageReport`.

    Parameters
    ----------
    results_dir:  directory containing ``diffs.jsonl`` and optionally
                  ``mutation_log.jsonl``
    sample_limit: maximum number of raw diff records to include as samples
    """
    file_names = cfg.reporting.files
    diffs      = _load_jsonl(results_dir / file_names["diffs"])

    mutation_log     = results_dir / "mutation_log.jsonl"
    diffs_by_strategy = _build_strategy_counts(diffs, mutation_log)

    return TriageReport(
        diffs_by_reason   = _count_by_key(diffs, "reason"),
        diffs_by_name     = _count_by_key(diffs, "name"),
        diffs_by_strategy = diffs_by_strategy,
        samples           = diffs[:sample_limit],
    )


def write_triage(report: TriageReport, output_path: Path) -> None:
    """Write *report* as a pretty-printed JSON file."""
    payload = {
        "diffs_by_reason":   report.diffs_by_reason,
        "diffs_by_name":     report.diffs_by_name,
        "diffs_by_strategy": report.diffs_by_strategy,
        "samples":           report.samples,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
