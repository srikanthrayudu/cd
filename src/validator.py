"""
validator.py — LLVM IR validation.

Validation pipeline (in order of preference):
  1. llvm-as + opt -passes=verify   (requires LLVM tools on PATH)
  2. opt -passes=mem2reg             (optional SSA repair; env SSA_FIX=1)
  3. alive-tv                        (optional semantic check; env ALIVE2_VALIDATE=1)
  4. Lightweight regex sanity check  (fallback when LLVM tools are absent)

Tool names and environment-variable keys are read from ``cfg``.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from src.config import cfg


# ---------------------------------------------------------------------------
# Tool probing (cached per interpreter session)
# ---------------------------------------------------------------------------

def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def _llvm_tools_available() -> bool:
    return (
        _tool_available(cfg.validation.assembler_tool)
        and _tool_available(cfg.validation.optimizer_tool)
    )


def _alive2_available() -> bool:
    return _tool_available(cfg.validation.alive2_tool)


def _ssa_fix_enabled() -> bool:
    return os.getenv(cfg.validation.ssa_fix_env_var) in {"1", "true", "True"}


def _alive2_enabled() -> bool:
    return bool(os.getenv(cfg.validation.alive2_env_var)) and _alive2_available()


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Outcome of validating one IR file."""
    is_valid: bool
    reason:   str   # "ok" | "tooling_unavailable" | stderr excerpt


# ---------------------------------------------------------------------------
# Regex fallback (no LLVM tools required)
# ---------------------------------------------------------------------------

def _regex_sanity_check(text: str) -> bool:
    """
    Return True if the IR text passes a minimal structural sanity check:
      - Must contain at least one ``define`` and one ``ret``.
      - Every basic block (any label followed by a colon) must end with a
        ``ret`` or ``br`` terminator.
    """
    if "define" not in text or "ret" not in text:
        return False

    # Split on label lines; even-indexed parts are labels, odd are bodies.
    blocks = re.split(r"\n([a-zA-Z0-9_.]+):\n", "\n" + text)
    if len(blocks) <= 1:
        return True  # single basic block — already checked for ret above

    for idx in range(2, len(blocks), 2):
        body = blocks[idx]
        if not re.search(r"\b(ret|br)\b", body):
            return False
    return True


# ---------------------------------------------------------------------------
# LLVM-based validation
# ---------------------------------------------------------------------------

def _run_llvm_validate(file_path: Path) -> ValidationResult:
    """
    Assemble then verify the IR with llvm-as + opt -passes=verify.
    Optionally run mem2reg (SSA repair) and alive-tv (semantic check).
    """
    tmp_bc = file_path.with_suffix(".bc")
    assembler = cfg.validation.assembler_tool
    optimizer = cfg.validation.optimizer_tool

    try:
        subprocess.run(
            [assembler, str(file_path), "-o", str(tmp_bc)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [optimizer, "-passes=verify", str(tmp_bc), "-o", str(tmp_bc)],
            check=True,
            capture_output=True,
            text=True,
        )
        if _ssa_fix_enabled():
            subprocess.run(
                [optimizer, "-passes=mem2reg", str(tmp_bc), "-o", str(tmp_bc)],
                check=True,
                capture_output=True,
                text=True,
            )
        if _alive2_enabled():
            subprocess.run(
                [cfg.validation.alive2_tool, str(file_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        return ValidationResult(True, "ok")

    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "verify_failed").strip()
        return ValidationResult(False, stderr[:200])  # cap length for readability

    finally:
        if tmp_bc.exists():
            tmp_bc.unlink()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_ir(file_path: Path) -> ValidationResult:
    """
    Validate a single IR file.  Returns a :class:`ValidationResult`.

    Prefer LLVM-based validation; fall back to the regex sanity check when
    LLVM tools are not on PATH.
    """
    if not file_path.exists():
        return ValidationResult(False, "file_missing")

    if _llvm_tools_available():
        return _run_llvm_validate(file_path)

    # Fallback path
    text = file_path.read_text(errors="ignore")
    if _regex_sanity_check(text):
        return ValidationResult(True, "tooling_unavailable")
    return ValidationResult(False, "tooling_unavailable")


def validate_directory(
    input_dir:  Path,
    valid_dir:  Path,
    invalid_dir: Path,
) -> tuple[int, int]:
    """
    Validate every *.ll file in *input_dir*.

    Valid files are moved to *valid_dir*; invalid ones to *invalid_dir*.
    Returns ``(valid_count, invalid_count)``.
    """
    valid_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir.mkdir(parents=True, exist_ok=True)

    valid_count   = 0
    invalid_count = 0

    for file_path in sorted(input_dir.glob("*.ll")):
        result = validate_ir(file_path)
        if result.is_valid:
            file_path.replace(valid_dir / file_path.name)
            valid_count += 1
        else:
            file_path.replace(invalid_dir / file_path.name)
            invalid_count += 1

    return valid_count, invalid_count
