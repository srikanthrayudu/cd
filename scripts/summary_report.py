from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.reporting import build_summary, write_summary


def main() -> None:
    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()
    report = build_summary(paths.results_dir, paths.evaluation_dir)
    output_path = paths.results_dir / "summary.md"
    write_summary(report, output_path)
    print(f"summary written to {output_path}")


if __name__ == "__main__":
    main()

