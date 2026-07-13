"""
metrics.py — Pipeline metrics collection and persistence.

``compute_metrics``  — aggregate the JSONL logs produced by the pipeline.
``write_metrics``    — write a JSON snapshot.
``write_csv``        — write a single-row CSV summary.
``write_bar_chart``  — draw a bar chart PNG (requires matplotlib).

All file names, chart dimensions, and colour palettes are read from ``cfg``
(config.yaml → reporting section).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.config import cfg


# ---------------------------------------------------------------------------
# Metrics dataclass
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    """All numeric pipeline metrics for one run."""
    # Pipeline counts
    generated:           int
    mutated:             int
    valid:               int
    invalid:             int
    # Execution counts
    executed_total:      int
    executed_lli:        int
    executed_clang:      int
    compile_failed:      int
    timeouts:            int
    diffs:               int
    skipped_exec:        int
    # Binary-size analysis
    total_o0_size:       int
    total_o3_size:       int
    paired_binary_cases: int
    binary_savings:      int
    binary_reduction_pct: float


# ---------------------------------------------------------------------------
# JSONL helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> List[dict]:
    """Read a JSONL file and return a list of parsed dicts (skips bad lines)."""
    if not path.exists():
        return []
    rows: List[dict] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _count_nonempty_lines(path: Path) -> int:
    """Count non-blank lines in a file (used for JSONL diff/skipped counts)."""
    if not path.exists():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_metrics(results_dir: Path, counts: Dict[str, int]) -> Metrics:
    """
    Aggregate execution logs and binary-size data from *results_dir* into a
    :class:`Metrics` instance.

    Parameters
    ----------
    results_dir: directory containing ``executions.jsonl``, ``diffs.jsonl``,
                 and ``skipped_exec.jsonl``
    counts:      ``{"generated": N, "mutated": N, "valid": N, "invalid": N}``
                 from the generation/validation stage
    """
    file_names  = cfg.reporting.files
    exec_rows   = _load_jsonl(results_dir / file_names["executions"])
    diffs_count = _count_nonempty_lines(results_dir / file_names["diffs"])
    skip_count  = _count_nonempty_lines(results_dir / file_names["skipped"])

    executed_lli = sum(
        1 for row in exec_rows
        if row.get("mode") == "lli" and not row.get("skipped")
    )
    executed_clang = sum(
        1 for row in exec_rows
        if row.get("mode") in cfg.execution.opt_levels and not row.get("skipped")
    )
    compile_failed = sum(1 for row in exec_rows if row.get("reason") == "compile_failed")
    timeouts       = sum(1 for row in exec_rows if row.get("reason") == "timeout")

    # Collect object-file sizes per optimisation level
    o0_sizes: Dict[str, int] = {}
    o3_sizes: Dict[str, int] = {}
    for row in exec_rows:
        name = str(row.get("name", ""))
        size = row.get("binary_size")
        if name and isinstance(size, (int, float)):
            if row.get("mode") == "O0":
                o0_sizes[name] = int(size)
            elif row.get("mode") == "O3":
                o3_sizes[name] = int(size)

    paired_names         = sorted(set(o0_sizes) & set(o3_sizes))
    paired_binary_cases  = len(paired_names)
    binary_savings       = sum(o0_sizes[n] - o3_sizes[n] for n in paired_names)
    paired_o0_total      = sum(o0_sizes[n] for n in paired_names)
    binary_reduction_pct = (
        (binary_savings / paired_o0_total * 100) if paired_o0_total else 0.0
    )

    return Metrics(
        generated           = counts.get("generated", 0),
        mutated             = counts.get("mutated", 0),
        valid               = counts.get("valid", 0),
        invalid             = counts.get("invalid", 0),
        executed_total      = len(exec_rows),
        executed_lli        = executed_lli,
        executed_clang      = executed_clang,
        compile_failed      = compile_failed,
        timeouts            = timeouts,
        diffs               = diffs_count,
        skipped_exec        = skip_count,
        total_o0_size       = sum(o0_sizes.values()),
        total_o3_size       = sum(o3_sizes.values()),
        paired_binary_cases = paired_binary_cases,
        binary_savings      = binary_savings,
        binary_reduction_pct= binary_reduction_pct,
    )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def write_metrics(metrics: Metrics, output_path: Path) -> None:
    """Write *metrics* as a pretty-printed JSON file."""
    output_path.write_text(json.dumps(metrics.__dict__, indent=2), encoding="utf-8")


def write_csv(metrics: Metrics, output_path: Path) -> None:
    """Write *metrics* as a single-row CSV with a header."""
    headers = ",".join(metrics.__dict__.keys())
    values  = ",".join(
        f"{v:.4f}" if isinstance(v, float) else str(v)
        for v in metrics.__dict__.values()
    )
    output_path.write_text(f"{headers}\n{values}\n", encoding="utf-8")


def write_bar_chart(metrics: Metrics, output_path: Path) -> Optional[Path]:
    """
    Draw a bar chart of key pipeline counts and save it as a PNG.

    Returns the output path on success, or None if matplotlib is unavailable.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    labels = ["Generated", "Valid", "Invalid", "Executed", "Pairs", "Diffs", "Skipped"]
    values = [
        metrics.generated,
        metrics.valid,
        metrics.invalid,
        metrics.executed_total,
        metrics.paired_binary_cases,
        metrics.diffs,
        metrics.skipped_exec,
    ]

    chart_cfg = cfg.reporting.chart
    colors    = chart_cfg.colors or [
        "#7c3aed", "#22c55e", "#ef4444",
        "#0ea5e9", "#f59e0b", "#6366f1", "#94a3b8",
    ]
    # Ensure we have enough colours (cycle if needed)
    colors = [colors[i % len(colors)] for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(chart_cfg.width, chart_cfg.height), dpi=chart_cfg.dpi)
    bars = ax.bar(labels, values, color=colors)

    ax.set_title("LLVM IR Pipeline Snapshot", pad=14, fontsize=14, fontweight="bold")
    ax.set_ylabel("Count")
    ax.grid(axis="y", linestyle="--", alpha=0.22)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", rotation=0)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(value),
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path
