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
        # no "entry:" label — function returns unchanged
        out = _strategy_insert_dead_code(ir, rng)
        # The original block structure is preserved
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
        # should be unchanged — already has a branch
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
        # original has "i32 1" and "i32 2" — one should be replaced
        assert out != _SIMPLE_IR

    def test_no_change_when_no_integer_found(self):
        ir  = "define i32 @main() {\nentry:\n  ret i32 %x\n}\n"
        rng = random.Random(0)
        # no bare integer literal — unchanged
        assert _strategy_const_tweak(ir, rng) == ir


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


class TestMutateFiles:
    def test_creates_correct_number_of_files(self, tmp_path):
        src = tmp_path / "input"
        src.mkdir()
        (src / "a.ll").write_text(_SIMPLE_IR)
        (src / "b.ll").write_text(_SIMPLE_IR)
        out = tmp_path / "output"
        created = mutate_files(src, out, per_file=2, seed=0)
        assert len(created) == 4  # 2 files × 2 mutations each

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
        out = tmp_path / "output"
        log_file = tmp_path / "mutations.jsonl"
        created = mutate_files(src, out, per_file=2, seed=0, mutation_log=log_file)
        assert len(created) == 2
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        
        # Check layout of log entries
        entry1 = json.loads(lines[0])
        assert entry1["source"] == "test_file.ll"
        assert entry1["output"] == "test_file_mut0.ll"
        assert isinstance(entry1["strategies"], list)

