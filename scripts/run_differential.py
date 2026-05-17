from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.diff_test import compare_results
from src.executor import run_clang, run_lli


def main() -> None:
    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()

    executions_path = paths.results_dir / "executions.jsonl"
    diffs_path = paths.results_dir / "diffs.jsonl"
    skipped_path = paths.results_dir / "skipped_exec.jsonl"

    for file_path in sorted(paths.valid_dir.glob("*.ll")):
        res_lli = run_lli(file_path)
        res_o0 = run_clang(file_path, "O0")
        res_o3 = run_clang(file_path, "O3")

        if not res_lli.skipped:
            (paths.logs_dir / f"{file_path.stem}.lli.out").write_text(res_lli.stdout)
            (paths.logs_dir / f"{file_path.stem}.lli.err").write_text(res_lli.stderr)

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

        (paths.logs_dir / f"{file_path.stem}.O0.out").write_text(res_o0.stdout)
        (paths.logs_dir / f"{file_path.stem}.O0.err").write_text(res_o0.stderr)
        (paths.logs_dir / f"{file_path.stem}.O3.out").write_text(res_o3.stdout)
        (paths.logs_dir / f"{file_path.stem}.O3.err").write_text(res_o3.stderr)

        diff = compare_results(file_path.stem, res_o0, res_o3)
        if not diff.match:
            with diffs_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(diff)) + "\n")


if __name__ == "__main__":
    main()
