"""
tests/test_diff_test.py — Unit tests for src/diff_test.py
"""
import pytest
from src.diff_test import (
    compare_results,
    compare_optimized_ir,
    count_ir_instructions,
)
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


class TestCountIrInstructions:
    def test_counts_basic_instructions(self):
        ir = "  %x = add i32 1, 2\n  ret i32 %x\n"
        assert count_ir_instructions(ir) == 2

    def test_blank_lines_not_counted(self):
        ir = "\n  %x = add i32 1, 2\n\n  ret i32 %x\n\n"
        assert count_ir_instructions(ir) == 2

    def test_labels_not_counted(self):
        ir = "entry:\n  %x = add i32 1, 2\n  ret i32 %x\n"
        assert count_ir_instructions(ir) == 2

    def test_comments_not_counted(self):
        ir = "; this is a comment\n  %x = add i32 1, 2\n  ret i32 %x\n"
        assert count_ir_instructions(ir) == 2

    def test_define_line_not_counted(self):
        ir = "define i32 @main() {\nentry:\n  ret i32 0\n}\n"
        assert count_ir_instructions(ir) == 1

    def test_empty_string_returns_zero(self):
        assert count_ir_instructions("") == 0

    def test_longer_function(self):
        ir = (
            "define i32 @main() {\n"
            "entry:\n"
            "  %a = add i32 1, 2\n"
            "  %b = mul i32 %a, 3\n"
            "  %c = sub i32 %b, 1\n"
            "  ret i32 %c\n"
            "}\n"
        )
        assert count_ir_instructions(ir) == 4


class TestCompareOptimizedIr:
    _O0 = "define i32 @main() {\nentry:\n  %x = add i32 1, 2\n  ret i32 %x\n}\n"
    _O3 = "define i32 @main() {\nentry:\n  ret i32 3\n}\n"
    _SAME = "define i32 @main() {\nentry:\n  ret i32 42\n}\n"

    def test_identical_ir_is_flagged(self):
        r = compare_optimized_ir("f", self._SAME, self._SAME)
        assert r.identical is True
        assert r.unified_diff == ""

    def test_different_ir_produces_diff(self):
        r = compare_optimized_ir("f", self._O0, self._O3)
        assert r.identical is False
        assert "---" in r.unified_diff
        assert "+++" in r.unified_diff

    def test_diff_file_names_in_header(self):
        r = compare_optimized_ir("mymod", self._O0, self._O3)
        assert "mymod.O0.ll" in r.unified_diff
        assert "mymod.O3.ll" in r.unified_diff

    def test_name_preserved(self):
        r = compare_optimized_ir("xyz", self._SAME, self._SAME)
        assert r.name == "xyz"

    def test_instr_counts_computed(self):
        r = compare_optimized_ir("f", self._O0, self._O3)
        # O0 has 2 instructions (add + ret), O3 has 1 (ret)
        assert r.o0_instr_count == 2
        assert r.o3_instr_count == 1

    def test_instr_delta_positive_when_o3_shrinks(self):
        r = compare_optimized_ir("f", self._O0, self._O3)
        assert r.instr_delta == 1

    def test_instr_reduction_pct_correct(self):
        r = compare_optimized_ir("f", self._O0, self._O3)
        # 1 out of 2 instructions eliminated → 50 %
        assert abs(r.instr_reduction_pct - 50.0) < 0.1

    def test_zero_pct_when_ir_identical(self):
        r = compare_optimized_ir("f", self._SAME, self._SAME)
        assert r.instr_delta == 0
        assert r.instr_reduction_pct == 0.0
