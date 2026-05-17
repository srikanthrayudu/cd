from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class SummaryReport:
    totals: Dict[str, int]
    diff_reasons: Dict[str, int]
    sample_diffs: List[dict]
    notes: List[str]
    size_comparisons: List[dict]



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


def _load_json(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    output: Dict[str, int] = {}
    for key in ("generated", "mutated", "valid", "invalid"):
        value = payload.get(key)
        if isinstance(value, int):
            output[key] = value
    return output


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
    manifest = _load_json(results_dir / "run_manifest.json")

    totals: Dict[str, int] = {
        "executions": len(executions),
        "diffs": len(diffs),
        "skipped_exec": len(skipped),
    }
    totals.update({k: v for k, v in manifest.items() if k in {"generated", "mutated", "valid", "invalid"}})
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
        required_tools = ("llvm-as", "opt", "lli", "clang")
        optional_tools = ("alive-tv",)
        missing_tools = [tool for tool in required_tools if shutil.which(tool) is None]
        if missing_tools:
            notes.append(
                "Some executions were skipped due to missing tools: "
                + ", ".join(missing_tools)
                + ". Required LLVM tools: "
                + ", ".join(required_tools)
                + ". Optional: "
                + ", ".join(optional_tools)
                + "."
            )
        else:
            notes.append(
                "Some executions were skipped (likely unsupported architectures). Required LLVM tools: "
                + ", ".join(required_tools)
                + ". Optional: "
                + ", ".join(optional_tools)
                + "."
            )

    # Compile paired binary size comparisons (-O0 vs -O3)
    o0_sizes = {row["name"]: int(row["binary_size"]) for row in executions if row.get("mode") == "O0" and row.get("binary_size") is not None and row.get("name")}
    o3_sizes = {row["name"]: int(row["binary_size"]) for row in executions if row.get("mode") == "O3" and row.get("binary_size") is not None and row.get("name")}

    size_comparisons = []
    for name in sorted(o0_sizes.keys()):
        if name in o3_sizes:
            o0_sz = o0_sizes[name]
            o3_sz = o3_sizes[name]
            savings = o0_sz - o3_sz
            pct = (savings / o0_sz) * 100 if o0_sz > 0 else 0.0
            size_comparisons.append({
                "name": name,
                "o0_size": o0_sz,
                "o3_size": o3_sz,
                "savings": savings,
                "reduction_pct": pct,
                "direction": "smaller" if savings >= 0 else "larger",
            })

    return SummaryReport(totals, diff_reasons, sample_diffs, notes, size_comparisons)



def write_summary(report: SummaryReport, output_path: Path) -> None:
    lines = ["# Pipeline Summary", ""]
    if report.size_comparisons:
        total_o0 = sum(item["o0_size"] for item in report.size_comparisons)
        total_o3 = sum(item["o3_size"] for item in report.size_comparisons)
        total_savings = sum(item["savings"] for item in report.size_comparisons)
        reduction_pct = (total_savings / total_o0 * 100) if total_o0 else 0.0
        positive = sum(1 for item in report.size_comparisons if item["savings"] >= 0)
        lines.append("## Executive Overview")
        lines.append(f"- Paired comparisons: {len(report.size_comparisons)}")
        lines.append(f"- Aggregate -O0 size: {total_o0:,} bytes")
        lines.append(f"- Aggregate -O3 size: {total_o3:,} bytes")
        lines.append(f"- Net savings: {total_savings:,} bytes ({reduction_pct:.2f}% reduction)")
        lines.append(f"- Positive savings cases: {positive}/{len(report.size_comparisons)}")
        lines.append("")

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
    lines.append("")
    lines.append("## Paired Binary Size Comparisons (-O0 vs -O3)")
    if getattr(report, "size_comparisons", None):
        lines.append("| Program | -O0 Size (bytes) | -O3 Size (bytes) | Savings (bytes) | Reduction (%) | Direction |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for item in report.size_comparisons:
            name = item["name"]
            o0_sz = f"{item['o0_size']:,}"
            o3_sz = f"{item['o3_size']:,}"
            savings = f"{item['savings']:,}"
            pct = f"{item['reduction_pct']:.2f}%"
            lines.append(f"| {name} | {o0_sz} | {o3_sz} | {savings} | {pct} | {item['direction']} |")
    else:
        lines.append("- No successful paired -O0 vs -O3 compilation results found.")
    if report.notes:
        lines.append("")
        lines.append("## Notes")
        for note in report.notes:
            lines.append(f"- {note}")
    output_path.write_text("\n".join(lines) + "\n")
