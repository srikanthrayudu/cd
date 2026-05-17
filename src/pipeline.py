from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from src.config import ProjectPaths
from src.diff_test import compare_results
from src.executor import run_clang, run_lli
from src.llm_generator import GenerationConfig, write_generated_ir
from src.metrics import compute_metrics, write_bar_chart, write_csv, write_metrics
from src.mutator import MutationConfig, mutate_files
from src.reporting import build_summary, write_summary
from src.triage import build_triage, write_triage
from src.validator import validate_directory


def ensure_seed_corpus(paths: ProjectPaths) -> None:
    sample_file = paths.dataset_dir / "seed_sample.ll"
    if sample_file.exists():
        return
    sample_ir = (
        "define i32 @seed_add(i32 %x, i32 %y) {\n"
        "entry:\n"
        "  %sum = add i32 %x, %y\n"
        "  ret i32 %sum\n"
        "}\n"
    )
    sample_file.write_text(sample_ir)


def run_pipeline(
    root: Path,
    gen_count: int = 5,
    mut_per_file: int = 2,
    backend: str = "template",
    model: str = "gpt-4o-mini",
    mode: str = "generate",
    seed_dir: Optional[Path] = None,
) -> None:
    paths = ProjectPaths.from_root(root)
    paths.ensure_dirs()
    ensure_seed_corpus(paths)

    generated = write_generated_ir(
        paths.generated_dir,
        GenerationConfig(
            count=gen_count,
            backend=backend,
            model=model,
            mode=mode,
            seed_dir=seed_dir,
        ),
    )
    mutated = mutate_files(paths.dataset_dir, paths.mutated_dir, MutationConfig(per_file=mut_per_file))
    mutated += mutate_files(paths.generated_dir, paths.mutated_dir, MutationConfig(per_file=1))

    valid_count, invalid_count = validate_directory(
        paths.generated_dir,
        paths.valid_dir,
        paths.invalid_dir,
    )
    valid_mut_count, invalid_mut_count = validate_directory(
        paths.mutated_dir,
        paths.valid_dir,
        paths.invalid_dir,
    )

    counts = {
        "generated": len(generated),
        "mutated": len(mutated),
        "valid": valid_count + valid_mut_count,
        "invalid": invalid_count + invalid_mut_count,
    }

    executions_path = paths.results_dir / "executions.jsonl"
    diffs_path = paths.results_dir / "diffs.jsonl"
    skipped_path = paths.results_dir / "skipped_exec.jsonl"

    for file_path in sorted(paths.valid_dir.glob("*.ll")):
        res_lli = run_lli(file_path)
        res_o0 = run_clang(file_path, "O0")
        res_o3 = run_clang(file_path, "O3")

        if not res_lli.skipped:
            with (paths.logs_dir / f"{file_path.stem}.lli.out").open("w", encoding="utf-8") as handle:
                handle.write(res_lli.stdout)
            with (paths.logs_dir / f"{file_path.stem}.lli.err").open("w", encoding="utf-8") as handle:
                handle.write(res_lli.stderr)

        if res_o0.skipped or res_o3.skipped:
            with skipped_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps({"name": file_path.stem, "reason": "tool_missing"})
                    + "\n"
                )
            continue

        with executions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(res_lli)) + "\n")
            handle.write(json.dumps(asdict(res_o0)) + "\n")
            handle.write(json.dumps(asdict(res_o3)) + "\n")

        with (paths.logs_dir / f"{file_path.stem}.O0.out").open("w", encoding="utf-8") as handle:
            handle.write(res_o0.stdout)
        with (paths.logs_dir / f"{file_path.stem}.O0.err").open("w", encoding="utf-8") as handle:
            handle.write(res_o0.stderr)
        with (paths.logs_dir / f"{file_path.stem}.O3.out").open("w", encoding="utf-8") as handle:
            handle.write(res_o3.stdout)
        with (paths.logs_dir / f"{file_path.stem}.O3.err").open("w", encoding="utf-8") as handle:
            handle.write(res_o3.stderr)

        diff = compare_results(file_path.stem, res_o0, res_o3)
        if not diff.match:
            with diffs_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(diff)) + "\n")

    metrics = compute_metrics(paths.results_dir, counts)
    write_metrics(metrics, paths.evaluation_dir / "metrics.json")
    write_csv(metrics, paths.evaluation_dir / "metrics.csv")
    write_bar_chart(metrics, paths.evaluation_dir / "metrics.png")
    summary = build_summary(paths.results_dir, paths.evaluation_dir)
    write_summary(summary, paths.results_dir / "summary.md")
    triage = build_triage(paths.results_dir)
    write_triage(triage, paths.results_dir / "triage.json")
