from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class SummaryReport:
    totals: Dict[str, int]
    diff_reasons: Dict[str, int]
    sample_diffs: List[dict]
    notes: List[str]


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


def build_summary(results_dir: Path, evaluation_dir: Path) -> SummaryReport:
    executions = _load_jsonl(results_dir / "executions.jsonl")
    diffs = _load_jsonl(results_dir / "diffs.jsonl")
    skipped = _load_jsonl(results_dir / "skipped_exec.jsonl")
    metrics_path = evaluation_dir / "metrics.json"

    totals: Dict[str, int] = {
        "executions": len(executions),
        "diffs": len(diffs),
        "skipped_exec": len(skipped),
    }
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text())
            totals.update({f"metric_{k}": int(v) for k, v in metrics.items() if str(v).isdigit()})
        except json.JSONDecodeError:
            pass

    diff_reasons = _count_by_key(diffs, "reason")
    sample_diffs = diffs[:5]
    notes = []
    if not executions:
        notes.append("No executions recorded. Ensure LLVM tools are installed or rerun the pipeline.")
    if skipped:
        notes.append("Some executions were skipped (likely missing LLVM tools).")

    return SummaryReport(totals, diff_reasons, sample_diffs, notes)


def write_summary(report: SummaryReport, output_path: Path) -> None:
    lines = ["# Pipeline Summary", ""]
    lines.append("## Totals")
    for key in sorted(report.totals.keys()):
        lines.append(f"- {key}: {report.totals[key]}")
    lines.append("")
    lines.append("## Diff Reasons")
    if report.diff_reasons:
        for key, value in sorted(report.diff_reasons.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Sample Diffs")
    if report.sample_diffs:
        for row in report.sample_diffs:
            name = row.get("name", "unknown")
            reason = row.get("reason", "unknown")
            lines.append(f"- {name}: {reason}")
    else:
        lines.append("- None")
    if report.notes:
        lines.append("")
        lines.append("## Notes")
        for note in report.notes:
            lines.append(f"- {note}")
    output_path.write_text("\n".join(lines) + "\n")

