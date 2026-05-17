from __future__ import annotations

import os
import random
import re
import importlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .templates import TEMPLATE_LIBRARY, TEMPLATES

HEAVY_TEMPLATE_NAMES = {
    "dead_code_elimination",
    "branch_fanout",
    "branch_fanout_2",
    "multi_way_branch",
    "multi_way_branch_2",
    "switch_lowering",
    "switch_lowering_2",
}

_TEMPLATE_WEIGHT_OVERRIDES = {
    "dead_code_elimination": 8,
    "branch_fanout": 7,
    "branch_fanout_2": 7,
    "multi_way_branch": 6,
    "multi_way_branch_2": 6,
    "switch_lowering": 5,
    "switch_lowering_2": 5,
    "loop_invariant": 4,
    "vector_pattern": 3,
    "array_promote": 3,
}

@dataclass
class GenerationConfig:
    count: int = 10
    seed: int = 1337
    backend: str = "template"
    model: str = "gpt-4o-mini"
    mode: str = "generate"
    seed_dir: Optional[Path] = None
    prompt_template: str = (
        "Generate a single valid LLVM IR function. "
        "Return only LLVM IR, no prose.\n"
        "Constraints: SSA form, i32 ops, and end with ret. Must be a zero-argument define i32 @main(). Use opaque ptr syntax (ptr instead of i32*)."
    )
    mutate_prompt_template: str = (
        "Mutate the following LLVM IR while keeping it valid. "
        "Return only LLVM IR, no prose.\n"
        "Prefer small edits (opcode swap, constant tweak, or control-flow split)."
        "Do not change the function name from @main."
    )

_ENV_LOADED = False


def _load_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        _ENV_LOADED = True
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
    _ENV_LOADED = True


def _openai_generate(prompt: str, model: str) -> Optional[str]:
    _load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        openai_module = importlib.import_module("openai")
        OpenAI = getattr(openai_module, "OpenAI")
    except Exception:
        return None

    try:
        client = OpenAI()
        response = client.responses.create(
            model=model,
            input=prompt,
        )
    except Exception:
        return None

    text_chunks = []
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    text_chunks.append(content.text)
    return "\n".join(text_chunks).strip() if text_chunks else None


def _load_seed_texts(seed_dir: Optional[Path]) -> List[str]:
    if not seed_dir or not seed_dir.exists():
        return []
    return [path.read_text() for path in sorted(seed_dir.glob("*.ll"))]


def _template_choice_pool(rng: random.Random) -> list[dict[str, str]]:
    if not TEMPLATE_LIBRARY:
        return [{"name": "fallback", "template": rng.choice(TEMPLATES), "category": "fallback"}]
    heavy_pool = [entry for entry in TEMPLATE_LIBRARY if entry["name"] in HEAVY_TEMPLATE_NAMES]
    if heavy_pool and rng.random() < 0.85:
        return heavy_pool
    return TEMPLATE_LIBRARY


def _select_template_entry(rng: random.Random) -> dict[str, str]:
    pool = _template_choice_pool(rng)
    weights = [
        _TEMPLATE_WEIGHT_OVERRIDES.get(entry["name"], 1 + (4 if entry["name"] in HEAVY_TEMPLATE_NAMES else 0))
        for entry in pool
    ]
    return rng.choices(pool, weights=weights, k=1)[0]


def _weighted_template_entry(rng: random.Random) -> dict[str, str]:
    if not TEMPLATE_LIBRARY:
        return {"name": "fallback", "template": rng.choice(TEMPLATES), "category": "fallback"}

    heavy_pool = [entry for entry in TEMPLATE_LIBRARY if entry["name"] in HEAVY_TEMPLATE_NAMES]
    if heavy_pool and rng.random() < 0.8:
        pool = heavy_pool
    else:
        pool = TEMPLATE_LIBRARY

    weights = [
        _TEMPLATE_WEIGHT_OVERRIDES.get(entry["name"], 1 + (3 if entry["name"] in HEAVY_TEMPLATE_NAMES else 0))
        for entry in pool
    ]
    return rng.choices(pool, weights=weights, k=1)[0]


def _local_mutate_seed(seed_text: str, rng: random.Random) -> str:
    mutated = seed_text
    mutated = mutated.replace(" add ", " sub ", 1) if " add " in mutated else mutated
    mutated = mutated.replace(" mul ", " add ", 1) if " mul " in mutated else mutated
    mutated = mutated.replace(" xor ", " and ", 1) if " xor " in mutated else mutated
    if " i32 " in mutated:
        mutated = mutated.replace(" i32 1", f" i32 {rng.randint(5, 23)}", 1)
        mutated = mutated.replace(" i32 2", f" i32 {rng.randint(7, 31)}", 1)
    if "br label" in mutated:
        mutated = mutated.replace("br label", "br i1 true, label", 1)
    if "ret i32" in mutated and rng.random() < 0.5:
        mutated += f"\n  %mut_extra = add i32 {rng.randint(11, 41)}, {rng.randint(2, 9)}"
    if not mutated.endswith("\n"):
        mutated += "\n"
    return _decorate_snippet(mutated, rng, label="mut")


