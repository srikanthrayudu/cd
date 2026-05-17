from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class Metrics:
    generated: int
    mutated: int
    valid: int
    invalid: int
    executed_total: int
    executed_lli: int
    executed_clang: int
    compile_failed: int
    timeouts: int
    diffs: int
    skipped_exec: int
    total_o0_size: int = 0
    total_o3_size: int = 0
    paired_binary_cases: int = 0
    binary_savings: int = 0
    binary_reduction_pct: float = 0.0


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.read_text().splitlines() if _.strip())


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def compute_metrics(results_dir: Path, counts: Dict[str, int]) -> Metrics:
    execution_rows = _load_jsonl(results_dir / "executions.jsonl")
    executions = len(execution_rows)
    executed_lli = sum(1 for row in execution_rows if row.get("mode") == "lli" and not row.get("skipped"))
    executed_clang = sum(
        1
        for row in execution_rows
        if row.get("mode") in {"O0", "O3"} and not row.get("skipped")
    )
    compile_failed = sum(1 for row in execution_rows if row.get("reason") == "compile_failed")
    timeouts = sum(1 for row in execution_rows if row.get("reason") == "timeout")
    diffs = _count_lines(results_dir / "diffs.jsonl")
    skipped_exec = _count_lines(results_dir / "skipped_exec.jsonl")
    total_o0_size = sum(row.get("binary_size") or 0 for row in execution_rows if row.get("mode") == "O0")
    total_o3_size = sum(row.get("binary_size") or 0 for row in execution_rows if row.get("mode") == "O3")
    o0_sizes = {str(row.get("name")): int(row.get("binary_size") or 0) for row in execution_rows if row.get("mode") == "O0" and row.get("name") and row.get("binary_size") is not None}
    o3_sizes = {str(row.get("name")): int(row.get("binary_size") or 0) for row in execution_rows if row.get("mode") == "O3" and row.get("name") and row.get("binary_size") is not None}
    paired_names = sorted(set(o0_sizes).intersection(o3_sizes))
    paired_binary_cases = len(paired_names)
    binary_savings = sum(o0_sizes[name] - o3_sizes[name] for name in paired_names)
    paired_o0_total = sum(o0_sizes[name] for name in paired_names)
    binary_reduction_pct = (binary_savings / paired_o0_total * 100) if paired_o0_total else 0.0
    return Metrics(
        generated=counts.get("generated", 0),
        mutated=counts.get("mutated", 0),
        valid=counts.get("valid", 0),
        invalid=counts.get("invalid", 0),
        executed_total=executions,
        executed_lli=executed_lli,
        executed_clang=executed_clang,
        compile_failed=compile_failed,
        timeouts=timeouts,
        diffs=diffs,
        skipped_exec=skipped_exec,
        total_o0_size=total_o0_size,
        total_o3_size=total_o3_size,
        paired_binary_cases=paired_binary_cases,
        binary_savings=binary_savings,
        binary_reduction_pct=binary_reduction_pct,
    )


def write_metrics(metrics: Metrics, output_path: Path) -> None:
    output_path.write_text(json.dumps(metrics.__dict__, indent=2))


def write_csv(metrics: Metrics, output_path: Path) -> None:
    output_path.write_text(
        "generated,mutated,valid,invalid,executed_total,executed_lli,executed_clang,"
        "compile_failed,timeouts,diffs,skipped_exec,total_o0_size,total_o3_size,"
        "paired_binary_cases,binary_savings,binary_reduction_pct\n"
        f"{metrics.generated},{metrics.mutated},{metrics.valid},{metrics.invalid},"
        f"{metrics.executed_total},{metrics.executed_lli},{metrics.executed_clang},"
        f"{metrics.compile_failed},{metrics.timeouts},{metrics.diffs},{metrics.skipped_exec},"
        f"{metrics.total_o0_size},{metrics.total_o3_size},{metrics.paired_binary_cases},"
        f"{metrics.binary_savings},{metrics.binary_reduction_pct:.4f}\n"
    )


def write_bar_chart(metrics: Metrics, output_path: Path) -> Optional[Path]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
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
    colors = ["#7c3aed", "#22c55e", "#ef4444", "#0ea5e9", "#f59e0b", "#6366f1", "#94a3b8"]
    plt.figure(figsize=(11.5, 5.5), dpi=140)
    bars = plt.bar(labels, values, color=colors)
    plt.title("LLVM IR Pipeline Snapshot", pad=14, fontsize=14, fontweight="bold")
    plt.ylabel("Count")
    plt.grid(axis="y", linestyle="--", alpha=0.22)
    plt.xticks(rotation=0, ha="center")
    plt.gca().spines["top"].set_visible(False)
    plt.gca().spines["right"].set_visible(False)
    for bar, value in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(value), ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    return output_path
