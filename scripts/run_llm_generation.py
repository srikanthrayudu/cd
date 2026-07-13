"""
scripts/run_llm_generation.py — Generate IR only (no mutation or validation).

Writes *.ll files to the generated_ir/ directory and prints a count.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.ir_generator import write_generated_ir


def _build_parser() -> argparse.ArgumentParser:
    gen = cfg.generation
    parser = argparse.ArgumentParser(
        description="Generate LLVM IR files without running the full pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--gen-count", type=int,  default=gen.count,   metavar="N",   help="Number of files to generate.")
    parser.add_argument("--backend",   default=gen.backend, choices=["template", "openai"], help="Generation backend.")
    parser.add_argument("--model",     default=gen.model,   help="LLM model (openai backend only).")
    parser.add_argument("--mode",      default=gen.mode,    choices=["generate", "mutate"], help="Generation mode.")
    parser.add_argument("--seed-dir",  type=Path,  default=None, metavar="DIR", help="Seed directory for mutate mode.")
    return parser


def main() -> None:
    args  = _build_parser().parse_args()
    paths = ProjectPaths.from_config(cfg, ROOT)
    paths.ensure_dirs()

    created = write_generated_ir(
        output_dir = paths.generated_dir,
        count      = args.gen_count,
        seed       = cfg.generation.seed,
        backend    = args.backend,
        model      = args.model,
        mode       = args.mode,
        seed_dir   = args.seed_dir,
    )
    print(f"generated={len(created)}  dir={paths.generated_dir}")


if __name__ == "__main__":
    main()