def _build_size_pad(label: str, strength: int, seed: int) -> str:
    # Keep the pad small, valid, and deterministic. The helper is intentionally
    # unused so O3 can often drop it, while O0 keeps the extra code around.
    strength = max(2, min(12, strength))
    blob_len = 16 + (seed % 5) * 4 + strength * 8
    blob_payload = "A" * max(8, blob_len - 1)
    blob_name = f"@{label}_blob_{seed}"
    dead_ops = max(2, min(8, strength))

    lines = [
        f"{blob_name} = private unnamed_addr constant [{blob_len} x i8] c\"{blob_payload}\\00\"",
        f"define internal i32 @{label}_pad_{seed}(i32 %seed) {{",
        "entry:",
        f"  %seed_base = add i32 %seed, {1 + (seed % 7)}",
        f"  %cond = icmp eq i32 %seed, {-1 - (seed % 3)}",
        "  br i1 %cond, label %dead, label %exit",
        "",
        "dead:",
        f"  %blobptr = getelementptr [{blob_len} x i8], [{blob_len} x i8]* {blob_name}, i32 0, i32 0",
        "  %blobv = load volatile i8, i8* %blobptr",
        "  %blobw = zext i8 %blobv to i32",
        "  %acc0 = add i32 %seed_base, %blobw",
    ]

    for i in range(1, dead_ops):
        op = ("add", "mul", "xor", "sub")[i % 4]
        rhs = (seed + i * 5) % 31 + 2
        prev = f"%acc{i - 1}"
        lines.append(f"  %acc{i} = {op} i32 {prev}, {rhs}")

    lines.extend([
        "  br label %exit",
        "",
        "exit:",
        f"  %phi = phi i32 [ %seed_base, %entry ], [ %acc{dead_ops - 1}, %dead ]",
        "  ret i32 %phi",
        "}",
    ])
    return "\n".join(lines)


def _label_index(label: str) -> int:
    match = re.search(r"(\d+)$", label)
    return int(match.group(1)) if match else 0


def _decorate_snippet(snippet: str, rng: random.Random, label: str) -> str:
    if not snippet.endswith("\n"):
        snippet += "\n"
    ret_marker = re.search(r"(?m)^(\s*)ret i32\s+(.+)$", snippet)
    if ret_marker and "@main" in snippet:
        indent = ret_marker.group(1)
        ret_val = ret_marker.group(2).strip()
        seed = rng.randint(10, 999)
        idx = _label_index(label)
        # Produce smaller, gradual deltas: short chains (few to a few dozen ops)
        chain_len = rng.randint(6, 32) + (idx % 4) * 4
        chain_ops = ["add", "mul", "xor", "sub"]
        chain_lines = [f"{indent}%size_{seed}_0 = add i32 {ret_val}, {seed % 29 + 3}"]
        for step in range(1, chain_len):
            op = chain_ops[step % len(chain_ops)]
            rhs = (seed + idx + step * 3) % 31 + 2
            chain_lines.append(f"{indent}%size_{seed}_{step} = {op} i32 %size_{seed}_{step - 1}, {rhs}")
        chain_lines.append(f"{indent}ret i32 %size_{seed}_{chain_len - 1}")
        snippet = re.sub(r"(?m)^(\s*)ret i32\s+.+$", "\n".join(chain_lines), snippet, count=1)

        # Keep a small dead helper so the generated IR stays visibly different
        # even when the main function is optimized aggressively.
        strength = 6 + (idx % 3) * 2 + rng.randint(0, 3)
        pad = _build_size_pad(label, strength, seed)
        return snippet + "\n\n" + pad + "\n"

    return snippet


def _pick_template(rng: random.Random, idx: int) -> str:
    template_entry = _select_template_entry(rng)
    template = template_entry["template"]
    const_val = rng.randint(1, 9)
    rendered = template.format(id=idx, c=const_val)
    return _decorate_snippet(rendered, rng, label=f"gen_{idx}")


def generate_ir_snippets(config: GenerationConfig) -> Iterable[str]:
    rng = random.Random(config.seed)
    seed_texts = _load_seed_texts(config.seed_dir)
    if config.backend == "openai":
        for i in range(config.count):
            if config.mode == "mutate" and seed_texts:
                seed_text = rng.choice(seed_texts)
                prompt = (
                    f"{config.mutate_prompt_template}\n\n; Original IR:\n"
                    f"{seed_text}\n; Mutated IR:\n"
                )
            else:
                prompt = f"{config.prompt_template}\n\n; id: {i}\n"
            result = _openai_generate(prompt, config.model)
            if result:
                yield _decorate_snippet(result + "\n", rng, label=f"ai_{i}")
                continue
            if config.mode == "mutate" and seed_texts:
                yield _local_mutate_seed(rng.choice(seed_texts), rng)
            else:
                yield _pick_template(rng, i)
        return

    for i in range(config.count):
        if config.mode == "mutate" and seed_texts:
            yield _local_mutate_seed(rng.choice(seed_texts), rng)
        else:
            yield _pick_template(rng, i)


def write_generated_ir(output_dir: Path, config: GenerationConfig) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created: List[Path] = []
    timestamp = int(time.time())
    for idx, snippet in enumerate(generate_ir_snippets(config)):
        file_path = output_dir / f"gen_{timestamp}_{idx}.ll"
        file_path.write_text(snippet)
        created.append(file_path)
    return created
