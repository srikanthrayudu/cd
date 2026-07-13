"""
scripts/summary_report.py — Re-generate results/summary.md from existing pipeline artefacts.

Run this after the pipeline has completed to refresh the report without
re-executing any IR files.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.reporting import build_summary, write_summary


def main() -> None:
    paths       = ProjectPaths.from_config(cfg, ROOT)
    output_path = paths.results_dir / cfg.reporting.files["summary"]

    report = build_summary(paths.results_dir, paths.evaluation_dir)
    write_summary(report, output_path)
    print(f"summary written → {output_path}")


if __name__ == "__main__":
    main()
