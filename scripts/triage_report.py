"""
scripts/triage_report.py — Re-generate results/triage.json from existing diffs.jsonl.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.triage import build_triage, write_triage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Re-generate the triage report from existing pipeline artefacts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of raw diff records to include as samples.",
    )
    return parser


def main() -> None:
    args        = _build_parser().parse_args()
    paths       = ProjectPaths.from_config(cfg, ROOT)
    output_path = paths.results_dir / cfg.reporting.files["triage"]

    report = build_triage(paths.results_dir, sample_limit=args.sample_limit)
    write_triage(report, output_path)
    print(f"triage written → {output_path}")


if __name__ == "__main__":
    main()
