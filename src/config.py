from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    dataset_dir: Path
    generated_dir: Path
    mutated_dir: Path
    valid_dir: Path
    invalid_dir: Path
    logs_dir: Path
    results_dir: Path
    evaluation_dir: Path
    optimized_dir: Path
    diffs_dir: Path

    @staticmethod
    def from_root(root: Path) -> "ProjectPaths":
        return ProjectPaths(
            root=root,
            dataset_dir=root / "dataset",
            generated_dir=root / "generated_ir",
            mutated_dir=root / "mutated_ir",
            valid_dir=root / "valid_ir",
            invalid_dir=root / "invalid_ir",
            logs_dir=root / "logs",
            results_dir=root / "results",
            evaluation_dir=root / "evaluation",
            optimized_dir=root / "results" / "optimized_ir",
            diffs_dir=root / "results" / "code_diffs",
        )

    def ensure_dirs(self) -> None:
        for path in (
            self.dataset_dir,
            self.generated_dir,
            self.mutated_dir,
            self.valid_dir,
            self.invalid_dir,
            self.logs_dir,
            self.results_dir,
            self.evaluation_dir,
            self.optimized_dir,
            self.diffs_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

