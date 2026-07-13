"""
main.py — Command-line entry point for the LLVM IR Differential Testing pipeline.

Usage examples
--------------
# Full pipeline with default settings from config.yaml:
    python3 main.py

# Override generation count and backend at the command line:
    python3 main.py --gen-count 20 --backend openai --model gpt-4o-mini

# Test a single IR file (skip generation/mutation):
    python3 main.py --file test.ll

All default values are read from config.yaml via src/config.py so that
changing a setting in one place takes effect everywhere.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import cfg
from src.pipeline import run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    gen = cfg.generation
    mut = cfg.mutation

    parser = argparse.ArgumentParser(
        prog="python3 main.py",
        description="LLVM IR Differential Testing Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Generation
    parser.add_argument(
        "--gen-count",
        type=int,
        default=gen.count,
        metavar="N",
        help="Number of IR files to generate.",
    )
    parser.add_argument(
        "--backend",
        choices=["template", "openai"],
        default=gen.backend,
        help="IR generation backend.",
    )
    parser.add_argument(
        "--model",
        default=gen.model,
        help="LLM model name (only used when --backend is openai).",
    )
    parser.add_argument(
        "--mode",
        choices=["generate", "mutate"],
        default=gen.mode,
        help="Generation mode.",
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Directory of *.ll seed files used in mutate mode.",
    )

    # Mutation
    parser.add_argument(
        "--mut-per-file",
        type=int,
        default=mut.per_file,
        metavar="N",
        help="Number of mutations to produce per input IR file.",
    )

    # Single-file mode
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "Skip generation/mutation and test a single *.ll file instead. "
            "The file is copied into valid_ir/ and the execution/analysis "
            "steps run on it alone."
        ),
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    # Validate --file early so the user gets a clear error before any work
    if args.file is not None and not Path(args.file).exists():
        parser.error(f"--file: path does not exist: {args.file}")

    run_pipeline(
        root         = Path.cwd(),
        gen_count    = args.gen_count,
        mut_per_file = args.mut_per_file,
        backend      = args.backend,
        model        = args.model,
        mode         = args.mode,
        seed_dir     = args.seed_dir,
        test_file    = args.file,
    )


if __name__ == "__main__":
    sys.exit(main())
