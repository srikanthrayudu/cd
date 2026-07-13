"""
mutator.py — LLVM IR mutation strategies.

Each strategy is a pure function that takes an IR text string and a seeded
RNG, and returns a (possibly modified) IR text string.  Strategies never
raise — if a transformation is not applicable they return the text unchanged.

Strategy selection probabilities and the maximum number of strategies
applied per file are read from ``cfg`` (config.yaml → mutation section).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Tuple

from src.config import cfg

# Type alias for a mutation strategy function
_Strategy = Callable[[str, random.Random], str]


# ---------------------------------------------------------------------------
# Strategy 1: Opcode swap
# ---------------------------------------------------------------------------

# Maps an opcode substring (with surrounding spaces) to its replacement.
# Using surrounding spaces prevents partial matches like "load" → "lsub".
_OPCODE_PAIRS: List[Tuple[str, str]] = [
    (" add ", " sub "),
    (" sub ", " add "),
    (" mul ", " add "),
    (" xor ", " or  "),
    (" and ", " or  "),
    (" or  ", " xor "),
]


def _strategy_opcode_swap(text: str, rng: random.Random) -> str:
    """Replace the first matching opcode with its pair (randomly ordered)."""
    pairs = list(_OPCODE_PAIRS)
    rng.shuffle(pairs)
    for old, new in pairs:
        if old in text:
            return text.replace(old, new, 1)
    return text


# ---------------------------------------------------------------------------
# Strategy 2: Insert dead code
# ---------------------------------------------------------------------------

def _strategy_insert_dead_code(text: str, rng: random.Random) -> str:
    """Insert one unreachable computation after the entry: label."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "entry:":
            name  = f"%dead_{rng.randint(0, 9999)}"
            value = rng.randint(1, 9)
            lines.insert(idx + 1, f"  {name} = add i32 0, {value}")
            result = "\n".join(lines)
            return result if result.endswith("\n") else result + "\n"
    return text


# ---------------------------------------------------------------------------
# Strategy 3: Split the entry block with an unconditional branch
# ---------------------------------------------------------------------------

def _strategy_block_split(text: str, rng: random.Random) -> str:
    """
    If the entry block has a single ``ret i32 <val>`` and no existing branches,
    split it into entry → exit so the CFG has two blocks.
    """
    m = re.search(r"\nentry:\n([\s\S]*?)\n}\n?", text)
    if not m:
        return text
    body = m.group(1)
    if "br " in body:
        return text  # already has control flow
    ret_m = re.search(r"\s+ret i32 (.+)", body)
    if not ret_m:
        return text

    ret_val  = ret_m.group(1).strip()
    new_body = re.sub(r"\s+ret i32 .+", "  br label %exit", body)
    exit_block = f"\nexit:\n  ret i32 {ret_val}\n"
    return text.replace(body, new_body + exit_block)


# ---------------------------------------------------------------------------
# Strategy 4: Insert a conditional + phi (trivially always-taken)
# ---------------------------------------------------------------------------

def _strategy_cond_phi(text: str, rng: random.Random) -> str:
    """
    Replace the single ``ret i32 <val>`` with a trivially always-true
    branch that merges via a phi node and returns the same value.
    """
    m = re.search(r"\nentry:\n([\s\S]*?)\n}\n?", text)
    if not m:
        return text
    body = m.group(1)
    if "br " in body:
        return text
    ret_m = re.search(r"\s+ret i32 (.+)", body)
    if not ret_m:
        return text

    ret_val   = ret_m.group(1).strip()
    tag       = rng.randint(100, 999)
    then_lbl  = f"then_{tag}"
    else_lbl  = f"else_{tag}"
    merge_lbl = f"merge_{tag}"

    cond_line   = f"  %cond{tag} = icmp eq i32 0, 0"
    branch_line = f"  br i1 %cond{tag}, label %{then_lbl}, label %{else_lbl}"
    new_body    = re.sub(r"\s+ret i32 .+", f"\n{cond_line}\n{branch_line}", body)
    extra = (
        f"\n{then_lbl}:\n  br label %{merge_lbl}\n"
        f"{else_lbl}:\n  br label %{merge_lbl}\n"
        f"{merge_lbl}:\n"
        f"  %phi{tag} = phi i32 [ {ret_val}, %{then_lbl} ], [ {ret_val}, %{else_lbl} ]\n"
        f"  ret i32 %phi{tag}\n"
    )
    return text.replace(body, new_body + extra)


