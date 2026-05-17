from __future__ import annotations

import difflib
from dataclasses import dataclass

from src.executor import ExecutionResult


@dataclass
class DiffResult:
    name: str
    match: bool
    reason: str
    diff: str
    o0_exit: int | None = None
    o3_exit: int | None = None


@dataclass
class CodeDiffResult:
    name: str
    o0_ir: str
    o3_ir: str
    unified_diff: str
    identical: bool


def compare_optimized_ir(name: str, o0_ir: str, o3_ir: str) -> CodeDiffResult:
    diff_lines = list(
        difflib.unified_diff(
            o0_ir.splitlines(),
            o3_ir.splitlines(),
            fromfile=f"{name}.O0.ll",
            tofile=f"{name}.O3.ll",
            lineterm="",
        )
    )
    return CodeDiffResult(name=name, o0_ir=o0_ir, o3_ir=o3_ir, unified_diff="\n".join(diff_lines) + ("\n" if diff_lines else ""), identical=(o0_ir == o3_ir))


def compare_results(name: str, res_o0: ExecutionResult, res_o3: ExecutionResult) -> DiffResult:
    if res_o0.exit_code != res_o3.exit_code:
        return DiffResult(
            name,
            False,
            "exit_code_mismatch",
            f"O0_exit={res_o0.exit_code!r}\nO3_exit={res_o3.exit_code!r}",
            o0_exit=res_o0.exit_code,
            o3_exit=res_o3.exit_code,
        )
    if res_o0.stdout != res_o3.stdout:
        return DiffResult(
            name,
            False,
            "stdout_mismatch",
            f"O0_stdout={res_o0.stdout!r}\nO3_stdout={res_o3.stdout!r}",
            o0_exit=res_o0.exit_code,
            o3_exit=res_o3.exit_code,
        )
    if res_o0.stderr != res_o3.stderr:
        return DiffResult(
            name,
            False,
            "stderr_mismatch",
            f"O0_stderr={res_o0.stderr!r}\nO3_stderr={res_o3.stderr!r}",
            o0_exit=res_o0.exit_code,
            o3_exit=res_o3.exit_code,
        )
    return DiffResult(name, True, "match", "", o0_exit=res_o0.exit_code, o3_exit=res_o3.exit_code)

