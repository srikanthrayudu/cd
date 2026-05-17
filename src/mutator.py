from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class MutationConfig:
    per_file: int = 2
    seed: int = 1337


OPCODE_REPLACEMENTS = {
    " add ": " sub ",
    " sub ": " add ",
    " mul ": " add ",
    " xor ": " or ",
    " and ": " or ",
    " or ": " xor ",
}


INT_CONST_RE = re.compile(r"\b(i32|i64)\s+(\d+)\b")


def _insert_dead_code(text: str, rng: random.Random) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "entry:":
            dead = f"  %dead{rng.randint(0,999)} = add i32 0, {rng.randint(1, 9)}"
            lines.insert(idx + 1, dead)
            return "\n".join(lines) + "\n"
    return text


def _split_single_block(text: str, rng: random.Random) -> str:
    match = re.search(r"\nentry:\n([\s\S]*?)\n}\n?", text)
    if not match:
        return text
    body = match.group(1)
    if "br " in body:
        return text
    ret_match = re.search(r"\s+ret i32 (.+)", body)
    if not ret_match:
        return text
    ret_val = ret_match.group(1).strip()
    new_body = re.sub(r"\s+ret i32 .+", "  br label %exit", body)
    exit_block = f"\nexit:\n  ret i32 {ret_val}\n"
    return text.replace(body, new_body + exit_block)


def _insert_conditional_phi(text: str, rng: random.Random) -> str:
    match = re.search(r"\nentry:\n([\s\S]*?)\n}\n?", text)
    if not match:
        return text
    body = match.group(1)
    if "br " in body:
        return text
    ret_match = re.search(r"\s+ret i32 (.+)", body)
    if not ret_match:
        return text
    ret_val = ret_match.group(1).strip()
    tag = rng.randint(100, 999)
    then_label = f"then_{tag}"
    else_label = f"else_{tag}"
    merge_label = f"merge_{tag}"
    cond_inst = f"  %cond{tag} = icmp eq i32 0, 0"
    branch_inst = f"  br i1 %cond{tag}, label %{then_label}, label %{else_label}"
    new_body = re.sub(r"\s+ret i32 .+", f"{cond_inst}\n{branch_inst}", body)
    extra = (
        f"\n{then_label}:\n  br label %{merge_label}\n"
        f"{else_label}:\n  br label %{merge_label}\n"
        f"{merge_label}:\n  %phi{tag} = phi i32 [ {ret_val}, %{then_label} ],"
        f" [ {ret_val}, %{else_label} ]\n  ret i32 %phi{tag}\n"
    )
    return text.replace(body, new_body + extra)


def _mutate_constants(text: str, rng: random.Random) -> str:
    match = INT_CONST_RE.search(text)
    if not match:
        return text
    old = match.group(0)
    width = match.group(1)
    new_val = rng.randint(0, 12)
    return text.replace(old, f"{width} {new_val}", 1)


def _mutate_text(text: str, rng: random.Random) -> str:
    mutated = text
    mutations = [
        "opcode",
        "dead",
        "split",
        "cond_phi",
        "const",
    ]
    rng.shuffle(mutations)
    applied = 0
    for needle, repl in OPCODE_REPLACEMENTS.items():
        if needle in mutated and rng.random() < 0.6:
            mutated = mutated.replace(needle, repl, 1)
            applied += 1
            break
    for action in mutations:
        if applied >= 3:
            break
        roll = rng.random()
        if action == "dead" and roll < 0.5:
            mutated = _insert_dead_code(mutated, rng)
            applied += 1
        elif action == "split" and roll < 0.4:
            mutated = _split_single_block(mutated, rng)
            applied += 1
        elif action == "cond_phi" and roll < 0.3:
            mutated = _insert_conditional_phi(mutated, rng)
            applied += 1
        elif action == "const" and roll < 0.6:
            mutated = _mutate_constants(mutated, rng)
            applied += 1
    if not mutated.endswith("\n"):
        mutated += "\n"
    return mutated


def mutate_files(input_dir: Path, output_dir: Path, config: MutationConfig) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(config.seed)
    created: List[Path] = []
    for file_path in sorted(input_dir.glob("*.ll")):
        original = file_path.read_text()
        for idx in range(config.per_file):
            mutated = _mutate_text(original, rng)
            out_path = output_dir / f"{file_path.stem}_mut{idx}.ll"
            out_path.write_text(mutated)
            created.append(out_path)
    return created
