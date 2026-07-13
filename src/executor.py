"""
executor.py — IR execution and binary-size measurement.

Three public functions:

``run_lli``        — interpret an IR file with the LLVM interpreter.
``run_clang``      — compile an IR file with clang at a given optimisation
                     level, measure the object-file size, then run the binary.
``emit_optimized_ir`` — produce textual LLVM IR after running opt at a given
                     optimisation level (used for diff analysis).

All tool names and timeout values come from ``cfg`` (config.yaml →
execution section) so nothing is hardcoded here.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from src.config import cfg


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    """Outcome of executing one IR file under one mode."""
    name:              str
    mode:              str               # "lli" | "O0" | "O3" | …
    exit_code:         Optional[int]
    stdout:            str
    stderr:            str
    skipped:           bool
    reason:            str               # "ok" | "missing_<tool>" | "timeout" | "compile_failed" | …
    compile_exit_code: Optional[int]     = field(default=None)
    compile_stdout:    str               = field(default="")
    compile_stderr:    str               = field(default="")
    binary_size:       Optional[int]     = field(default=None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tool_on_path(name: str) -> bool:
    return shutil.which(name) is not None


def _run(cmd: list, timeout: int) -> Tuple[int, str, str]:
    """Run *cmd* and return (returncode, stdout, stderr).  Raises TimeoutExpired."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_lli(file_path: Path) -> ExecutionResult:
    """
    Interpret *file_path* using the LLVM interpreter (lli).

    Returns a skipped result immediately when lli is not on PATH.
    """
    tool = cfg.execution.interpreter

    if not _tool_on_path(tool):
        return ExecutionResult(
            name     = file_path.stem,
            mode     = "lli",
            exit_code= None,
            stdout   = "",
            stderr   = "",
            skipped  = True,
            reason   = f"missing_{tool}",
        )
    try:
        code, out, err = _run([tool, str(file_path)], cfg.execution.timeouts.lli)
        return ExecutionResult(
            name      = file_path.stem,
            mode      = "lli",
            exit_code = code,
            stdout    = out,
            stderr    = err,
            skipped   = False,
            reason    = "ok",
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            name      = file_path.stem,
            mode      = "lli",
            exit_code = None,
            stdout    = "",
            stderr    = "timeout",
            skipped   = False,
            reason    = "timeout",
        )


def run_clang(file_path: Path, opt_level: str) -> ExecutionResult:
    """
    Compile *file_path* at *opt_level* (e.g. ``"O0"`` or ``"O3"``) using
    clang, measure the object-file size, link to an executable, and run it.

    Using an object file rather than a final linked binary makes the size
    comparison more sensitive to code-generation differences.

    Returns a skipped result when clang is not on PATH.
    """
    tool = cfg.execution.compiler
    t    = cfg.execution.timeouts

    if not _tool_on_path(tool):
        return ExecutionResult(
            name      = file_path.stem,
            mode      = opt_level,
            exit_code = None,
            stdout    = "",
            stderr    = "",
            skipped   = True,
            reason    = f"missing_{tool}",
        )

    out_o   = file_path.with_suffix(f".{opt_level}.o")
    out_exe = file_path.with_suffix(f".{opt_level}.exe")

    try:
        # ── Step 1: compile to object ──────────────────────────────────────
        cc, co, ce = _run(
            [tool, "-c", str(file_path), f"-{opt_level}", "-o", str(out_o)],
            t.compile,
        )
        if cc != 0:
            return ExecutionResult(
                name              = file_path.stem,
                mode              = opt_level,
                exit_code         = None,
                stdout            = "",
                stderr            = "",
                skipped           = False,
                reason            = "compile_failed",
                compile_exit_code = cc,
                compile_stdout    = co,
                compile_stderr    = ce,
            )

        # ── Step 2: measure object size ────────────────────────────────────
        try:
            bin_size: Optional[int] = out_o.stat().st_size
        except OSError:
            bin_size = None

        # ── Step 3: link to executable ─────────────────────────────────────
        lc, lo, le = _run([tool, str(out_o), "-o", str(out_exe)], t.link)
        if lc != 0:
            return ExecutionResult(
                name              = file_path.stem,
                mode              = opt_level,
                exit_code         = None,
                stdout            = "",
                stderr            = "",
                skipped           = False,
                reason            = "link_failed",
                compile_exit_code = cc,
                compile_stdout    = co + lo,
                compile_stderr    = ce + le,
                binary_size       = bin_size,
            )

        # ── Step 4: run the executable ─────────────────────────────────────
        rc, ro, re_ = _run([str(out_exe)], t.run)
        return ExecutionResult(
            name              = file_path.stem,
            mode              = opt_level,
            exit_code         = rc,
            stdout            = ro,
            stderr            = re_,
            skipped           = False,
            reason            = "ok",
            compile_exit_code = cc,
            compile_stdout    = co + lo,
            compile_stderr    = ce + le,
            binary_size       = bin_size,
        )

    except subprocess.TimeoutExpired:
        return ExecutionResult(
            name      = file_path.stem,
            mode      = opt_level,
            exit_code = None,
            stdout    = "",
            stderr    = "timeout",
            skipped   = False,
            reason    = "timeout",
        )

    finally:
        # Always clean up temporary files
        for tmp in (out_o, out_exe):
            if tmp.exists():
                tmp.unlink()


def emit_optimized_ir(file_path: Path, opt_level: str) -> Tuple[bool, str, str]:
    """
    Run ``opt -S -<opt_level>`` on *file_path* and return
    ``(success, stdout_ir_text, stderr_text)``.

    Used to produce the human-readable textual IR for diff analysis.
    Returns ``(False, "", "missing_opt")`` when opt is unavailable.
    """
    tool = cfg.execution.optimizer

    if not _tool_on_path(tool):
        return False, "", f"missing_{tool}"

    try:
        code, out, err = _run(
            [tool, "-S", f"-{opt_level}", str(file_path)],
            cfg.execution.timeouts.emit_ir,
        )
        return code == 0, out, err

    except subprocess.TimeoutExpired:
        return False, "", "timeout"
