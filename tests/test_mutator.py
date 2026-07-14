"""
tests/test_mutator.py — Unit tests for src/mutator.py

Tests each mutation strategy in isolation, then tests the file-level
mutate_files function.
"""
import random
import pytest
from pathlib import Path
from src.mutator import (
    _strategy_opcode_swap,
    _strategy_insert_dead_code,
    _strategy_block_split,
    _strategy_cond_phi,
    _strategy_const_tweak,
    _strategy_loop_insert,
    _strategy_func_call,
    _strategy_global_var,
    _strategy_vector_ops,
    _mutate_text,
    mutate_files,
)

# Minimal valid IR used across multiple tests
_SIMPLE_IR = """\
define i32 @main() {
entry:
  %v0 = add i32 1, 2
  ret i32 %v0
}
"""


class TestOpcodeSwap:
    def test_replaces_add_with_sub(self):
        ir  = "  %x = add i32 1, 2\n"
        rng = random.Random(0)
        out = _strategy_opcode_swap(ir, rng)
        assert " sub " in out

    def test_returns_unchanged_if_no_match(self):
        ir  = "  ret i32 0\n"
        rng = random.Random(0)
        assert _strategy_opcode_swap(ir, rng) == ir

    def test_result_ends_with_newline(self):
        rng = random.Random(0)
        out = _strategy_opcode_swap(_SIMPLE_IR, rng)
        assert out.endswith("\n")


class TestInsertDeadCode:
    def test_inserts_dead_instruction_after_entry(self):
        rng = random.Random(42)
        out = _strategy_insert_dead_code(_SIMPLE_IR, rng)
        assert "%dead_" in out

    def test_does_nothing_without_entry_label(self):
        ir  = "define i32 @f() {\n  ret i32 0\n}\n"
        rng = random.Random(0)
        out = _strategy_insert_dead_code(ir, rng)
        assert "ret i32 0" in out

    def test_result_is_valid_structure(self):
        rng = random.Random(7)
        out = _strategy_insert_dead_code(_SIMPLE_IR, rng)
        assert "define i32 @main" in out
        assert "ret i32" in out


class TestBlockSplit:
    def test_splits_entry_into_two_blocks(self):
        rng = random.Random(0)
        out = _strategy_block_split(_SIMPLE_IR, rng)
        assert "br label %exit" in out
        assert "exit:" in out

    def test_no_split_when_branch_already_present(self):
        ir = (
            "define i32 @main() {\n"
            "entry:\n"
            "  br label %done\n"
            "done:\n"
            "  ret i32 0\n"
            "}\n"
        )
        rng = random.Random(0)
        out = _strategy_block_split(ir, rng)
        assert out == ir

    def test_return_value_preserved(self):
        rng = random.Random(0)
        out = _strategy_block_split(_SIMPLE_IR, rng)
        assert "ret i32 %v0" in out


class TestCondPhi:
    def test_inserts_phi_node(self):
        rng = random.Random(0)
        out = _strategy_cond_phi(_SIMPLE_IR, rng)
        assert "phi i32" in out

    def test_result_ends_with_newline(self):
        rng = random.Random(0)
        out = _strategy_cond_phi(_SIMPLE_IR, rng)
        assert out.endswith("\n")


class TestConstTweak:
    def test_changes_an_integer_literal(self):
        rng = random.Random(1)
        out = _strategy_const_tweak(_SIMPLE_IR, rng)
        assert out != _SIMPLE_IR

    def test_no_change_when_no_integer_found(self):
        ir  = "define i32 @main() {\nentry:\n  ret i32 %x\n}\n"
        rng = random.Random(0)
        assert _strategy_const_tweak(ir, rng) == ir


# ---------------------------------------------------------------------------
# New strategy tests
# ---------------------------------------------------------------------------

class TestLoopInsert:
    def test_inserts_loop_header(self):
        rng = random.Random(0)
        out = _strategy_loop_insert(_SIMPLE_IR, rng)
        assert "loop_" in out
        assert "phi i32" in out

    def test_loop_has_exit_block(self):
        rng = random.Random(5)
        out = _strategy_loop_insert(_SIMPLE_IR, rng)
        assert "loop_exit_" in out

    def test_skipped_when_cfg_already_has_branch(self):
        ir = (
            "define i32 @main() {\n"
            "entry:\n"
            "  br label %done\n"
            "done:\n"
            "  ret i32 0\n"
            "}\n"
        )
        rng = random.Random(0)
        out = _strategy_loop_insert(ir, rng)
        assert out == ir  # untouched because CFG already has control flow

    def test_result_ends_with_newline(self):
        rng = random.Random(3)
        out = _strategy_loop_insert(_SIMPLE_IR, rng)
        assert out.endswith("\n")

    def test_original_define_preserved(self):
        rng = random.Random(7)
        out = _strategy_loop_insert(_SIMPLE_IR, rng)
        assert "define i32 @main" in out


class TestFuncCall:
    def test_inserts_helper_function(self):
        rng = random.Random(0)
        out = _strategy_func_call(_SIMPLE_IR, rng)
        assert "@helper_" in out

    def test_inserts_call_instruction(self):
        rng = random.Random(0)
        out = _strategy_func_call(_SIMPLE_IR, rng)
        assert "call i32 @helper_" in out

    def test_skipped_for_multi_function_modules(self):
        ir = (
            "define i32 @helper(i32 %x) {\n  ret i32 %x\n}\n"
            "define i32 @main() {\nentry:\n  ret i32 0\n}\n"
        )
        rng = random.Random(0)
        out = _strategy_func_call(ir, rng)
        # Already has 2 defines — strategy should not add another
        assert out == ir

    def test_result_ends_with_newline(self):
        rng = random.Random(2)
        out = _strategy_func_call(_SIMPLE_IR, rng)
        assert out.endswith("\n")


