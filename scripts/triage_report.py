from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.triage import build_triage, write_triage


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate triage report for diffs.")
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args()

    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()
    report = build_triage(paths.results_dir, sample_limit=args.sample_limit)
    output_path = paths.results_dir / "triage.json"
    write_triage(report, output_path)
    print(f"triage written to {output_path}")


if __name__ == "__main__":
    main()

