from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
from src.metrics import compute_metrics, write_bar_chart, write_csv, write_metrics
from src.reporting import build_summary, write_summary
from src.triage import build_triage, write_triage


def main() -> None:
    paths = ProjectPaths.from_root(Path.cwd())
    paths.ensure_dirs()
    counts = {
        "generated": len(list(paths.generated_dir.glob("*.ll"))),
        "mutated": len(list(paths.mutated_dir.glob("*.ll"))),
        "valid": len(list(paths.valid_dir.glob("*.ll"))),
        "invalid": len(list(paths.invalid_dir.glob("*.ll"))),
    }
    metrics = compute_metrics(paths.results_dir, counts)
    write_metrics(metrics, paths.evaluation_dir / "metrics.json")
    write_csv(metrics, paths.evaluation_dir / "metrics.csv")
    write_bar_chart(metrics, paths.evaluation_dir / "metrics.png")
    summary = build_summary(paths.results_dir, paths.evaluation_dir)
    write_summary(summary, paths.results_dir / "summary.md")
    triage = build_triage(paths.results_dir)
    write_triage(triage, paths.results_dir / "triage.json")
    print("metrics written")


if __name__ == "__main__":
    main()
