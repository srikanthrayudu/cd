from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.replay import replay_failures, write_replay


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay failing IR cases.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()
    results = replay_failures(paths.valid_dir, paths.results_dir, limit=args.limit)
    output_path = paths.results_dir / "replay.json"
    write_replay(results, output_path)
    print(f"replay written to {output_path}")


if __name__ == "__main__":
    main()

