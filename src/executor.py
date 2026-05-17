from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExecutionResult:
    name: str
    mode: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    skipped: bool
    reason: str
    compile_exit_code: Optional[int] = None
    compile_stdout: str = ""
    compile_stderr: str = ""
    binary_size: Optional[int] = None


def _has_tool(tool: str) -> bool:
    return shutil.which(tool) is not None


def _run_command(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return completed.returncode, completed.stdout, completed.stderr


def run_lli(file_path: Path, timeout: int = 5) -> ExecutionResult:
    if not _has_tool("lli"):
        return ExecutionResult(file_path.stem, "lli", None, "", "", True, "missing_lli")
    try:
        code, out, err = _run_command(["lli", str(file_path)], timeout)
        return ExecutionResult(file_path.stem, "lli", code, out, err, False, "ok")
    except subprocess.TimeoutExpired:
        return ExecutionResult(file_path.stem, "lli", None, "", "timeout", False, "timeout")


def run_clang(file_path: Path, opt_level: str, timeout: int = 5) -> ExecutionResult:
    if not _has_tool("clang"):
        return ExecutionResult(file_path.stem, opt_level, None, "", "", True, "missing_clang")
    # Compile to an object file first and measure the object size. Object
    # sizes reflect codegen differences more directly and avoid linker
    # noise that can make O0/O3 sizes look identical. Then link the
    # object to an executable so we can run it for behavioral checks.
    out_o = file_path.with_suffix(f".{opt_level}.o")
    out_exe = file_path.with_suffix(f".{opt_level}.exe")
    try:
        # Compile to object
        compile_code, compile_out, compile_err = _run_command(
            ["clang", "-c", str(file_path), f"-{opt_level}", "-o", str(out_o)],
            timeout,
        )
        if compile_code != 0:
            return ExecutionResult(
                file_path.stem,
                opt_level,
                None,
                "",
                "",
                False,
                "compile_failed",
                compile_exit_code=compile_code,
                compile_stdout=compile_out,
                compile_stderr=compile_err,
            )

        # Measure object size (more sensitive to opt level differences)
        try:
            bin_size = out_o.stat().st_size
        except Exception:
            bin_size = None

        # Link the object to produce an executable so we can run it
        link_code, link_out, link_err = _run_command(["clang", str(out_o), "-o", str(out_exe)], timeout)
        if link_code != 0:
            # Linking failed; still return compile info
            return ExecutionResult(
                file_path.stem,
                opt_level,
                None,
                "",
                "",
                False,
                "link_failed",
                compile_exit_code=compile_code,
                compile_stdout=compile_out + link_out,
                compile_stderr=compile_err + link_err,
                binary_size=bin_size,
            )

        # Run the produced executable for behavioral observation
        code, out, err = _run_command([str(out_exe)], timeout)
        return ExecutionResult(
            file_path.stem,
            opt_level,
            code,
            out,
            err,
            False,
            "ok",
            compile_exit_code=compile_code,
            compile_stdout=compile_out + link_out,
            compile_stderr=compile_err + link_err,
            binary_size=bin_size,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            file_path.stem,
            opt_level,
            None,
            "",
            "timeout",
            False,
            "timeout",
        )
    finally:
        if out_exe.exists():
            out_exe.unlink()
        if out_o.exists():
            out_o.unlink()


def emit_optimized_ir(file_path: Path, opt_level: str, timeout: int = 10) -> tuple[bool, str, str]:
    """Return (ok, stdout, stderr) for textual LLVM IR after applying opt level."""
    if not _has_tool("opt"):
        return False, "", "missing_opt"
    try:
        code, out, err = _run_command(["opt", "-S", f"-{opt_level}", str(file_path)], timeout)
        return code == 0, out, err
    except subprocess.TimeoutExpired:
        return False, "", "timeout"

