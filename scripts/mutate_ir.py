"""
scripts/mutate_ir.py — Mutate an existing IR directory.

Reads *.ll files from an input directory, applies mutation strategies, and
writes variants to mutated_ir/.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.mutator import mutate_files


def _build_parser() -> argparse.ArgumentParser:
    mut = cfg.mutation
    parser = argparse.ArgumentParser(
        description="Mutate LLVM IR files in a directory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Source directory of *.ll files (default: dataset/).",
    )
    parser.add_argument(
        "--per-file",
        type=int,
        default=mut.per_file,
        metavar="N",
        help="Number of mutations to produce per source file.",
    )
    return parser


def main() -> None:
    args  = _build_parser().parse_args()
    paths = ProjectPaths.from_config(cfg, ROOT)
    paths.ensure_dirs()

    input_dir = args.input_dir if args.input_dir else paths.dataset_dir
    created   = mutate_files(
        input_dir  = input_dir,
        output_dir = paths.mutated_dir,
        per_file   = args.per_file,
        seed       = cfg.mutation.seed,
    )
    print(f"mutated={len(created)}  dir={paths.mutated_dir}")


if __name__ == "__main__":
    main()
