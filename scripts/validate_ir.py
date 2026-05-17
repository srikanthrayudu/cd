from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.validator import validate_directory


def main() -> None:
    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()
    valid_gen, invalid_gen = validate_directory(
        paths.generated_dir,
        paths.valid_dir,
        paths.invalid_dir,
    )
    valid_mut, invalid_mut = validate_directory(
        paths.mutated_dir,
        paths.valid_dir,
        paths.invalid_dir,
    )
    print(f"valid={valid_gen + valid_mut} invalid={invalid_gen + invalid_mut}")


if __name__ == "__main__":
    main()
