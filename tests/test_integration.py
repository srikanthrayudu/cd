"""
tests/test_integration.py — Integration smoke test for the full pipeline.

Runs run_pipeline() with gen_count=2 against a temp directory and asserts
that all expected output artefacts are created and well-formed.

This test does not require LLVM tools to be installed — the pipeline
degrades gracefully when they are absent.
"""
import json
import pytest
from pathlib import Path
from src.config import cfg, ProjectPaths
from src.pipeline import run_pipeline


@pytest.fixture(scope="module")
def pipeline_output(tmp_path_factory):
    """Run the pipeline once and return the paths object for all assertions."""
    root = tmp_path_factory.mktemp("pipeline_root")
    run_pipeline(root=root, gen_count=2, mut_per_file=1,
                 backend="template", model="", mode="generate")
    return ProjectPaths.from_config(cfg, root)


class TestPipelineOutputDirectories:
    def test_all_directories_exist(self, pipeline_output):
        paths = pipeline_output
        for attr in ("generated_dir", "mutated_dir", "valid_dir", "invalid_dir",
                     "logs_dir", "results_dir", "evaluation_dir",
                     "optimized_dir", "diffs_dir"):
            assert getattr(paths, attr).is_dir(), f"Missing directory: {attr}"


class TestRunManifest:
    def test_manifest_is_valid_json(self, pipeline_output):
        manifest_path = pipeline_output.results_dir / cfg.reporting.files["run_manifest"]
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert isinstance(data, dict)

    def test_manifest_has_required_keys(self, pipeline_output):
        manifest_path = pipeline_output.results_dir / cfg.reporting.files["run_manifest"]
        data = json.loads(manifest_path.read_text())
        for key in ("generated_at", "backend", "mode", "counts"):
            assert key in data, f"Missing key in manifest: {key}"

    def test_manifest_counts_are_non_negative(self, pipeline_output):
        manifest_path = pipeline_output.results_dir / cfg.reporting.files["run_manifest"]
        data = json.loads(manifest_path.read_text())
        counts = data.get("counts", {})
        for key in ("generated", "mutated", "valid", "invalid"):
            assert counts.get(key, 0) >= 0


class TestSummaryReport:
    def test_summary_md_exists(self, pipeline_output):
        summary = pipeline_output.results_dir / cfg.reporting.files["summary"]
        assert summary.exists()

    def test_summary_md_is_non_empty(self, pipeline_output):
        summary = pipeline_output.results_dir / cfg.reporting.files["summary"]
        assert summary.stat().st_size > 0

    def test_summary_md_has_headings(self, pipeline_output):
        summary = pipeline_output.results_dir / cfg.reporting.files["summary"]
        text = summary.read_text()
        assert "# Pipeline Summary" in text
        assert "## Totals" in text


class TestMetricsFiles:
    def test_metrics_json_is_valid(self, pipeline_output):
        metrics_path = pipeline_output.evaluation_dir / cfg.reporting.files["metrics_json"]
        assert metrics_path.exists()
        data = json.loads(metrics_path.read_text())
        assert isinstance(data, dict)
        assert "generated" in data
        assert "valid" in data

    def test_metrics_csv_has_two_lines(self, pipeline_output):
        csv_path = pipeline_output.evaluation_dir / cfg.reporting.files["metrics_csv"]
        assert csv_path.exists()
        lines = [ln for ln in csv_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2  # header + data row

    def test_metrics_values_are_non_negative(self, pipeline_output):
        metrics_path = pipeline_output.evaluation_dir / cfg.reporting.files["metrics_json"]
        data = json.loads(metrics_path.read_text())
        for key in ("generated", "mutated", "valid", "invalid",
                    "executed_total", "compile_failed", "timeouts"):
            assert data.get(key, 0) >= 0, f"Negative value for {key}"


class TestTriageFile:
    def test_triage_json_is_valid(self, pipeline_output):
        triage_path = pipeline_output.results_dir / cfg.reporting.files["triage"]
        assert triage_path.exists()
        data = json.loads(triage_path.read_text())
        assert "diffs_by_reason" in data
        assert "diffs_by_name" in data
        assert "samples" in data


class TestSingleFileMode:
    def test_single_file_pipeline(self, tmp_path):
        """Pipeline --file mode should work with a single handwritten IR file."""
        ir_file = tmp_path / "input.ll"
        ir_file.write_text(
            "define i32 @main() {\nentry:\n  ret i32 42\n}\n"
        )
        root = tmp_path / "run"
        run_pipeline(root=root, gen_count=0, mut_per_file=0,
                     backend="template", model="", mode="generate",
                     test_file=ir_file)
        paths = ProjectPaths.from_config(cfg, root)
        assert (paths.valid_dir / "input.ll").exists()
        summary = paths.results_dir / cfg.reporting.files["summary"]
        assert summary.exists()
