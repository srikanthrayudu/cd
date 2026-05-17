from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from src.config import ProjectPaths
from src.diff_test import compare_optimized_ir, compare_results
from src.executor import emit_optimized_ir, run_clang, run_lli
from src.llm_generator import GenerationConfig, write_generated_ir
from src.metrics import compute_metrics, write_bar_chart, write_csv, write_metrics
from src.mutator import MutationConfig, mutate_files
from src.reporting import build_summary, write_summary
from src.triage import build_triage, write_triage
from src.validator import validate_directory


def _clear_ll_files(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("*.ll"):
        path.unlink()


def _clear_diff_artifacts(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("*"):
        if path.is_file():
            path.unlink()


def ensure_seed_corpus(paths: ProjectPaths) -> None:
    sample_file = paths.dataset_dir / "seed_sample.ll"
    if sample_file.exists():
        sample_file.unlink()

    lines = ["define i32 @main() {", "entry:"]
    lines.append("  %x0 = add i32 0, 0")
    for i in range(1, 1500):
        lines.append(f"  %x{i} = add i32 %x{i-1}, 1")
    lines.append("  ret i32 %x1499")
    lines.append("}\n")
    sample_file.write_text("\n".join(lines))


def run_pipeline(
    root: Path,
    gen_count: int = 5,
    mut_per_file: int = 2,
    backend: str = "template",
    model: str = "gpt-4o-mini",
    mode: str = "generate",
    seed_dir: Optional[Path] = None,
    test_file: Optional[Path] = None,
) -> None:
    paths = ProjectPaths.from_root(root)
    paths.ensure_dirs()
    for directory in (paths.generated_dir, paths.mutated_dir, paths.valid_dir, paths.invalid_dir):
        _clear_ll_files(directory)
    for directory in (paths.optimized_dir, paths.diffs_dir):
        _clear_diff_artifacts(directory)
    ensure_seed_corpus(paths)
    manifest_path = paths.results_dir / "run_manifest.json"

    # If a single test file is provided (Option A), copy it into the valid_dir and
    # run the execution/analysis steps only for that file. Otherwise run the
    # normal generate->mutate->validate flow.
    if test_file is None:
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
    else:
        # ensure directories exist and place the test file into valid_dir
        paths.valid_dir.mkdir(parents=True, exist_ok=True)
        if not test_file.exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")
        dest = paths.valid_dir / Path(test_file).name
        dest.write_text(Path(test_file).read_text())

        # No generation or mutation performed
        generated = []
        mutated = []
        counts = {"generated": 0, "mutated": 0, "valid": 1, "invalid": 0}

    manifest_path.write_text(json.dumps(counts, indent=2) + "\n")

    executions_path = paths.results_dir / "executions.jsonl"
    diffs_path = paths.results_dir / "diffs.jsonl"
    skipped_path = paths.results_dir / "skipped_exec.jsonl"

    for p in (executions_path, diffs_path, skipped_path):
        if p.exists():
            p.unlink()

    for file_path in sorted(paths.valid_dir.glob("*.ll")):
        res_lli = run_lli(file_path)
        res_o0 = run_clang(file_path, "O0")
        res_o3 = run_clang(file_path, "O3")

        o0_ok, o0_ir, o0_ir_err = emit_optimized_ir(file_path, "O0")
        o3_ok, o3_ir, o3_ir_err = emit_optimized_ir(file_path, "O3")

        if o0_ok:
            (paths.optimized_dir / f"{file_path.stem}.O0.ll").write_text(o0_ir)
        if o3_ok:
            (paths.optimized_dir / f"{file_path.stem}.O3.ll").write_text(o3_ir)
        if o0_ok and o3_ok:
            code_diff = compare_optimized_ir(file_path.stem, o0_ir, o3_ir)
            (paths.diffs_dir / f"{file_path.stem}.diff").write_text(code_diff.unified_diff or "# no textual diff\n")
        else:
            (paths.diffs_dir / f"{file_path.stem}.diff").write_text(
                f"# optimized IR unavailable\no0_ok={o0_ok} o0_err={o0_ir_err}\no3_ok={o3_ok} o3_err={o3_ir_err}\n"
            )

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
