from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class TriageReport:
    diffs_by_reason: Dict[str, int]
    diffs_by_name: Dict[str, int]
    samples: List[dict]


def _load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows: List[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _count_by_key(rows: List[dict], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_triage(results_dir: Path, sample_limit: int = 10) -> TriageReport:
    diffs = _load_jsonl(results_dir / "diffs.jsonl")
    diffs_by_reason = _count_by_key(diffs, "reason")
    diffs_by_name = _count_by_key(diffs, "name")
    samples = diffs[:sample_limit]
    return TriageReport(diffs_by_reason, diffs_by_name, samples)


def write_triage(report: TriageReport, output_path: Path) -> None:
    payload = {
        "diffs_by_reason": report.diffs_by_reason,
        "diffs_by_name": report.diffs_by_name,
        "samples": report.samples,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n")

