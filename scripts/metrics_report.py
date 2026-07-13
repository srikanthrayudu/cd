"""
scripts/metrics_report.py — Recompute metrics and regenerate all evaluation artefacts.

Reads execution logs from results/, recounts IR files in each staging directory,
then writes evaluation/metrics.json, metrics.csv, metrics.png, results/summary.md,
and results/triage.json.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import cfg, ProjectPaths
from src.metrics import compute_metrics, write_bar_chart, write_csv, write_metrics
from src.reporting import build_summary, write_summary
from src.triage import build_triage, write_triage


def main() -> None:
    paths      = ProjectPaths.from_config(cfg, ROOT)
    file_names = cfg.reporting.files
    paths.ensure_dirs()

    # Count IR files currently on disk as a proxy for pipeline counts.
    # The canonical numbers come from run_manifest.json when present;
    # compute_metrics will read the manifest automatically.
    counts = {
        "generated": len(list(paths.generated_dir.glob("*.ll"))),
        "mutated":   len(list(paths.mutated_dir.glob("*.ll"))),
        "valid":     len(list(paths.valid_dir.glob("*.ll"))),
        "invalid":   len(list(paths.invalid_dir.glob("*.ll"))),
    }

    metrics = compute_metrics(paths.results_dir, counts)
    write_metrics(metrics,   paths.evaluation_dir / file_names["metrics_json"])
    write_csv(metrics,       paths.evaluation_dir / file_names["metrics_csv"])
    write_bar_chart(metrics, paths.evaluation_dir / file_names["metrics_png"])

    summary = build_summary(paths.results_dir, paths.evaluation_dir)
    write_summary(summary, paths.results_dir / file_names["summary"])

    triage = build_triage(paths.results_dir)
    write_triage(triage, paths.results_dir / file_names["triage"])

    print(
        f"metrics written → {paths.evaluation_dir / file_names['metrics_json']}\n"
        f"summary written → {paths.results_dir / file_names['summary']}\n"
        f"triage  written → {paths.results_dir / file_names['triage']}"
    )


if __name__ == "__main__":
    main()
