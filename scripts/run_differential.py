"""
scripts/run_differential.py — Run differential execution on all files in valid_ir/.

Compiles and runs each *.ll file at every configured optimisation level, records
execution results and binary sizes, and writes diffs.jsonl for any mismatches.

This is the execution-only portion of the full pipeline — useful when you have
already generated and validated IR and only want to re-run the comparison step.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.diff_test import compare_results, compare_optimized_ir
from src.executor import emit_optimized_ir, run_clang, run_lli


def main() -> None:
    paths      = ProjectPaths.from_config(cfg, ROOT)
    file_names = cfg.reporting.files
    paths.ensure_dirs()

    executions_path = paths.results_dir / file_names["executions"]
    diffs_path      = paths.results_dir / file_names["diffs"]
    skipped_path    = paths.results_dir / file_names["skipped"]

    # Start fresh for this run
    for p in (executions_path, diffs_path, skipped_path):
        if p.exists():
            p.unlink()

    ir_files = sorted(paths.valid_dir.glob("*.ll"))
    if not ir_files:
        print("No *.ll files found in valid_ir/ — nothing to execute.")
        return

    opt_levels = cfg.execution.opt_levels
    lvl_base   = opt_levels[0]
    lvl_opt    = opt_levels[1]

    for ir_file in ir_files:
        stem     = ir_file.stem
        res_lli  = run_lli(ir_file)
        res_base = run_clang(ir_file, lvl_base)
        res_opt  = run_clang(ir_file, lvl_opt)

        # Emit textual IR for diff analysis
        ok_base, ir_base, _ = emit_optimized_ir(ir_file, lvl_base)
        ok_opt,  ir_opt,  _ = emit_optimized_ir(ir_file, lvl_opt)

        if ok_base:
            (paths.optimized_dir / f"{stem}.{lvl_base}.ll").write_text(ir_base, encoding="utf-8")
        if ok_opt:
            (paths.optimized_dir / f"{stem}.{lvl_opt}.ll").write_text(ir_opt,  encoding="utf-8")
        if ok_base and ok_opt:
            code_diff = compare_optimized_ir(stem, ir_base, ir_opt)
            (paths.diffs_dir / f"{stem}.diff").write_text(
                code_diff.unified_diff or "# no textual diff\n", encoding="utf-8"
            )

        # Write interpreter logs
        if not res_lli.skipped:
            (paths.logs_dir / f"{stem}.lli.out").write_text(res_lli.stdout, encoding="utf-8")
            (paths.logs_dir / f"{stem}.lli.err").write_text(res_lli.stderr, encoding="utf-8")

        # Handle missing compiler
        if res_base.skipped or res_opt.skipped:
            with skipped_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"name": stem, "reason": "tool_missing"}) + "\n")
            continue

        # Write execution records
        with executions_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(res_lli))  + "\n")
            fh.write(json.dumps(asdict(res_base)) + "\n")
            fh.write(json.dumps(asdict(res_opt))  + "\n")

        # Write clang logs
        (paths.logs_dir / f"{stem}.{lvl_base}.out").write_text(res_base.stdout, encoding="utf-8")
        (paths.logs_dir / f"{stem}.{lvl_base}.err").write_text(res_base.stderr, encoding="utf-8")
        (paths.logs_dir / f"{stem}.{lvl_opt}.out").write_text(res_opt.stdout,  encoding="utf-8")
        (paths.logs_dir / f"{stem}.{lvl_opt}.err").write_text(res_opt.stderr,  encoding="utf-8")

        # Record behavioural diffs
        diff = compare_results(stem, res_base, res_opt)
        if not diff.match:
            with diffs_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(diff)) + "\n")

    print(
        f"executed={len(ir_files)}  "
        f"executions={executions_path}  "
        f"diffs={diffs_path}"
    )


if __name__ == "__main__":
    main()
