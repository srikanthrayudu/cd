"""
tests/test_replay.py — Unit tests for src/replay.py
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from src.replay import (
    replay_failures,
    write_replay,
    _iter_failure_names,
    _resolve_ir_path,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class TestReplayFailures:
    def test_iter_failure_names_from_triage(self, tmp_path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        
        # Scenario 1: triage.json exists and has samples
        triage_path = results_dir / "triage.json"
        _write_json(triage_path, {
            "samples": [
                {"name": "fail_1", "reason": "exit_code_mismatch"},
                {"name": "fail_2", "reason": "stdout_mismatch"},
            ]
        })
        
        names = list(_iter_failure_names(results_dir))
        assert names == ["fail_1", "fail_2"]

    def test_iter_failure_names_fallback_to_diffs(self, tmp_path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        
        # Scenario 2: triage.json is empty/missing, diffs.jsonl exists
        diffs_path = results_dir / "diffs.jsonl"
        _write_jsonl(diffs_path, [
            {"name": "fail_3", "reason": "exit_code_mismatch"},
            {"name": "fail_4", "reason": "stdout_mismatch"},
        ])
        
        names = list(_iter_failure_names(results_dir))
        assert names == ["fail_3", "fail_4"]

    def test_resolve_ir_path_exact(self, tmp_path):
        valid_dir = tmp_path / "valid"
        valid_dir.mkdir()
        
        ir_file = valid_dir / "foo.ll"
        ir_file.write_text("define i32 @main() { ret i32 0 }")
        
        resolved = _resolve_ir_path(valid_dir, "foo")
        assert resolved == ir_file

    def test_resolve_ir_path_glob_fallback(self, tmp_path):
        valid_dir = tmp_path / "valid"
        valid_dir.mkdir()
        
        ir_file = valid_dir / "foo_mut0.ll"
        ir_file.write_text("define i32 @main() { ret i32 0 }")
        
        resolved = _resolve_ir_path(valid_dir, "foo_mut0")
        assert resolved == ir_file

    def test_resolve_ir_path_not_found(self, tmp_path):
        valid_dir = tmp_path / "valid"
        valid_dir.mkdir()
        
        resolved = _resolve_ir_path(valid_dir, "missing")
        assert resolved is None

    def test_replay_failures_limit(self, tmp_path):
        valid_dir = tmp_path / "valid"
        valid_dir.mkdir()
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        
        # Create test IR files
        for i in range(1, 4):
            (valid_dir / f"fail_{i}.ll").write_text("define i32 @main() { ret i32 0 }")
            
        _write_jsonl(results_dir / "diffs.jsonl", [
            {"name": "fail_1", "reason": "exit_code_mismatch"},
            {"name": "fail_2", "reason": "stdout_mismatch"},
            {"name": "fail_3", "reason": "exit_code_mismatch"},
        ])
        
        # Limit to 2 replays
        replays = replay_failures(valid_dir, results_dir, limit=2)
        assert len(replays) == 2
        assert replays[0].name == "fail_1"
        assert replays[1].name == "fail_2"

    def test_write_replay(self, tmp_path):
        from src.replay import ReplayResult
        
        output_path = tmp_path / "replay.json"
        results = [
            ReplayResult(name="fail_1", path="path/to/fail_1.ll", lli={}, o0={}, o3={})
        ]
        
        write_replay(results, output_path)
        assert output_path.exists()
        
        data = json.loads(output_path.read_text())
        assert len(data) == 1
        assert data[0]["name"] == "fail_1"
