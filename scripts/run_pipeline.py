from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full IR pipeline.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--per-file", type=int, default=2)
    parser.add_argument("--backend", type=str, default="template")
    parser.add_argument("--model", type=str, default="gpt-4o-mini")
    parser.add_argument("--mode", type=str, default="generate", choices=["generate", "mutate"])
    parser.add_argument("--seed-dir", type=str, default=None)
    args = parser.parse_args()

    run_pipeline(
        Path.cwd(),
        gen_count=args.count,
        mut_per_file=args.per_file,
        backend=args.backend,
        model=args.model,
        mode=args.mode,
        seed_dir=Path(args.seed_dir) if args.seed_dir else None,
    )


if __name__ == "__main__":
    main()
