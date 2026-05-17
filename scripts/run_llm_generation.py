from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.llm_generator import GenerationConfig, write_generated_ir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LLVM IR (template-based).")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--backend", type=str, default="template")
    parser.add_argument("--model", type=str, default="gpt-4o-mini")
    parser.add_argument("--mode", type=str, default="generate", choices=["generate", "mutate"])
    parser.add_argument("--seed-dir", type=str, default=None)
    args = parser.parse_args()

    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()
    created = write_generated_ir(
        paths.generated_dir,
        GenerationConfig(
            count=args.count,
            backend=args.backend,
            model=args.model,
            mode=args.mode,
            seed_dir=Path(args.seed_dir) if args.seed_dir else None,
        ),
    )
    print(f"generated={len(created)}")


if __name__ == "__main__":
    main()
