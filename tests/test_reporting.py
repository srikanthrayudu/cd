"""
tests/test_reporting.py — Unit tests for src/reporting.py
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from src.reporting import (
    build_summary,
    write_summary,
    SummaryReport,
    _collect_instr_stats,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _empty_results(tmp_path: Path) -> tuple[Path, Path]:
    """Create minimal empty results and evaluation dirs."""
    results = tmp_path / "results"
    eval_d  = tmp_path / "evaluation"
    results.mkdir()
    eval_d.mkdir()
    for name in ("executions.jsonl", "diffs.jsonl", "skipped_exec.jsonl"):
        (results / name).write_text("")
    (results / "run_manifest.json").write_text("{}")
    (eval_d / "metrics.json").write_text("{}")
    return results, eval_d


class TestBuildSummary:
    def test_empty_logs_return_valid_report(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        report = build_summary(results, eval_d)
        assert isinstance(report, SummaryReport)
        assert report.totals["executions"] == 0
        assert report.diff_reasons == {}
        assert report.sample_diffs == []

    def test_diff_reasons_counted(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        _write_jsonl(results / "diffs.jsonl", [
            {"name": "f1", "match": False, "reason": "exit_code_mismatch"},
            {"name": "f2", "match": False, "reason": "stdout_mismatch"},
            {"name": "f3", "match": False, "reason": "exit_code_mismatch"},
        ])
        report = build_summary(results, eval_d)
        assert report.diff_reasons["exit_code_mismatch"] == 2
        assert report.diff_reasons["stdout_mismatch"] == 1

    def test_size_comparisons_built(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        _write_jsonl(results / "executions.jsonl", [
            {"name": "f1", "mode": "O0", "binary_size": 1000, "skipped": False, "reason": "ok"},
            {"name": "f1", "mode": "O3", "binary_size":  400, "skipped": False, "reason": "ok"},
        ])
        report = build_summary(results, eval_d)
        assert len(report.size_comparisons) == 1
        assert report.size_comparisons[0]["savings"] == 600
        assert abs(report.size_comparisons[0]["reduction_pct"] - 60.0) < 0.01

    def test_instr_stats_collected(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        _write_jsonl(results / "executions.jsonl", [
            {"name": "f1", "mode": "O0",
             "o0_instr_count": 10, "o3_instr_count": 4,
             "instr_delta": 6, "instr_reduction_pct": 60.0,
             "skipped": False, "reason": "ok"},
        ])
        report = build_summary(results, eval_d)
        assert report.instr_stats.get("total_o0_instructions") == 10
        assert report.instr_stats.get("total_instr_eliminated") == 6

    def test_strategy_diff_rates_from_metrics(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        _write_json(eval_d / "metrics.json", {
            "strategy_diff_rates": {"deep_cfg": 50.0, "loop_insert": 25.0}
        })
        report = build_summary(results, eval_d)
        assert report.strategy_diff_rates["deep_cfg"] == 50.0

    def test_note_added_when_no_executions(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        report = build_summary(results, eval_d)
        assert any("No executions" in n for n in report.notes)

    def test_no_mismatch_note_added_when_no_diffs(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        _write_jsonl(results / "executions.jsonl", [
            {"name": "f1", "mode": "O0", "binary_size": 100, "skipped": False, "reason": "ok"},
        ])
        report = build_summary(results, eval_d)
        assert any("No mismatches" in n for n in report.notes)

    def test_sample_diffs_capped(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        rows = [{"name": f"f{i}", "match": False, "reason": "stdout_mismatch"}
                for i in range(20)]
        _write_jsonl(results / "diffs.jsonl", rows)
        report = build_summary(results, eval_d)
        # max_sample_diffs from config is 5
        assert len(report.sample_diffs) <= 5

    def test_run_metadata_from_manifest(self, tmp_path):
        results, eval_d = _empty_results(tmp_path)
        _write_json(results / "run_manifest.json", {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "backend": "template",
            "mode": "generate",
        })
        report = build_summary(results, eval_d)
        assert report.run_metadata.get("backend") == "template"


class TestWriteSummary:
    def _simple_report(self, **kwargs) -> SummaryReport:
        defaults = dict(
            totals={}, diff_reasons={}, sample_diffs=[], notes=[],
            size_comparisons=[], metrics_snapshot={}, run_metadata={},
        )
        defaults.update(kwargs)
        return SummaryReport(**defaults)

    def test_creates_markdown_file(self, tmp_path):
        out = tmp_path / "summary.md"
        write_summary(self._simple_report(), out)
        assert out.exists()
        assert "Pipeline Summary" in out.read_text()

    def test_totals_section_present(self, tmp_path):
        report = self._simple_report(totals={"executions": 42, "diffs": 3})
        out = tmp_path / "summary.md"
        write_summary(report, out)
        content = out.read_text()
        assert "Totals" in content
        assert "42" in content

    def test_diff_reasons_section(self, tmp_path):
        report = self._simple_report(diff_reasons={"stdout_mismatch": 7})
        out = tmp_path / "summary.md"
        write_summary(report, out)
        assert "stdout_mismatch" in out.read_text()

    def test_size_table_present(self, tmp_path):
        report = self._simple_report(size_comparisons=[{
            "name": "foo", "o0_size": 1000, "o3_size": 400,
            "savings": 600, "reduction_pct": 60.0, "direction": "smaller"
        }])
        out = tmp_path / "summary.md"
        write_summary(report, out)
        content = out.read_text()
        assert "foo" in content
        assert "1,000" in content

    def test_instr_stats_present(self, tmp_path):
        report = self._simple_report(instr_stats={
            "total_o0_instructions": 500,
            "total_o3_instructions": 200,
            "total_instr_eliminated": 300,
            "avg_instr_reduction_pct": 60.0,
            "max_instr_reduction_pct": 80.0,
            "min_instr_reduction_pct": 40.0,
            "files_with_instr_data": 10,
        })
        out = tmp_path / "summary.md"
        write_summary(report, out)
        content = out.read_text()
        assert "Instruction-Count Statistics" in content
        assert "500" in content

    def test_strategy_diff_rates_table(self, tmp_path):
        report = self._simple_report(
            strategy_diff_rates={"deep_cfg": 50.0, "opcode_swap": 10.0}
        )
        out = tmp_path / "summary.md"
        write_summary(report, out)
        content = out.read_text()
        assert "Per-Strategy Diff Rates" in content
        assert "deep_cfg" in content
        assert "50.00%" in content

    def test_run_metadata_section(self, tmp_path):
        report = self._simple_report(run_metadata={"backend": "template", "mode": "generate"})
        out = tmp_path / "summary.md"
        write_summary(report, out)
        assert "backend" in out.read_text()

    def test_executive_overview_present_when_size_data(self, tmp_path):
        report = self._simple_report(size_comparisons=[{
            "name": "x", "o0_size": 200, "o3_size": 100,
            "savings": 100, "reduction_pct": 50.0, "direction": "smaller"
        }])
        out = tmp_path / "summary.md"
        write_summary(report, out)
        assert "Executive Overview" in out.read_text()
