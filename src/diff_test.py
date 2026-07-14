"""
diff_test.py — Differential testing logic.

Three public functions:

``compare_results``       — compare the *runtime behaviour* of two
                            :class:`~src.executor.ExecutionResult` objects
                            (exit code, stdout, stderr).  Used to detect
                            correctness bugs introduced by optimisation.

``compare_optimized_ir``  — compare the *textual LLVM IR* produced by two
                            optimisation levels, generating a unified diff
                            and instruction-count statistics.

``count_ir_instructions`` — count the number of non-label, non-comment
                            LLVM IR instructions in a textual IR string.
                            Provides a direct measure of optimiser
                            effectiveness independent of binary size.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional

from src.executor import ExecutionResult


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class DiffResult:
    """Outcome of comparing the runtime behaviour of two executions."""
    name:     str
    match:    bool            # True  → outputs are identical
    reason:   str             # "match" | "exit_code_mismatch" | "stdout_mismatch" | "stderr_mismatch"
    diff:     str             # human-readable description of the mismatch
    o0_exit:  Optional[int]  = None
    o3_exit:  Optional[int]  = None


@dataclass
class CodeDiffResult:
    """Unified diff between two textual IR representations, plus instruction counts."""
    name:                str
    o0_ir:               str
    o3_ir:               str
    unified_diff:        str
    identical:           bool    # True when the two IR texts are byte-for-byte equal
    o0_instr_count:      int     = field(default=0)
    o3_instr_count:      int     = field(default=0)
    instr_delta:         int     = field(default=0)   # o0 - o3 (positive = shrinkage)
    instr_reduction_pct: float   = field(default=0.0) # % instructions eliminated by O3


# ---------------------------------------------------------------------------
# Instruction counting
# ---------------------------------------------------------------------------

# Lines that are NOT real instructions:
#   - blank lines
#   - comment lines     (optional whitespace then ';')
#   - label lines       (identifier followed by ':')
#   - function openers  (define / declare)
#   - module directives (target triple/datalayout, attributes, metadata)
#   - module-level globals / constants / aliases
#   - curly braces      (opening/closing blocks)
_NON_INSTR_RE = re.compile(
    r"^\s*$"                         # blank
    r"|^\s*;"                        # comment
    r"|^\s*[a-zA-Z0-9_.%@]+:\s*$"   # bare label line (ends in ':')
    r"|^\s*define\b"                 # function definition opener
    r"|^\s*declare\b"                # external declaration
    r"|^\s*target\b"                 # target triple / datalayout
    r"|^\s*attributes\b"             # attribute group
    r"|^\s*!\s*\d"                   # numbered metadata
    r"|^\s*[;@]"                     # module-level metadata / global
    r"|^\s*[\}\{]\s*$"               # lone brace
)


def count_ir_instructions(ir_text: str) -> int:
    """
    Count the number of LLVM IR instructions in *ir_text*.

    Labels, blank lines, comments, and module-level declarations are
    excluded.  This gives a direct, tool-independent measure of how many
    operations the back-end must lower to machine code.

    Examples
    --------
    >>> count_ir_instructions("  %x = add i32 1, 2\\n  ret i32 %x\\n")
    2
    """
    count = 0
    for line in ir_text.splitlines():
        if line.strip() and not _NON_INSTR_RE.match(line):
            count += 1
    return count


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
    Produce a unified textual diff between *o0_ir* and *o3_ir*, and compute
    instruction-count statistics for both IR texts.

    The diff uses the standard ``---`` / ``+++`` format so it can be saved
    as a ``.diff`` file and rendered by any patch viewer.

    The instruction-count fields (``o0_instr_count``, ``o3_instr_count``,
    ``instr_delta``, ``instr_reduction_pct``) quantify how aggressively O3
    reduced the IR regardless of binary-size measurement availability.
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

    o0_count = count_ir_instructions(o0_ir)
    o3_count = count_ir_instructions(o3_ir)
    delta    = o0_count - o3_count
    pct      = round(delta / o0_count * 100, 2) if o0_count else 0.0

    return CodeDiffResult(
        name                = name,
        o0_ir               = o0_ir,
        o3_ir               = o3_ir,
        unified_diff        = unified,
        identical           = (o0_ir == o3_ir),
        o0_instr_count      = o0_count,
        o3_instr_count      = o3_count,
        instr_delta         = delta,
        instr_reduction_pct = pct,
    )
