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
    )


def write_metrics(metrics: Metrics, output_path: Path) -> None:
    output_path.write_text(json.dumps(metrics.__dict__, indent=2))


def write_csv(metrics: Metrics, output_path: Path) -> None:
    output_path.write_text(
        "generated,mutated,valid,invalid,executed_total,executed_lli,executed_clang,"
        "compile_failed,timeouts,diffs,skipped_exec\n"
        f"{metrics.generated},{metrics.mutated},{metrics.valid},{metrics.invalid},"
        f"{metrics.executed_total},{metrics.executed_lli},{metrics.executed_clang},"
        f"{metrics.compile_failed},{metrics.timeouts},{metrics.diffs},{metrics.skipped_exec}\n"
    )


def write_bar_chart(metrics: Metrics, output_path: Path) -> Optional[Path]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None

    labels = [
        "generated",
        "mutated",
        "valid",
        "invalid",
        "executed_total",
        "executed_lli",
        "executed_clang",
        "compile_failed",
        "timeouts",
        "diffs",
        "skipped",
    ]
    values = [
        metrics.generated,
        metrics.mutated,
        metrics.valid,
        metrics.invalid,
        metrics.executed_total,
        metrics.executed_lli,
        metrics.executed_clang,
        metrics.compile_failed,
        metrics.timeouts,
        metrics.diffs,
        metrics.skipped_exec,
    ]
    plt.figure(figsize=(8, 4))
    plt.bar(labels, values)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    return output_path

