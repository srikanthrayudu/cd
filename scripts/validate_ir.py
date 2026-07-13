"""
scripts/validate_ir.py — Validate all IR files in generated_ir/ and mutated_ir/.

Valid files are moved to valid_ir/; invalid ones to invalid_ir/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.validator import validate_directory


def main() -> None:
    paths = ProjectPaths.from_config(cfg, ROOT)
    paths.ensure_dirs()

    valid_gen,  invalid_gen  = validate_directory(paths.generated_dir, paths.valid_dir, paths.invalid_dir)
    valid_mut,  invalid_mut  = validate_directory(paths.mutated_dir,   paths.valid_dir, paths.invalid_dir)

    total_valid   = valid_gen   + valid_mut
    total_invalid = invalid_gen + invalid_mut
    print(f"valid={total_valid}  invalid={total_invalid}  valid_dir={paths.valid_dir}")


if __name__ == "__main__":
    main()