# ---------------------------------------------------------------------------
# Strategy 5: Deep CFG split (multi-level diamond)
# ---------------------------------------------------------------------------

def _strategy_deep_cfg(text: str, rng: random.Random) -> str:
    """
    Insert a two-level CFG diamond before the return.
    Both paths compute slightly different values and merge via phi nodes.
    O3 can often simplify the whole structure; O0 keeps every block.
    """
    m = re.search(r"\nentry:\n([\s\S]*?)\n}\n?", text)
    if not m:
        return text
    body  = m.group(1)
    ret_m = re.search(r"\s+ret i32 (.+)", body)
    if not ret_m:
        return text

    ret_val = ret_m.group(1).strip()
    t       = rng.randint(1000, 9999)
    r       = rng.randint

    # Entry diamond condition (always evaluable at compile time)
    entry_cond   = f"  %split{t} = icmp sgt i32 {t % 17}, {t % 7}"
    entry_branch = f"  br i1 %split{t}, label %sa_{t}, label %sb_{t}"

    path_a = (
        f"sa_{t}:\n"
        f"  %a1_{t} = add i32 {ret_val}, {r(1, 9)}\n"
        f"  %a2_{t} = mul i32 %a1_{t}, {r(2, 5)}\n"
        f"  %acond_{t} = icmp slt i32 %a2_{t}, {r(10, 99)}\n"
        f"  br i1 %acond_{t}, label %at_{t}, label %ae_{t}\n"
        f"at_{t}:\n"
        f"  %atv_{t} = add i32 %a2_{t}, {r(1, 7)}\n"
        f"  br label %merge_{t}\n"
        f"ae_{t}:\n"
        f"  %aev_{t} = sub i32 %a2_{t}, {r(1, 7)}\n"
        f"  br label %merge_{t}\n"
    )

    path_b = (
        f"sb_{t}:\n"
        f"  %b1_{t} = sub i32 {ret_val}, {r(1, 9)}\n"
        f"  %b2_{t} = xor i32 %b1_{t}, {r(3, 11)}\n"
        f"  %bcond_{t} = icmp sgt i32 %b2_{t}, {r(10, 99)}\n"
        f"  br i1 %bcond_{t}, label %bt_{t}, label %be_{t}\n"
        f"bt_{t}:\n"
        f"  %btv_{t} = add i32 %b2_{t}, {r(1, 7)}\n"
        f"  br label %merge_{t}\n"
        f"be_{t}:\n"
        f"  %bev_{t} = xor i32 %b2_{t}, {r(3, 11)}\n"
        f"  br label %merge_{t}\n"
    )

    merge = (
        f"merge_{t}:\n"
        f"  %phi_{t} = phi i32 "
        f"[ %atv_{t}, %at_{t} ], [ %aev_{t}, %ae_{t} ], "
        f"[ %btv_{t}, %bt_{t} ], [ %bev_{t}, %be_{t} ]\n"
        f"  %res_{t} = add i32 %phi_{t}, {r(1, 13)}\n"
        f"  ret i32 %res_{t}\n"
    )

    new_body = re.sub(
        r"\s+ret i32 .+",
        f"\n{entry_cond}\n{entry_branch}\n",
        body,
    )
    return text.replace(body, new_body + "\n" + path_a + "\n" + path_b + "\n" + merge)


# ---------------------------------------------------------------------------
# Strategy 6: Constant tweak
# ---------------------------------------------------------------------------

