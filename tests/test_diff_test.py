"""
tests/test_diff_test.py — Unit tests for src/diff_test.py
"""
import pytest
from src.diff_test import compare_results, compare_optimized_ir
from src.executor import ExecutionResult


def _result(name="f", mode="O0", exit_code=0, stdout="", stderr="", skipped=False):
    return ExecutionResult(
        name=name, mode=mode, exit_code=exit_code,
        stdout=stdout, stderr=stderr, skipped=skipped, reason="ok",
    )


class TestCompareResults:
    def test_identical_results_match(self):
        r = compare_results("f", _result(exit_code=0, stdout="hi"), _result(exit_code=0, stdout="hi"))
        assert r.match is True
        assert r.reason == "match"

    def test_exit_code_mismatch_detected(self):
        r = compare_results("f", _result(exit_code=0), _result(exit_code=1))
        assert r.match is False
        assert r.reason == "exit_code_mismatch"

    def test_stdout_mismatch_detected(self):
        r = compare_results("f", _result(stdout="a"), _result(stdout="b"))
        assert r.match is False
        assert r.reason == "stdout_mismatch"

    def test_stderr_mismatch_detected(self):
        r = compare_results("f",
                            _result(stdout="x", stderr="warn"),
                            _result(stdout="x", stderr=""))
        assert r.match is False
        assert r.reason == "stderr_mismatch"

    def test_exit_codes_recorded(self):
        r = compare_results("f", _result(exit_code=2), _result(exit_code=3))
        assert r.o0_exit == 2
        assert r.o3_exit == 3

    def test_name_preserved(self):
        r = compare_results("myfile", _result(), _result())
        assert r.name == "myfile"


class TestCompareOptimizedIr:
    _O0 = "define i32 @main() {\nentry:\n  ret i32 42\n}\n"
    _O3 = "define i32 @main() {\nentry:\n  ret i32 42\n}\n"
    _O3_DIFF = "define i32 @main() {\nentry:\n  ret i32 0\n}\n"

    def test_identical_ir_is_flagged(self):
        r = compare_optimized_ir("f", self._O0, self._O3)
        assert r.identical is True
        assert r.unified_diff == ""

    def test_different_ir_produces_diff(self):
        r = compare_optimized_ir("f", self._O0, self._O3_DIFF)
        assert r.identical is False
        assert "---" in r.unified_diff
        assert "+++" in r.unified_diff

    def test_diff_file_names_in_header(self):
        r = compare_optimized_ir("mymod", self._O0, self._O3_DIFF)
        assert "mymod.O0.ll" in r.unified_diff
        assert "mymod.O3.ll" in r.unified_diff

    def test_name_preserved(self):
        r = compare_optimized_ir("xyz", self._O0, self._O3)
        assert r.name == "xyz"
