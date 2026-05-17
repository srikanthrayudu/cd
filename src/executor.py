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

    out_exe = file_path.with_suffix(f".{opt_level}.exe")
    try:
        compile_code, compile_out, compile_err = _run_command(
            ["clang", str(file_path), f"-{opt_level}", "-o", str(out_exe)],
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
            compile_stdout=compile_out,
            compile_stderr=compile_err,
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

