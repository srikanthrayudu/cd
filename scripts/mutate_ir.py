from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.mutator import MutationConfig, mutate_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Mutate LLVM IR files.")
    parser.add_argument("--per-file", type=int, default=2)
    parser.add_argument("--input-dir", type=str, default=None)
    args = parser.parse_args()

    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()
    input_dir = Path(args.input_dir) if args.input_dir else paths.dataset_dir
    created = mutate_files(input_dir, paths.mutated_dir, MutationConfig(per_file=args.per_file))
    print(f"mutated={len(created)}")


if __name__ == "__main__":
    main()
