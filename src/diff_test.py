"""
diff_test.py — Differential testing logic.

Two comparison functions:

``compare_results``      — compare the *runtime behaviour* of two
                           :class:`~src.executor.ExecutionResult` objects
                           (exit code, stdout, stderr).  Used to detect
                           correctness bugs introduced by optimisation.

``compare_optimized_ir`` — compare the *textual LLVM IR* produced by two
                           optimisation levels, generating a unified diff.
                           Used for code-size analysis and documentation.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Optional

from src.executor import ExecutionResult


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class DiffResult:
    """Outcome of comparing the runtime behaviour of two executions."""
    name:     str
    match:    bool             # True  → outputs are identical
    reason:   str              # "match" | "exit_code_mismatch" | "stdout_mismatch" | "stderr_mismatch"
    diff:     str              # human-readable description of the mismatch
    o0_exit:  Optional[int]   = None
    o3_exit:  Optional[int]   = None


@dataclass
class CodeDiffResult:
    """Unified diff between two textual IR representations."""
    name:         str
    o0_ir:        str
    o3_ir:        str
    unified_diff: str
    identical:    bool  # True when the two IR texts are byte-for-byte equal


# ---------------------------------------------------------------------------
# Public comparison functions
# ---------------------------------------------------------------------------

def compare_results(
    name:   str,
    res_o0: ExecutionResult,
    res_o3: ExecutionResult,
) -> DiffResult:
    """
    Compare the runtime outputs of two executions (typically -O0 vs -O3).

    Checks (in order): exit code → stdout → stderr.
    Returns a :class:`DiffResult` with ``match=True`` if all three match.
    """
    if res_o0.exit_code != res_o3.exit_code:
        return DiffResult(
            name    = name,
            match   = False,
            reason  = "exit_code_mismatch",
            diff    = f"O0_exit={res_o0.exit_code!r}\nO3_exit={res_o3.exit_code!r}",
            o0_exit = res_o0.exit_code,
            o3_exit = res_o3.exit_code,
        )

    if res_o0.stdout != res_o3.stdout:
        return DiffResult(
            name    = name,
            match   = False,
            reason  = "stdout_mismatch",
            diff    = f"O0_stdout={res_o0.stdout!r}\nO3_stdout={res_o3.stdout!r}",
            o0_exit = res_o0.exit_code,
            o3_exit = res_o3.exit_code,
        )

    if res_o0.stderr != res_o3.stderr:
        return DiffResult(
            name    = name,
            match   = False,
            reason  = "stderr_mismatch",
            diff    = f"O0_stderr={res_o0.stderr!r}\nO3_stderr={res_o3.stderr!r}",
            o0_exit = res_o0.exit_code,
            o3_exit = res_o3.exit_code,
        )

    return DiffResult(
        name    = name,
        match   = True,
        reason  = "match",
        diff    = "",
        o0_exit = res_o0.exit_code,
        o3_exit = res_o3.exit_code,
    )


def compare_optimized_ir(name: str, o0_ir: str, o3_ir: str) -> CodeDiffResult:
    """
    Produce a unified textual diff between *o0_ir* and *o3_ir*.

    The diff uses the standard ``---`` / ``+++`` format so it can be saved
    as a ``.diff`` file and rendered by any patch viewer.
    """
    diff_lines = list(
        difflib.unified_diff(
            o0_ir.splitlines(),
            o3_ir.splitlines(),
            fromfile=f"{name}.O0.ll",
            tofile=f"{name}.O3.ll",
            lineterm="",
        )
    )
    unified = "\n".join(diff_lines)
    if diff_lines:
        unified += "\n"

    return CodeDiffResult(
        name         = name,
        o0_ir        = o0_ir,
        o3_ir        = o3_ir,
        unified_diff = unified,
        identical    = (o0_ir == o3_ir),
    )