_INT_CONST_RE = re.compile(r"\b(i32|i64)\s+(\d+)\b")


def _strategy_const_tweak(text: str, rng: random.Random) -> str:
    """Replace the first small integer literal found in the text."""
    m = _INT_CONST_RE.search(text)
    if not m:
        return text
    width   = m.group(1)
    new_val = rng.randint(0, 12)
    return text.replace(m.group(0), f"{width} {new_val}", 1)


# ---------------------------------------------------------------------------
# Ordered strategy table
# ---------------------------------------------------------------------------

_STRATEGIES: List[Tuple[str, _Strategy]] = [
    ("opcode_swap", _strategy_opcode_swap),
    ("dead_code",   _strategy_insert_dead_code),
    ("block_split", _strategy_block_split),
    ("cond_phi",    _strategy_cond_phi),
    ("deep_cfg",    _strategy_deep_cfg),
    ("const_tweak", _strategy_const_tweak),
]


# ---------------------------------------------------------------------------
# Public mutation entry point
# ---------------------------------------------------------------------------

def _mutate_text(text: str, rng: random.Random) -> tuple[str, list[str]]:
    """
    Apply a random subset of strategies to *text* and return the result
    along with the list of strategy names that were actually applied.

    - The strategy list is shuffled so the order varies per call.
    - Each strategy is applied with the probability from ``cfg``.
    - At most ``cfg.mutation.max_strategies_per_file`` strategies are applied.
    """
    weights = cfg.mutation.strategy_weights
    threshold_map: dict[str, float] = {
        "opcode_swap": weights.opcode_swap,
        "dead_code":   weights.dead_code,
        "block_split": weights.block_split,
        "cond_phi":    weights.cond_phi,
        "deep_cfg":    weights.deep_cfg,
        "const_tweak": weights.const_tweak,
    }
    max_applied = cfg.mutation.max_strategies_per_file

    strategy_list = list(_STRATEGIES)
    rng.shuffle(strategy_list)

    mutated  = text
    applied  = 0
    applied_names: list[str] = []

    for name, fn in strategy_list:
        if applied >= max_applied:
            break
        threshold = threshold_map.get(name, 0.5)
        if rng.random() < threshold:
            mutated  = fn(mutated, rng)
            applied += 1
            applied_names.append(name)

    result = mutated if mutated.endswith("\n") else mutated + "\n"
    return result, applied_names


def mutate_files(
    input_dir:    Path,
    output_dir:   Path,
    per_file:     int,
    seed:         int,
    mutation_log: Path | None = None,
) -> list[Path]:
    """
    Mutate every *.ll file in *input_dir*, writing *per_file* variants for
    each into *output_dir*.  Returns the list of created file paths.

    Parameters
    ----------
    input_dir:    directory containing the source *.ll files
    output_dir:   directory where mutated files are written
    per_file:     how many mutations to produce per source file
    seed:         RNG seed for reproducibility
    mutation_log: optional path to a JSONL audit log (one entry per mutated file)
    """
    import json

    output_dir.mkdir(parents=True, exist_ok=True)
    rng     = random.Random(seed)
    created: List[Path] = []
    log_fh  = mutation_log.open("a", encoding="utf-8") if mutation_log else None

    try:
        for source in sorted(input_dir.glob("*.ll")):
            original = source.read_text(encoding="utf-8")
            for idx in range(per_file):
                mutated, strategies = _mutate_text(original, rng)
                out_path = output_dir / f"{source.stem}_mut{idx}.ll"
                out_path.write_text(mutated, encoding="utf-8")
                created.append(out_path)

                if log_fh is not None:
                    entry = {
                        "source":     source.name,
                        "output":     out_path.name,
                        "strategies": strategies,
                    }
                    log_fh.write(json.dumps(entry) + "\n")
    finally:
        if log_fh is not None:
            log_fh.close()

    return created
