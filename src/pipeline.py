"""
pipeline.py — End-to-end pipeline orchestration.

``run_pipeline`` drives the full flow:

  1. Resolve project paths and create directories.
  2. Clear stale IR and diff artefacts from a previous run.
  3. Ensure a seed corpus exists (synthetic if the dataset directory is empty).
  4. Generate IR (template-based or LLM-backed).
  5. Mutate dataset and generated IR.
  6. Validate all IR files (move to valid_ir / invalid_ir).
  7. Execute each valid IR file at all configured optimisation levels.
  8. Emit and diff the optimised textual IR.
  9. Write per-file execution logs.
  10. Compute metrics and write JSON / CSV / PNG.
  11. Build and write the Markdown summary report.
  12. Write a run manifest for reproducibility.

All file names, tool names, timeouts, and other constants are loaded from
``cfg`` (config.yaml) — nothing is hardcoded in this module.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.config import cfg, ProjectPaths
from src.diff_test import compare_optimized_ir, compare_results
from src.executor import ExecutionResult, emit_optimized_ir, run_clang, run_lli
from src.ir_generator import write_generated_ir
from src.metrics import compute_metrics, write_bar_chart, write_csv, write_metrics
from src.mutator import mutate_files
from src.reporting import build_summary, write_summary
from src.triage import build_triage, write_triage
from src.validator import validate_directory

try:
    from tqdm import tqdm as _tqdm
except ImportError:  # pragma: no cover
    def _tqdm(it, **kwargs):  # type: ignore[misc]
        """Minimal no-op fallback when tqdm is not installed."""
        total = kwargs.get("total")
        desc  = kwargs.get("desc", "")
        if desc:
            print(f"  {desc} ...", flush=True)
        return it


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _clear_ll_files(directory: Path) -> None:
    """Remove all *.ll files from *directory* (non-recursive)."""
    if directory.exists():
        for path in directory.glob("*.ll"):
            path.unlink()


def _clear_files(directory: Path) -> None:
    """Remove all regular files from *directory* (non-recursive)."""
    if directory.exists():
        for path in directory.iterdir():
            if path.is_file():
                path.unlink()


def _ensure_seed_corpus(paths: ProjectPaths) -> None:
    """
    Create a synthetic seed IR file in the dataset directory if it does
    not already exist.  The file contains a long chain of add instructions
    that O3 folds to a constant — a reliable benchmark for DCE/CF.
    """
    seed_cfg  = cfg.seed_corpus
    seed_file = paths.dataset_dir / seed_cfg.filename

    if seed_file.exists():
        return  # already present from a previous run or user-supplied

    chain = seed_cfg.chain_length
    lines = ["define i32 @main() {", "entry:"]
    lines.append("  %x0 = add i32 0, 0")
    for i in range(1, chain):
        lines.append(f"  %x{i} = add i32 %x{i - 1}, 1")
    lines.append(f"  ret i32 %x{chain - 1}")
    lines.append("}\n")
    seed_file.write_text("\n".join(lines), encoding="utf-8")


def _write_run_manifest(
    manifest_path: Path,
    *,
    root:        Path,
    backend:     str,
    model:       str,
    mode:        str,
    gen_count:   int,
    mut_per_file: int,
    seed_dir:    Optional[Path],
    test_file:   Optional[Path],
    counts:      Dict[str, int],
) -> None:
    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root":         str(root.resolve()),
        "backend":      backend,
        "model":        model,
        "mode":         mode,
        "gen_count":    gen_count,
        "mut_per_file": mut_per_file,
        "scope":        "single_file" if test_file is not None else "pipeline",
        "seed_dir":     str(seed_dir.resolve()) if seed_dir else None,
        "test_file":    str(test_file.resolve()) if test_file else None,
        "counts":       counts,
        **counts,  # flat copy so downstream tools can read without nesting
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _write_log(log_path: Path, text: str) -> None:
    log_path.write_text(text, encoding="utf-8")


def _fmt_bytes(n: int | float | None) -> str:
    """Human-readable byte count (e.g. 14.23 KB)."""
    if n is None:
        return "0 B"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024.0:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def _print_summary_table(counts: Dict[str, int], metrics_path: Path) -> None:
    """Print a compact results table to stdout after the pipeline completes."""
    import json as _json
    metrics: dict = {}
    if metrics_path.exists():
        try:
            metrics = _json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    savings     = metrics.get("binary_savings", 0)
    reduction   = metrics.get("binary_reduction_pct", 0.0)
    pairs       = metrics.get("paired_binary_cases", 0)
    mismatches  = metrics.get("diffs", 0)
    failed      = metrics.get("compile_failed", 0)
    timeouts    = metrics.get("timeouts", 0)

    sep = "─" * 44
    print(f"\n  ┌{sep}┐")
    print(f"  │{'  Pipeline Results':^44}│")
    print(f"  ├{sep}┤")
    rows = [
        ("Generated IR files",  counts.get("generated", 0)),
        ("Mutated variants",     counts.get("mutated",   0)),
        ("Valid IR files",       counts.get("valid",     0)),
        ("Invalid IR files",     counts.get("invalid",   0)),
        ("Paired comparisons",   pairs),
        ("Binary savings",       _fmt_bytes(savings) + f"  ({reduction:.1f}%)"),
        ("Output mismatches",    mismatches),
        ("Compile failures",     failed),
        ("Timeouts",             timeouts),
    ]
    for label, value in rows:
        print(f"  │  {label:<26}{str(value):>14}  │")
    print(f"  └{sep}┘\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    root:         Path,
    gen_count:    int            = cfg.generation.count,
    mut_per_file: int            = cfg.mutation.per_file,
    backend:      str            = cfg.generation.backend,
    model:        str            = cfg.generation.model,
    mode:         str            = cfg.generation.mode,
    seed_dir:     Optional[Path] = None,
    test_file:    Optional[Path] = None,
) -> None:
    """
    Run the complete LLVM IR differential testing pipeline.

    Parameters
    ----------
    root:         project root directory
    gen_count:    number of IR files to generate
    mut_per_file: mutations per dataset file
    backend:      generation backend ("template" | "openai")
    model:        LLM model name (only used when backend != "template")
    mode:         "generate" | "mutate"
    seed_dir:     optional directory of *.ll files used as mutation seeds
    test_file:    if set, skip generation/mutation and test this single file
    """
    paths = ProjectPaths.from_config(cfg, root)
    paths.ensure_dirs()

    # Clean stale artefacts from previous run
    for d in (paths.generated_dir, paths.mutated_dir, paths.valid_dir, paths.invalid_dir):
        _clear_ll_files(d)
    for d in (paths.optimized_dir, paths.diffs_dir):
        _clear_files(d)

    _ensure_seed_corpus(paths)

    file_names   = cfg.reporting.files
    manifest_path = paths.results_dir / file_names["run_manifest"]

    # ── Step 1: Generate and mutate (or inject a single test file) ─────────
    if test_file is None:
        gen_seed = cfg.generation.seed
        mut_seed = cfg.mutation.seed

        print(f"[1/5] Generating {gen_count} IR files  (backend={backend}, mode={mode}) ...",
              flush=True)
        generated = write_generated_ir(
            output_dir = paths.generated_dir,
            count      = gen_count,
            seed       = gen_seed,
            backend    = backend,
            model      = model,
            mode       = mode,
            seed_dir   = seed_dir,
        )
        print(f"       → {len(generated)} files written to {paths.generated_dir.relative_to(root)}",
              flush=True)

        print("[2/5] Mutating IR files ...", flush=True)
        mutated = mutate_files(
            paths.dataset_dir,
            paths.mutated_dir,
            per_file = mut_per_file,
            seed     = mut_seed,
        )
        mutated += mutate_files(
            paths.generated_dir,
            paths.mutated_dir,
            per_file = cfg.mutation.per_generated_file,
            seed     = mut_seed,
        )
        print(f"       → {len(mutated)} mutated variants", flush=True)

        print("[3/5] Validating IR files ...", flush=True)
        valid_gen,   invalid_gen   = validate_directory(paths.generated_dir, paths.valid_dir, paths.invalid_dir)
        valid_mut,   invalid_mut   = validate_directory(paths.mutated_dir,   paths.valid_dir, paths.invalid_dir)
        print(f"       → {valid_gen + valid_mut} valid, {invalid_gen + invalid_mut} invalid",
              flush=True)

        counts = {
            "generated": len(generated),
            "mutated":   len(mutated),
            "valid":     valid_gen + valid_mut,
            "invalid":   invalid_gen + invalid_mut,
        }
    else:
        if not test_file.exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")
        dest = paths.valid_dir / Path(test_file).name
        dest.write_text(Path(test_file).read_text(encoding="utf-8"), encoding="utf-8")
        generated = []
        mutated   = []
        counts    = {"generated": 0, "mutated": 0, "valid": 1, "invalid": 0}

    _write_run_manifest(
        manifest_path,
        root         = root,
        backend      = backend,
        model        = model,
        mode         = mode,
        gen_count    = gen_count,
        mut_per_file = mut_per_file,
        seed_dir     = seed_dir,
        test_file    = test_file,
        counts       = counts,
    )

    # ── Step 2: Execute, diff, and log ─────────────────────────────────────
    executions_path = paths.results_dir / file_names["executions"]
    diffs_path      = paths.results_dir / file_names["diffs"]
    skipped_path    = paths.results_dir / file_names["skipped"]

    for p in (executions_path, diffs_path, skipped_path):
        if p.exists():
            p.unlink()

    # Resolve the two comparison opt-levels from config (typically ["O0", "O3"])
    opt_levels = cfg.execution.opt_levels
    lvl_base   = opt_levels[0]   # e.g. "O0"
    lvl_opt    = opt_levels[1]   # e.g. "O3"

    ir_files = sorted(paths.valid_dir.glob("*.ll"))
    workers  = min(os.cpu_count() or 4, len(ir_files) or 1)
    print(f"[4/5] Executing {len(ir_files)} IR files  "
          f"(-{lvl_base} vs -{lvl_opt}, {workers} threads) ...", flush=True)

    def _process_one(ir_file: Path) -> Tuple[
        List[dict],   # exec records to append
        List[dict],   # diff records to append
        List[dict],   # skipped records to append
        List[Tuple[Path, str]],  # log files to write
    ]:
        stem     = ir_file.stem
        exec_recs: List[dict] = []
        diff_recs: List[dict] = []
        skip_recs: List[dict] = []
        logs:      List[Tuple[Path, str]] = []

        res_lli  = run_lli(ir_file)
        res_base = run_clang(ir_file, lvl_base)
        res_opt  = run_clang(ir_file, lvl_opt)

        ok_base, ir_base, err_base = emit_optimized_ir(ir_file, lvl_base)
        ok_opt,  ir_opt,  err_opt  = emit_optimized_ir(ir_file, lvl_opt)

        if ok_base:
            (paths.optimized_dir / f"{stem}.{lvl_base}.ll").write_text(ir_base, encoding="utf-8")
        if ok_opt:
            (paths.optimized_dir / f"{stem}.{lvl_opt}.ll").write_text(ir_opt, encoding="utf-8")

        diff_text = (
            compare_optimized_ir(stem, ir_base, ir_opt).unified_diff or "# no textual diff\n"
        ) if ok_base and ok_opt else (
            f"# optimised IR unavailable\n"
            f"# {lvl_base}: ok={ok_base} err={err_base!r}\n"
            f"# {lvl_opt}:  ok={ok_opt}  err={err_opt!r}\n"
        )
        (paths.diffs_dir / f"{stem}.diff").write_text(diff_text, encoding="utf-8")

        if not res_lli.skipped:
            logs.append((paths.logs_dir / f"{stem}.lli.out", res_lli.stdout))
            logs.append((paths.logs_dir / f"{stem}.lli.err", res_lli.stderr))

        if res_base.skipped or res_opt.skipped:
            skip_recs.append({"name": stem, "reason": "tool_missing"})
            return exec_recs, diff_recs, skip_recs, logs

        exec_recs.append(asdict(res_lli))
        exec_recs.append(asdict(res_base))
        exec_recs.append(asdict(res_opt))

        logs.append((paths.logs_dir / f"{stem}.{lvl_base}.out", res_base.stdout))
        logs.append((paths.logs_dir / f"{stem}.{lvl_base}.err", res_base.stderr))
        logs.append((paths.logs_dir / f"{stem}.{lvl_opt}.out",  res_opt.stdout))
        logs.append((paths.logs_dir / f"{stem}.{lvl_opt}.err",  res_opt.stderr))

        beh_diff = compare_results(stem, res_base, res_opt)
        if not beh_diff.match:
            diff_recs.append(asdict(beh_diff))

        return exec_recs, diff_recs, skip_recs, logs

    # Run all files in parallel; write results under a lock to avoid races
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_one, f): f for f in ir_files}
        with _tqdm(total=len(ir_files), desc="Executing", unit="file") as bar:
            for fut in as_completed(futures):
                exec_recs, diff_recs, skip_recs, logs = fut.result()

                # Sequential I/O (fast; avoids file-handle races)
                with executions_path.open("a", encoding="utf-8") as fh:
                    for rec in exec_recs:
                        fh.write(json.dumps(rec) + "\n")
                with diffs_path.open("a", encoding="utf-8") as fh:
                    for rec in diff_recs:
                        fh.write(json.dumps(rec) + "\n")
                with skipped_path.open("a", encoding="utf-8") as fh:
                    for rec in skip_recs:
                        fh.write(json.dumps(rec) + "\n")
                for log_path, content in logs:
                    _write_log(log_path, content)

                bar.update(1)

    print(f"       → results written to {paths.results_dir.relative_to(root)}", flush=True)

    # ── Step 3: Metrics + reports ──────────────────────────────────────────
    print("[5/5] Computing metrics and writing reports ...", flush=True)
    metrics_json_path = paths.evaluation_dir / file_names["metrics_json"]
    metrics = compute_metrics(paths.results_dir, counts)
    write_metrics(metrics, metrics_json_path)
    write_csv(metrics,     paths.evaluation_dir / file_names["metrics_csv"])
    write_bar_chart(metrics, paths.evaluation_dir / file_names["metrics_png"])

    summary = build_summary(paths.results_dir, paths.evaluation_dir)
    write_summary(summary, paths.results_dir / file_names["summary"])

    triage = build_triage(paths.results_dir)
    write_triage(triage, paths.results_dir / file_names["triage"])

    _print_summary_table(counts, metrics_json_path)
