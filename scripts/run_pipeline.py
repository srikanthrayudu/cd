"""
scripts/run_pipeline.py — Thin CLI wrapper around the full pipeline.

Equivalent to running ``python3 main.py`` from the project root, but
callable as a standalone script from the scripts/ directory.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the project root importable when this script is run directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg
from src.pipeline import run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    gen = cfg.generation
    mut = cfg.mutation
    parser = argparse.ArgumentParser(
        description="Run the full LLVM IR differential testing pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--gen-count",    type=int,   default=gen.count,   metavar="N",   help="Number of IR files to generate.")
    parser.add_argument("--mut-per-file", type=int,   default=mut.per_file, metavar="N",  help="Mutations per dataset file.")
    parser.add_argument("--backend",      default=gen.backend, choices=["template", "openai"], help="Generation backend.")
    parser.add_argument("--model",        default=gen.model,   help="LLM model (openai backend only).")
    parser.add_argument("--mode",         default=gen.mode,    choices=["generate", "mutate"], help="Generation mode.")
    parser.add_argument("--seed-dir",     type=Path,  default=None, metavar="DIR", help="Seed directory for mutate mode.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    run_pipeline(
        root         = ROOT,
        gen_count    = args.gen_count,
        mut_per_file = args.mut_per_file,
        backend      = args.backend,
        model        = args.model,
        mode         = args.mode,
        seed_dir     = args.seed_dir,
    )


if __name__ == "__main__":
    main()
