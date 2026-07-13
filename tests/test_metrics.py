"""
tests/test_metrics.py — Unit tests for src/metrics.py
"""
import json
import pytest
from pathlib import Path
from src.metrics import compute_metrics, write_metrics, write_csv, Metrics


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _base_counts() -> dict:
    return {"generated": 5, "mutated": 3, "valid": 7, "invalid": 1}


class TestComputeMetrics:
    def test_counts_from_dict(self, tmp_path):
        (tmp_path / "executions.jsonl").write_text("")
        (tmp_path / "diffs.jsonl").write_text("")
        (tmp_path / "skipped_exec.jsonl").write_text("")
        m = compute_metrics(tmp_path, _base_counts())
        assert m.generated == 5
        assert m.mutated   == 3
        assert m.valid     == 7
        assert m.invalid   == 1

    def test_zero_metrics_on_empty_logs(self, tmp_path):
        for name in ("executions.jsonl", "diffs.jsonl", "skipped_exec.jsonl"):
            (tmp_path / name).write_text("")
        m = compute_metrics(tmp_path, _base_counts())
        assert m.executed_total == 0
        assert m.diffs          == 0
        assert m.skipped_exec   == 0

    def test_binary_sizes_computed(self, tmp_path):
        rows = [
            {"name": "f", "mode": "O0", "binary_size": 1000, "skipped": False, "reason": "ok"},
            {"name": "f", "mode": "O3", "binary_size":  400, "skipped": False, "reason": "ok"},
        ]
        _write_jsonl(tmp_path / "executions.jsonl", rows)
        (tmp_path / "diffs.jsonl").write_text("")
        (tmp_path / "skipped_exec.jsonl").write_text("")
        m = compute_metrics(tmp_path, _base_counts())
        assert m.paired_binary_cases == 1
        assert m.binary_savings      == 600
        assert abs(m.binary_reduction_pct - 60.0) < 0.01

    def test_compile_failed_counted(self, tmp_path):
        rows = [{"name": "x", "mode": "O0", "reason": "compile_failed",
                 "skipped": False, "binary_size": None}]
        _write_jsonl(tmp_path / "executions.jsonl", rows)
        (tmp_path / "diffs.jsonl").write_text("")
        (tmp_path / "skipped_exec.jsonl").write_text("")
        m = compute_metrics(tmp_path, _base_counts())
        assert m.compile_failed == 1

    def test_missing_files_dont_crash(self, tmp_path):
        # No JSONL files at all — should return zeros without raising
        m = compute_metrics(tmp_path, _base_counts())
        assert m.executed_total == 0


class TestWriteMetrics:
    def test_writes_valid_json(self, tmp_path):
        m = Metrics(
            generated=1, mutated=1, valid=1, invalid=0,
            executed_total=3, executed_lli=1, executed_clang=2,
            compile_failed=0, timeouts=0, diffs=0, skipped_exec=0,
            total_o0_size=100, total_o3_size=50,
            paired_binary_cases=1, binary_savings=50, binary_reduction_pct=50.0,
        )
        out = tmp_path / "metrics.json"
        write_metrics(m, out)
        data = json.loads(out.read_text())
        assert data["generated"] == 1
        assert data["binary_reduction_pct"] == 50.0

    def test_write_csv_has_header_and_row(self, tmp_path):
        m = Metrics(
            generated=2, mutated=2, valid=2, invalid=0,
            executed_total=6, executed_lli=2, executed_clang=4,
            compile_failed=0, timeouts=0, diffs=0, skipped_exec=0,
            total_o0_size=200, total_o3_size=100,
            paired_binary_cases=2, binary_savings=100, binary_reduction_pct=50.0,
        )
        out = tmp_path / "metrics.csv"
        write_csv(m, out)
        lines = out.read_text().splitlines()
        assert len(lines) == 2          # header + one data row
        assert "generated" in lines[0]  # header contains field name
        assert "2" in lines[1]          # data row contains value
