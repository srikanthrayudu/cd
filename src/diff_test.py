from __future__ import annotations

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

