"""
tests/test_validator.py — Unit tests for src/validator.py

These tests exercise the regex fallback path that runs when LLVM tools
are not installed, so they work in any environment.
"""
import pytest
from pathlib import Path
from src.validator import validate_ir, validate_directory, _regex_sanity_check


class TestRegexSanityCheck:
    def test_valid_minimal_ir(self):
        ir = "define i32 @main() {\nentry:\n  ret i32 0\n}\n"
        assert _regex_sanity_check(ir) is True

    def test_missing_define_fails(self):
        ir = "entry:\n  ret i32 0\n"
        assert _regex_sanity_check(ir) is False

    def test_missing_ret_fails(self):
        ir = "define i32 @main() {\nentry:\n  %x = add i32 0, 1\n}\n"
        assert _regex_sanity_check(ir) is False

    def test_multi_block_with_terminators(self):
        ir = (
            "define i32 @main() {\n"
            "entry:\n  br label %done\n"
            "done:\n  ret i32 0\n"
            "}\n"
        )
        assert _regex_sanity_check(ir) is True

    def test_empty_string_fails(self):
        assert _regex_sanity_check("") is False


class TestValidateIr:
    def test_missing_file_is_invalid(self, tmp_path):
        result = validate_ir(tmp_path / "nonexistent.ll")
        assert result.is_valid is False
        assert result.reason == "file_missing"

    def test_valid_ir_file_passes(self, tmp_path):
        ir_file = tmp_path / "good.ll"
        ir_file.write_text("define i32 @main() {\nentry:\n  ret i32 0\n}\n")
        result = validate_ir(ir_file)
        # Either LLVM tools validated it ("ok") or the fallback did
        assert result.is_valid is True
        assert result.reason in ("ok", "tooling_unavailable")

    def test_bad_ir_file_fails(self, tmp_path):
        ir_file = tmp_path / "bad.ll"
        ir_file.write_text("this is not llvm ir at all")
        result = validate_ir(ir_file)
        # May fail via LLVM tools or via regex fallback — either way invalid
        assert result.is_valid is False


class TestValidateDirectory:
    _GOOD_IR = "define i32 @main() {\nentry:\n  ret i32 0\n}\n"
    _BAD_IR  = "not valid ir"

    def test_valid_files_moved_to_valid_dir(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        (src / "good.ll").write_text(self._GOOD_IR)
        valid_dir   = tmp_path / "valid"
        invalid_dir = tmp_path / "invalid"
        v, i = validate_directory(src, valid_dir, invalid_dir)
        assert v == 1
        assert i == 0
        assert (valid_dir / "good.ll").exists()

    def test_invalid_files_moved_to_invalid_dir(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        (src / "bad.ll").write_text(self._BAD_IR)
        valid_dir   = tmp_path / "valid"
        invalid_dir = tmp_path / "invalid"
        v, i = validate_directory(src, valid_dir, invalid_dir)
        assert i == 1
        assert (invalid_dir / "bad.ll").exists()

    def test_empty_directory_returns_zeros(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        v, i = validate_directory(src, tmp_path / "v", tmp_path / "i")
        assert v == 0 and i == 0

    def test_creates_output_directories(self, tmp_path):
        src = tmp_path / "src"; src.mkdir()
        v_dir = tmp_path / "valid"
        i_dir = tmp_path / "invalid"
        validate_directory(src, v_dir, i_dir)
        assert v_dir.is_dir()
        assert i_dir.is_dir()
