"""
tests/test_feedback_history_reporting.py — Unit tests for the feedback loop,
run history tracking, and the updated reporting module.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


_SIMPLE_IR = """\
define i32 @main() {
entry:
  %v0 = add i32 1, 2
  ret i32 %v0
}
"""


# ---------------------------------------------------------------------------
# Feedback loop: _collect_diff_seeds
# ---------------------------------------------------------------------------

class TestCollectDiffSeeds:
    from src.pipeline import _collect_diff_seeds

    def test_copies_diffing_file_to_seeds_dir(self, tmp_path):
        from src.pipeline import _collect_diff_seeds

        valid_dir  = tmp_path / "valid_ir"
        seeds_dir  = tmp_path / "feedback_seeds"
        valid_dir.mkdir()
        (valid_dir / "foo_mut0.ll").write_text(_SIMPLE_IR)

        diffs_path = tmp_path / "diffs.jsonl"
        _write_jsonl(diffs_path, [{"name": "foo_mut0", "match": False, "reason": "exit_code_mismatch"}])

        n = _collect_diff_seeds(diffs_path, valid_dir, seeds_dir)
        assert n == 1
        assert (seeds_dir / "seed_foo_mut0.ll").exists()

    def test_skips_files_not_in_valid_dir(self, tmp_path):
        from src.pipeline import _collect_diff_seeds

        valid_dir  = tmp_path / "valid_ir"
        seeds_dir  = tmp_path / "feedback_seeds"
        valid_dir.mkdir()
        # No .ll file written — should not crash

        diffs_path = tmp_path / "diffs.jsonl"
        _write_jsonl(diffs_path, [{"name": "missing_file", "match": False, "reason": "stdout_mismatch"}])

        n = _collect_diff_seeds(diffs_path, valid_dir, seeds_dir)
        assert n == 0

    def test_returns_zero_when_diffs_empty(self, tmp_path):
        from src.pipeline import _collect_diff_seeds

        valid_dir  = tmp_path / "valid_ir"
        seeds_dir  = tmp_path / "feedback_seeds"
        valid_dir.mkdir()

        diffs_path = tmp_path / "diffs.jsonl"
        diffs_path.write_text("")

        n = _collect_diff_seeds(diffs_path, valid_dir, seeds_dir)
        assert n == 0

    def test_returns_zero_when_diffs_missing(self, tmp_path):
        from src.pipeline import _collect_diff_seeds

        valid_dir  = tmp_path / "valid_ir"
        seeds_dir  = tmp_path / "feedback_seeds"
        valid_dir.mkdir()

        n = _collect_diff_seeds(tmp_path / "nonexistent.jsonl", valid_dir, seeds_dir)
        assert n == 0

    def test_deduplicates_same_name(self, tmp_path):
        from src.pipeline import _collect_diff_seeds

        valid_dir  = tmp_path / "valid_ir"
        seeds_dir  = tmp_path / "feedback_seeds"
        valid_dir.mkdir()
        (valid_dir / "bar_mut0.ll").write_text(_SIMPLE_IR)

        diffs_path = tmp_path / "diffs.jsonl"
        _write_jsonl(diffs_path, [
            {"name": "bar_mut0", "match": False, "reason": "exit_code_mismatch"},
            {"name": "bar_mut0", "match": False, "reason": "stdout_mismatch"},
        ])

        n = _collect_diff_seeds(diffs_path, valid_dir, seeds_dir)
        assert n == 1  # deduplicated


# ---------------------------------------------------------------------------
# Run history: _append_run_history
# ---------------------------------------------------------------------------

class TestAppendRunHistory:
    def test_creates_history_file_on_first_call(self, tmp_path):
        from src.pipeline import _append_run_history
        from src.metrics import Metrics

        history_path = tmp_path / "history.jsonl"
        m = Metrics(
            generated=5, mutated=3, valid=4, invalid=1,
            executed_total=12, executed_lli=4, executed_clang=8,
            compile_failed=0, timeouts=0, diffs=2, skipped_exec=0,
            total_o0_size=1000, total_o3_size=400,
            paired_binary_cases=4, binary_savings=600, binary_reduction_pct=60.0,
            strategy_diff_rates={"deep_cfg": 50.0},
        )
        _append_run_history(history_path, m, {"generated": 5, "mutated": 3, "valid": 4, "invalid": 1})
        assert history_path.exists()

    def test_appends_valid_json_line(self, tmp_path):
        from src.pipeline import _append_run_history
        from src.metrics import Metrics

        history_path = tmp_path / "history.jsonl"
        m = Metrics(
            generated=2, mutated=2, valid=2, invalid=0,
            executed_total=6, executed_lli=2, executed_clang=4,
            compile_failed=0, timeouts=0, diffs=1, skipped_exec=0,
            total_o0_size=500, total_o3_size=200,
            paired_binary_cases=2, binary_savings=300, binary_reduction_pct=60.0,
        )
        _append_run_history(history_path, m, {"generated": 2, "mutated": 2, "valid": 2, "invalid": 0})
        lines = history_path.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["diffs"] == 1
        assert record["generated"] == 2
        assert "timestamp" in record

    def test_multiple_calls_append_multiple_lines(self, tmp_path):
        from src.pipeline import _append_run_history
        from src.metrics import Metrics

        history_path = tmp_path / "history.jsonl"

        def _make_metrics(diffs: int) -> Metrics:
            return Metrics(
                generated=1, mutated=1, valid=1, invalid=0,
                executed_total=3, executed_lli=1, executed_clang=2,
                compile_failed=0, timeouts=0, diffs=diffs, skipped_exec=0,
                total_o0_size=100, total_o3_size=50,
                paired_binary_cases=1, binary_savings=50, binary_reduction_pct=50.0,
            )

        for d in (0, 1, 3):
            _append_run_history(history_path, _make_metrics(d),
                                {"generated": 1, "mutated": 1, "valid": 1, "invalid": 0})

        lines = history_path.read_text().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[2])["diffs"] == 3

    def test_strategy_diff_rates_recorded(self, tmp_path):
        from src.pipeline import _append_run_history
        from src.metrics import Metrics

        history_path = tmp_path / "history.jsonl"
        m = Metrics(
            generated=1, mutated=1, valid=1, invalid=0,
            executed_total=3, executed_lli=1, executed_clang=2,
            compile_failed=0, timeouts=0, diffs=0, skipped_exec=0,
            total_o0_size=100, total_o3_size=50,
            paired_binary_cases=1, binary_savings=50, binary_reduction_pct=50.0,
            strategy_diff_rates={"loop_insert": 33.3, "func_call": 0.0},
        )
        _append_run_history(history_path, m, {"generated": 1})
        record = json.loads(history_path.read_text().splitlines()[0])
        assert record["strategy_diff_rates"]["loop_insert"] == 33.3


# ---------------------------------------------------------------------------
# Reporting: _collect_instr_stats
# ---------------------------------------------------------------------------

class TestCollectInstrStats:
    def test_aggregates_from_o0_records(self):
        from src.reporting import _collect_instr_stats

        rows = [
            {"mode": "O0", "o0_instr_count": 10, "o3_instr_count": 4,
             "instr_delta": 6, "instr_reduction_pct": 60.0},
            {"mode": "O0", "o0_instr_count": 8, "o3_instr_count": 2,
             "instr_delta": 6, "instr_reduction_pct": 75.0},
            {"mode": "O3"},  # should be ignored
            {"mode": "lli"}, # should be ignored
        ]
        stats = _collect_instr_stats(rows)
        assert stats["total_o0_instructions"]  == 18
        assert stats["total_o3_instructions"]  == 6
        assert stats["total_instr_eliminated"] == 12
        assert abs(stats["avg_instr_reduction_pct"] - 67.5) < 0.1
        assert stats["max_instr_reduction_pct"] == 75.0
        assert stats["min_instr_reduction_pct"] == 60.0
        assert stats["files_with_instr_data"]   == 2

    def test_returns_empty_when_no_instr_data(self):
        from src.reporting import _collect_instr_stats

        rows = [
            {"mode": "O0", "binary_size": 500},  # no instr_count fields
            {"mode": "O3", "binary_size": 200},
        ]
        assert _collect_instr_stats(rows) == {}

    def test_returns_empty_for_empty_input(self):
        from src.reporting import _collect_instr_stats

        assert _collect_instr_stats([]) == {}


# ---------------------------------------------------------------------------
# Reporting: write_summary includes new sections
# ---------------------------------------------------------------------------

class TestWriteSummaryNewSections:
    def _make_report(self, **kwargs: Any):
        from src.reporting import SummaryReport
        defaults = dict(
            totals={}, diff_reasons={}, sample_diffs=[], notes=[],
            size_comparisons=[], metrics_snapshot={}, run_metadata={},
        )
        defaults.update(kwargs)
        return SummaryReport(**defaults)

    def test_instr_stats_section_present(self, tmp_path):
        from src.reporting import write_summary

        report = self._make_report(
            instr_stats={
                "total_o0_instructions": 100,
                "total_o3_instructions": 40,
                "total_instr_eliminated": 60,
                "avg_instr_reduction_pct": 60.0,
                "max_instr_reduction_pct": 75.0,
                "min_instr_reduction_pct": 45.0,
                "files_with_instr_data": 5,
            }
        )
        out = tmp_path / "summary.md"
        write_summary(report, out)
        content = out.read_text()
        assert "Instruction-Count Statistics" in content
        assert "100" in content  # total_o0_instructions

    def test_strategy_diff_rates_section_present(self, tmp_path):
        from src.reporting import write_summary

        report = self._make_report(
            strategy_diff_rates={"deep_cfg": 50.0, "loop_insert": 25.0}
        )
        out = tmp_path / "summary.md"
        write_summary(report, out)
        content = out.read_text()
        assert "Per-Strategy Diff Rates" in content
        assert "deep_cfg" in content
        assert "50.00%" in content

    def test_sections_absent_when_data_empty(self, tmp_path):
        from src.reporting import write_summary

        report = self._make_report()
        out = tmp_path / "summary.md"
        write_summary(report, out)
        content = out.read_text()
        assert "Instruction-Count Statistics" not in content
        assert "Per-Strategy Diff Rates"      not in content
