"""
tests/test_ir_generator.py — Unit tests for src/ir_generator.py
"""
import pytest
from pathlib import Path
from src.ir_generator import generate_ir_snippets, write_generated_ir, _decorate, _pick_template


class TestGenerateIrSnippets:
    def test_yields_correct_count(self):
        snippets = list(generate_ir_snippets(count=3, seed=0, backend="template",
                                             model="", mode="generate"))
        assert len(snippets) == 3

    def test_each_snippet_is_non_empty_string(self):
        for snippet in generate_ir_snippets(count=2, seed=1, backend="template",
                                            model="", mode="generate"):
            assert isinstance(snippet, str)
            assert len(snippet) > 0

    def test_each_snippet_contains_define(self):
        for snippet in generate_ir_snippets(count=3, seed=42, backend="template",
                                            model="", mode="generate"):
            assert "define" in snippet

    def test_each_snippet_ends_with_newline(self):
        for snippet in generate_ir_snippets(count=2, seed=7, backend="template",
                                            model="", mode="generate"):
            assert snippet.endswith("\n")

    def test_different_seeds_produce_different_output(self):
        s1 = list(generate_ir_snippets(count=1, seed=0,  backend="template", model="", mode="generate"))
        s2 = list(generate_ir_snippets(count=1, seed=99, backend="template", model="", mode="generate"))
        # Different seeds should (almost always) produce different text
        assert s1 != s2

    def test_same_seed_is_reproducible(self):
        a = list(generate_ir_snippets(count=3, seed=13, backend="template", model="", mode="generate"))
        b = list(generate_ir_snippets(count=3, seed=13, backend="template", model="", mode="generate"))
        assert a == b

    def test_zero_count_yields_nothing(self):
        snippets = list(generate_ir_snippets(count=0, seed=0, backend="template",
                                             model="", mode="generate"))
        assert snippets == []


class TestWriteGeneratedIr:
    def test_creates_correct_number_of_files(self, tmp_path):
        created = write_generated_ir(
            output_dir=tmp_path, count=4, seed=0,
            backend="template", model="", mode="generate",
        )
        assert len(created) == 4
        assert all(p.exists() for p in created)

    def test_files_have_ll_extension(self, tmp_path):
        created = write_generated_ir(
            output_dir=tmp_path, count=2, seed=0,
            backend="template", model="", mode="generate",
        )
        assert all(p.suffix == ".ll" for p in created)

    def test_output_directory_is_created(self, tmp_path):
        out = tmp_path / "new_dir"
        write_generated_ir(output_dir=out, count=1, seed=0,
                           backend="template", model="", mode="generate")
        assert out.is_dir()

    def test_file_content_is_valid_ir_snippet(self, tmp_path):
        created = write_generated_ir(
            output_dir=tmp_path, count=1, seed=5,
            backend="template", model="", mode="generate",
        )
        text = created[0].read_text()
        assert "define" in text
        assert "ret" in text


class TestDecorate:
    _BASE = "define i32 @main() {\nentry:\n  ret i32 0\n}\n"

    def test_decorator_replaces_ret(self):
        import random
        out = _decorate(self._BASE, 0, random.Random(1), "t")
        # Original plain "ret i32 0" should be gone; chain replaces it
        assert "ret i32 %pad_" in out

    def test_decorator_appends_dead_helper(self):
        import random
        out = _decorate(self._BASE, 0, random.Random(2), "t")
        assert "_dead_" in out

    def test_non_main_function_untouched(self):
        import random
        ir  = "define i32 @helper() {\nentry:\n  ret i32 1\n}\n"
        out = _decorate(ir, 0, random.Random(0), "t")
        # No @main → decorator is skipped
        assert out == ir + "\n" or out == ir
