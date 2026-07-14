"""
reporting.py — Summary report generation.

``build_summary``  — aggregate pipeline artefacts into a :class:`SummaryReport`.
``write_summary``  — render the report to a Markdown file.

All file names come from ``cfg`` (config.yaml → reporting.files).
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from src.config import cfg


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class SummaryReport:
    """All data needed to render a human-readable pipeline summary."""
    totals:              Dict[str, int]
    diff_reasons:        Dict[str, int]
    sample_diffs:        List[dict]
    notes:               List[str]
    size_comparisons:    List[dict]
    metrics_snapshot:    Dict[str, Any]
    run_metadata:        Dict[str, str]
    instr_stats:         Dict[str, Any]   = None   # type: ignore[assignment]
    strategy_diff_rates: Dict[str, float] = None   # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.instr_stats is None:
            self.instr_stats = {}
        if self.strategy_diff_rates is None:
            self.strategy_diff_rates = {}


# ---------------------------------------------------------------------------
# JSON / JSONL loading
# ---------------------------------------------------------------------------

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


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Internal aggregation helpers
# ---------------------------------------------------------------------------

def _count_by_key(rows: List[dict], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _collect_counts(manifest: dict) -> Dict[str, int]:
    """Extract generation/mutation/validation counts from a run manifest."""
    for source in (manifest.get("counts", {}), manifest):
        result: Dict[str, int] = {}
        for key in ("generated", "mutated", "valid", "invalid"):
            val = _coerce_int(source.get(key))
            if val is not None:
                result[key] = val
        if result:
            return result
    return {}


def _collect_run_metadata(manifest: dict) -> Dict[str, str]:
    keys = (
        "generated_at", "root", "backend", "model",
        "mode", "scope", "seed_dir", "test_file",
        "gen_count", "mut_per_file",
    )
    return {k: str(v) for k in keys if (v := manifest.get(k)) is not None}


def _collect_metrics_snapshot(metrics: dict) -> Dict[str, Any]:
    numeric_keys = (
        "generated", "mutated", "valid", "invalid",
        "executed_total", "executed_lli", "executed_clang",
        "compile_failed", "timeouts", "diffs", "skipped_exec",
        "total_o0_size", "total_o3_size",
        "paired_binary_cases", "binary_savings", "binary_reduction_pct",
    )
    return {
        k: v
        for k in numeric_keys
        if (v := metrics.get(k)) is not None and not isinstance(v, bool)
    }


def _collect_instr_stats(exec_rows: List[dict]) -> Dict[str, Any]:
    """
    Aggregate instruction-count statistics from execution records.

    The O0 execution records carry o0_instr_count / o3_instr_count /
    instr_delta / instr_reduction_pct fields written by _process_file_worker.
    Returns an empty dict if none are present (older runs without these fields).
    """
    o0_counts: List[int]   = []
    o3_counts: List[int]   = []
    deltas:    List[int]   = []
    pcts:      List[float] = []

    for row in exec_rows:
        if row.get("mode") != "O0":
            continue
        o0    = row.get("o0_instr_count")
        o3    = row.get("o3_instr_count")
        delta = row.get("instr_delta")
        pct   = row.get("instr_reduction_pct")
        if isinstance(o0, (int, float)) and isinstance(o3, (int, float)):
            o0_counts.append(int(o0))
            o3_counts.append(int(o3))
        if isinstance(delta, (int, float)):
            deltas.append(int(delta))
        if isinstance(pct, (int, float)):
            pcts.append(float(pct))

    if not o0_counts:
        return {}

    return {
        "total_o0_instructions":   sum(o0_counts),
        "total_o3_instructions":   sum(o3_counts),
        "total_instr_eliminated":  sum(deltas),
        "avg_instr_reduction_pct": round(sum(pcts) / len(pcts), 2) if pcts else 0.0,
        "max_instr_reduction_pct": round(max(pcts), 2) if pcts else 0.0,
        "min_instr_reduction_pct": round(min(pcts), 2) if pcts else 0.0,
        "files_with_instr_data":   len(o0_counts),
    }


def _format_metric(key: str, value: Any) -> str:
    if key == "binary_reduction_pct":
        return f"{float(value):.2f}%"
    if key.endswith("_size") or key == "binary_savings":
        return f"{int(value):,} bytes"
    if isinstance(value, float) and not float(value).is_integer():
        return f"{value:.4f}"
    return str(int(value)) if isinstance(value, float) else str(value)


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_summary(results_dir: Path, evaluation_dir: Path) -> SummaryReport:
    """
    Read all pipeline artefacts from *results_dir* and *evaluation_dir*
    and return a :class:`SummaryReport`.
    """
    file_names = cfg.reporting.files
    max_diffs  = cfg.reporting.max_sample_diffs

    executions = _load_jsonl(results_dir / file_names["executions"])
    diffs      = _load_jsonl(results_dir / file_names["diffs"])
    skipped    = _load_jsonl(results_dir / file_names["skipped"])
    manifest   = _load_json(results_dir  / file_names["run_manifest"])
    metrics    = _load_json(evaluation_dir / file_names["metrics_json"])

    counts       = _collect_counts(manifest)
    run_metadata = _collect_run_metadata(manifest)
    snapshot     = _collect_metrics_snapshot(metrics)
    instr_stats  = _collect_instr_stats(executions)

    # Per-strategy diff rates from metrics.json (written by compute_metrics)
    strategy_diff_rates: Dict[str, float] = {}
    raw_rates = metrics.get("strategy_diff_rates")
    if isinstance(raw_rates, dict):
        strategy_diff_rates = {
            k: float(v)
            for k, v in raw_rates.items()
            if isinstance(v, (int, float))
        }

    totals: Dict[str, int] = {
        "executions": len(executions),
        "diffs":      len(diffs),
        "skipped_exec": len(skipped),
    }
    totals.update(counts)

    diff_reasons = _count_by_key(diffs, "reason")
    sample_diffs = diffs[:max_diffs]

    # ── Notes ──────────────────────────────────────────────────────────────
    notes: List[str] = []
    if not executions:
        notes.append(
            "No executions recorded. "
            "Ensure LLVM tools are installed (llvm-as, opt, lli, clang) or re-run the pipeline."
        )
    elif not diffs:
        notes.append(
            "No mismatches detected — outputs matched across all comparable executions."
        )

    if skipped:
        required  = (cfg.execution.interpreter, cfg.execution.compiler, cfg.execution.optimizer)
        optional  = (cfg.validation.alive2_tool,)
        missing   = [t for t in required if not _tool_available(t)]
        tool_note = (
            "Executions skipped due to missing tools: " + ", ".join(missing) + ". "
            if missing
            else "Some executions skipped (possibly unsupported architecture). "
        )
        tool_note += "Required: " + ", ".join(required) + ". Optional: " + ", ".join(optional) + "."
        notes.append(tool_note)

    # ── Binary-size comparisons ────────────────────────────────────────────
    o0_sizes = {
        str(row["name"]): int(row["binary_size"])
        for row in executions
        if row.get("mode") == "O0"
        and row.get("name")
        and isinstance(row.get("binary_size"), (int, float))
    }
    o3_sizes = {
        str(row["name"]): int(row["binary_size"])
        for row in executions
        if row.get("mode") == "O3"
        and row.get("name")
        and isinstance(row.get("binary_size"), (int, float))
    }

    size_comparisons = []
    for name in sorted(o0_sizes):
        if name not in o3_sizes:
            continue
        o0 = o0_sizes[name]
        o3 = o3_sizes[name]
        savings = o0 - o3
        pct     = (savings / o0 * 100) if o0 > 0 else 0.0
        size_comparisons.append({
            "name":          name,
            "o0_size":       o0,
            "o3_size":       o3,
            "savings":       savings,
            "reduction_pct": pct,
            "direction":     "smaller" if savings >= 0 else "larger",
        })

    return SummaryReport(
        totals               = totals,
        diff_reasons         = diff_reasons,
        sample_diffs         = sample_diffs,
        notes                = notes,
        size_comparisons     = size_comparisons,
        metrics_snapshot     = snapshot,
        run_metadata         = run_metadata,
        instr_stats          = instr_stats,
        strategy_diff_rates  = strategy_diff_rates,
    )


# ---------------------------------------------------------------------------
# Markdown writer
# ---------------------------------------------------------------------------

def write_summary(report: SummaryReport, output_path: Path) -> None:
    """Render *report* as a Markdown file at *output_path*."""
    lines: List[str] = ["# Pipeline Summary", ""]

    # ── Run metadata ───────────────────────────────────────────────────────
    if report.run_metadata:
        lines.append("## Run Metadata")
        for key in sorted(report.run_metadata):
            lines.append(f"- **{key}**: {report.run_metadata[key]}")
        lines.append("")

    # ── Metrics snapshot ───────────────────────────────────────────────────
    if report.metrics_snapshot:
        lines.append("## Metrics Snapshot")
        for key in sorted(report.metrics_snapshot):
            lines.append(f"- **{key}**: {_format_metric(key, report.metrics_snapshot[key])}")
        lines.append("")

    # ── Executive overview (binary-size aggregate) ─────────────────────────
    if report.size_comparisons:
        total_o0  = sum(c["o0_size"] for c in report.size_comparisons)
        total_o3  = sum(c["o3_size"] for c in report.size_comparisons)
        savings   = sum(c["savings"] for c in report.size_comparisons)
        pct       = (savings / total_o0 * 100) if total_o0 else 0.0
        positive  = sum(1 for c in report.size_comparisons if c["savings"] >= 0)

        lines.append("## Executive Overview")
        lines.append(f"- Paired comparisons: {len(report.size_comparisons)}")
        lines.append(f"- Aggregate -O0 size: {total_o0:,} bytes")
        lines.append(f"- Aggregate -O3 size: {total_o3:,} bytes")
        lines.append(f"- Net savings:        {savings:,} bytes ({pct:.2f}% reduction)")
        lines.append(f"- Positive savings:   {positive}/{len(report.size_comparisons)}")
        lines.append("")

    # ── Totals ─────────────────────────────────────────────────────────────
    lines.append("## Totals")
    for key in sorted(report.totals):
        lines.append(f"- {key}: {report.totals[key]}")
    lines.append("")

    # ── Diff reasons ───────────────────────────────────────────────────────
    lines.append("## Diff Reasons")
    if report.diff_reasons:
        for reason, count in sorted(report.diff_reasons.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- None")
    lines.append("")

    # ── Sample diffs ───────────────────────────────────────────────────────
    lines.append("## Sample Diffs")
    if report.sample_diffs:
        for row in report.sample_diffs:
            lines.append(f"- {row.get('name', 'unknown')}: {row.get('reason', 'unknown')}")
    else:
        lines.append("- None")
    lines.append("")

    # ── Binary-size table ──────────────────────────────────────────────────
    lines.append("## Paired Binary-Size Comparisons (-O0 vs -O3)")
    if report.size_comparisons:
        lines.append(
            "| Program | -O0 (bytes) | -O3 (bytes) | Savings (bytes) | Reduction | Direction |"
        )
        lines.append(
            "| :--- | :---: | :---: | :---: | :---: | :---: |"
        )
        for c in report.size_comparisons:
            lines.append(
                f"| {c['name']} "
                f"| {c['o0_size']:,} "
                f"| {c['o3_size']:,} "
                f"| {c['savings']:,} "
                f"| {c['reduction_pct']:.2f}% "
                f"| {c['direction']} |"
            )
    else:
        lines.append("- No successful paired -O0 vs -O3 results found.")

    # ── Notes ──────────────────────────────────────────────────────────────
    if report.notes:
        lines.append("")
        lines.append("## Notes")
        for note in report.notes:
            lines.append(f"- {note}")

    # ── Instruction-count statistics ───────────────────────────────────────
    if report.instr_stats:
        lines.append("")
        lines.append("## Instruction-Count Statistics (O0 → O3)")
        s = report.instr_stats
        lines.append(f"- Total O0 instructions: {s.get('total_o0_instructions', 0):,}")
        lines.append(f"- Total O3 instructions: {s.get('total_o3_instructions', 0):,}")
        lines.append(f"- Total eliminated:      {s.get('total_instr_eliminated', 0):,}")
        lines.append(f"- Average reduction:     {s.get('avg_instr_reduction_pct', 0.0):.2f}%")
        lines.append(f"- Max reduction:         {s.get('max_instr_reduction_pct', 0.0):.2f}%")
        lines.append(f"- Min reduction:         {s.get('min_instr_reduction_pct', 0.0):.2f}%")
        lines.append(f"- Files with data:       {s.get('files_with_instr_data', 0)}")

    # ── Per-strategy diff rates ────────────────────────────────────────────
    if report.strategy_diff_rates:
        lines.append("")
        lines.append("## Per-Strategy Diff Rates")
        lines.append("| Strategy | Diff Rate (%) |")
        lines.append("| :--- | :---: |")
        for strategy, rate in sorted(
            report.strategy_diff_rates.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"| {strategy} | {rate:.2f}% |")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
