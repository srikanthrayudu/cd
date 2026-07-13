"""
scripts/replay_failures.py — Re-execute IR files that previously produced diffs.

Reads failure names from triage.json (or diffs.jsonl as a fallback),
re-runs those files through lli + clang, and writes results/replay.json.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.replay import replay_failures, write_replay


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay IR files that had differential failures.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of failures to replay.",
    )
    return parser


def main() -> None:
    args        = _build_parser().parse_args()
    paths       = ProjectPaths.from_config(cfg, ROOT)
    output_path = paths.results_dir / "replay.json"

    results = replay_failures(paths.valid_dir, paths.results_dir, limit=args.limit)
    write_replay(results, output_path)
    print(f"replayed={len(results)}  output={output_path}")


if __name__ == "__main__":
    main()