class TestGlobalVar:
    def test_inserts_global_declaration(self):
        rng = random.Random(0)
        out = _strategy_global_var(_SIMPLE_IR, rng)
        assert "@g_" in out

    def test_inserts_load_instruction(self):
        rng = random.Random(0)
        out = _strategy_global_var(_SIMPLE_IR, rng)
        assert "load i32" in out

    def test_skipped_when_global_already_present(self):
        ir = "@g_1234 = constant i32 5\n" + _SIMPLE_IR
        rng = random.Random(0)
        out = _strategy_global_var(ir, rng)
        # Already has a global — strategy should not add another
        assert out == ir

    def test_result_ends_with_newline(self):
        rng = random.Random(9)
        out = _strategy_global_var(_SIMPLE_IR, rng)
        assert out.endswith("\n")


class TestVectorOps:
    def test_inserts_vector_operations(self):
        rng = random.Random(0)
        out = _strategy_vector_ops(_SIMPLE_IR, rng)
        assert "<4 x i32>" in out

    def test_inserts_insertelement(self):
        rng = random.Random(0)
        out = _strategy_vector_ops(_SIMPLE_IR, rng)
        assert "insertelement" in out

    def test_inserts_extractelement(self):
        rng = random.Random(0)
        out = _strategy_vector_ops(_SIMPLE_IR, rng)
        assert "extractelement" in out

    def test_skipped_when_vector_already_present(self):
        ir = _SIMPLE_IR.replace("ret i32 %v0", "  %vx = add <4 x i32> undef, undef\n  ret i32 %v0")
        rng = random.Random(0)
        out = _strategy_vector_ops(ir, rng)
        assert out == ir

    def test_result_ends_with_newline(self):
        rng = random.Random(4)
        out = _strategy_vector_ops(_SIMPLE_IR, rng)
        assert out.endswith("\n")


class TestMutateText:
    def test_output_ends_with_newline(self):
        rng = random.Random(99)
        out, strategies = _mutate_text(_SIMPLE_IR, rng)
        assert out.endswith("\n")
        assert isinstance(strategies, list)

    def test_output_still_contains_define(self):
        rng = random.Random(5)
        out, _ = _mutate_text(_SIMPLE_IR, rng)
        assert "define i32 @main" in out

    def test_output_is_non_empty(self):
        rng = random.Random(0)
        out, _ = _mutate_text(_SIMPLE_IR, rng)
        assert len(out) > 0

    def test_strategy_names_are_strings(self):
        rng = random.Random(42)
        _, strategies = _mutate_text(_SIMPLE_IR, rng)
        assert all(isinstance(s, str) for s in strategies)

    def test_new_strategies_appear_in_strategy_list(self):
        """Run many seeds and confirm new strategies are reachable."""
        seen = set()
        for seed in range(200):
            _, strategies = _mutate_text(_SIMPLE_IR, random.Random(seed))
            seen.update(strategies)
        new = {"loop_insert", "func_call", "global_var", "vector_ops"}
        # At least one new strategy should fire across 200 seeds
        assert seen & new, f"None of the new strategies appeared in 200 runs; saw: {seen}"


class TestMutateFiles:
    def test_creates_correct_number_of_files(self, tmp_path):
        src = tmp_path / "input"
        src.mkdir()
        (src / "a.ll").write_text(_SIMPLE_IR)
        (src / "b.ll").write_text(_SIMPLE_IR)
        out = tmp_path / "output"
        created = mutate_files(src, out, per_file=2, seed=0)
        assert len(created) == 4

    def test_output_files_have_mut_suffix(self, tmp_path):
        src = tmp_path / "input"
        src.mkdir()
        (src / "foo.ll").write_text(_SIMPLE_IR)
        out = tmp_path / "output"
        created = mutate_files(src, out, per_file=1, seed=0)
        assert created[0].name == "foo_mut0.ll"

    def test_empty_input_produces_no_files(self, tmp_path):
        src = tmp_path / "empty"
        src.mkdir()
        out = tmp_path / "output"
        created = mutate_files(src, out, per_file=2, seed=0)
        assert created == []

    def test_output_directory_is_created(self, tmp_path):
        src = tmp_path / "input"
        src.mkdir()
        (src / "x.ll").write_text(_SIMPLE_IR)
        out = tmp_path / "new_output"
        mutate_files(src, out, per_file=1, seed=0)
        assert out.is_dir()

    def test_mutation_log_written_correctly(self, tmp_path):
        import json
        src = tmp_path / "input"
        src.mkdir()
        (src / "test_file.ll").write_text(_SIMPLE_IR)
        out      = tmp_path / "output"
        log_file = tmp_path / "mutations.jsonl"
        created  = mutate_files(src, out, per_file=2, seed=0, mutation_log=log_file)
        assert len(created) == 2
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        assert entry1["source"] == "test_file.ll"
        assert entry1["output"] == "test_file_mut0.ll"
        assert isinstance(entry1["strategies"], list)

