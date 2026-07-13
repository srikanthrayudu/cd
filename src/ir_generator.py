"""
ir_generator.py — LLVM IR generation.

Responsibilities
----------------
1. Pick an IR template (or call an LLM backend) and render it into a
   concrete LLVM IR snippet.
2. Append a size-padding decorator so O0 and O3 binaries differ visibly.
3. Write each snippet to a timestamped file in the output directory.

All tuneable values (counts, seeds, weights, prompts) come from ``cfg``
(see src/config.py and config.yaml).  No magic numbers live here.
"""
from __future__ import annotations

import importlib
import os
import random
import re
import time
from pathlib import Path
from typing import Iterable, List, Optional

from src.config import cfg
from src.templates import TEMPLATE_LIBRARY


# ---------------------------------------------------------------------------
# Template selection helpers
# ---------------------------------------------------------------------------

def _is_heavy(name: str) -> bool:
    """Return True if this template name is in the 'heavy' list from config."""
    return name in cfg.templates.heavy_names


def _template_weight(name: str) -> int:
    """Return the sampling weight for a template, with config override support."""
    base = cfg.templates.weights.get(name)
    if base is not None:
        return base
    return 5 if _is_heavy(name) else 1


def _select_template(rng: random.Random) -> dict:
    """
    Select one template entry from TEMPLATE_LIBRARY.

    With probability ``heavy_bias`` the pool is restricted to heavy
    templates; otherwise the full library is used.  Within each pool
    entries are drawn according to ``_template_weight``.
    """
    heavy_pool = [e for e in TEMPLATE_LIBRARY if _is_heavy(e["name"])]

    if heavy_pool and rng.random() < cfg.templates.heavy_bias:
        pool = heavy_pool
    else:
        pool = TEMPLATE_LIBRARY

    weights = [_template_weight(e["name"]) for e in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Size-padding decorator
# ---------------------------------------------------------------------------

def _decorator_chain_length(idx: int, rng: random.Random) -> int:
    """
    Compute the length of the arithmetic chain appended before ret.
    Varies with idx so different templates produce visibly different binary sizes.
    """
    dec = cfg.templates.decorator
    base = rng.randint(dec.chain_min, dec.chain_max)
    return base + (idx % 4) * dec.chain_stride


def _build_dead_helper(label: str, seed: int) -> str:
    """
    Return an internal helper function that is never called from main.
    O0 keeps it in the binary; O3 deletes it as dead code.
    """
    blob_len = 24 + (seed % 5) * 4
    dead_ops = 4 + (seed % 4)
    lines = [
        f"define internal i32 @{label}_dead_{seed}(i32 %x) {{",
        "entry:",
        f"  %base = add i32 %x, {1 + (seed % 7)}",
        f"  %cond = icmp eq i32 %x, {-1 - (seed % 3)}",
        "  br i1 %cond, label %never, label %done",
        "",
        "never:",
        f"  %acc0 = add i32 %base, {seed % 17 + 2}",
    ]
    for i in range(1, dead_ops):
        op = ("add", "mul", "xor", "sub")[i % 4]
        rhs = (seed + i * 5) % 31 + 2
        lines.append(f"  %acc{i} = {op} i32 %acc{i - 1}, {rhs}")
    lines.extend([
        "  br label %done",
        "",
        "done:",
        f"  %phi = phi i32 [ %base, %entry ], [ %acc{dead_ops - 1}, %never ]",
        "  ret i32 %phi",
        "}",
    ])
    return "\n".join(lines)


def _decorate(snippet: str, idx: int, rng: random.Random, label: str) -> str:
    """
    Append a deterministic arithmetic chain before the final ``ret i32``
    instruction and attach a dead helper function.

    The chain makes O0 binaries visibly larger than O3 binaries, because
    O3 constant-folds or DCE's the whole suffix.
    """
    if not snippet.endswith("\n"):
        snippet += "\n"

    # Only decorate if there is a @main and a "ret i32" to anchor on.
    ret_match = re.search(r"(?m)^(\s*)ret i32\s+(.+)$", snippet)
    if ret_match is None or "@main" not in snippet:
        return snippet

    indent   = ret_match.group(1)
    ret_val  = ret_match.group(2).strip()
    seed     = rng.randint(10, 999)
    length   = _decorator_chain_length(idx, rng)
    ops      = ["add", "mul", "xor", "sub"]

    chain: List[str] = [
        f"{indent}%pad_{seed}_0 = add i32 {ret_val}, {seed % 29 + 3}"
    ]
    for step in range(1, length):
        op  = ops[step % len(ops)]
        rhs = (seed + idx + step * 3) % 31 + 2
        chain.append(f"{indent}%pad_{seed}_{step} = {op} i32 %pad_{seed}_{step - 1}, {rhs}")
    chain.append(f"{indent}ret i32 %pad_{seed}_{length - 1}")

    snippet = re.sub(
        r"(?m)^(\s*)ret i32\s+.+$",
        "\n".join(chain),
        snippet,
        count=1,
    )

    dead_helper = _build_dead_helper(label, seed)
    return snippet + "\n\n" + dead_helper + "\n"


# ---------------------------------------------------------------------------
# LLM backend
# ---------------------------------------------------------------------------

_ENV_LOADED = False


def _load_dotenv() -> None:
    """Load .env if present so OPENAI_API_KEY etc. are available."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    _ENV_LOADED = True


def _openai_generate(prompt: str, model: str) -> Optional[str]:
    """Call the OpenAI Responses API and return the raw text, or None on failure."""
    _load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        openai_mod = importlib.import_module("openai")
        client = openai_mod.OpenAI()
        response = client.responses.create(model=model, input=prompt)
    except Exception:
        return None

    chunks = []
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    chunks.append(content.text)
    return "\n".join(chunks).strip() if chunks else None


# ---------------------------------------------------------------------------
# Seed mutation (template-only fallback for LLM mutate mode)
# ---------------------------------------------------------------------------

def _local_mutate_seed(seed_text: str, rng: random.Random) -> str:
    """Apply a handful of deterministic text-level mutations to a seed IR."""
    text = seed_text
    substitutions = [
        (" add ", " sub "),
        (" mul ", " add "),
        (" xor ", " and "),
    ]
    for old, new in substitutions:
        if old in text:
            text = text.replace(old, new, 1)
            break

    # Bump one small constant
    for old_const, new_const in [(" i32 1", f" i32 {rng.randint(5, 23)}"),
                                  (" i32 2", f" i32 {rng.randint(7, 31)}")]:
        if old_const in text:
            text = text.replace(old_const, new_const, 1)
            break

    # Convert an unconditional branch to an always-true conditional
    if "br label" in text:
        text = text.replace("br label", "br i1 true, label", 1)

    if not text.endswith("\n"):
        text += "\n"
    return text


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def _pick_template(idx: int, rng: random.Random) -> str:
    """Render one template entry and attach the size-padding decorator."""
    entry      = _select_template(rng)
    const_val  = rng.randint(1, 9)
    rendered   = entry["template"].format(id=idx, c=const_val)
    label      = f"gen_{idx}"
    return _decorate(rendered, idx, rng, label)


def _load_seed_texts(seed_dir: Optional[Path]) -> List[str]:
    """Return IR texts from all *.ll files in seed_dir (empty list if absent)."""
    if not seed_dir or not seed_dir.exists():
        return []
    return [p.read_text(encoding="utf-8") for p in sorted(seed_dir.glob("*.ll"))]


def generate_ir_snippets(
    count:    int,
    seed:     int,
    backend:  str,
    model:    str,
    mode:     str,
    seed_dir: Optional[Path] = None,
) -> Iterable[str]:
    """
    Parameters
    ----------
    count:    number of snippets to produce
    seed:     RNG seed for reproducibility
    backend:  "template" | "openai"
    model:    LLM model name (only relevant when backend == "openai")
    mode:     "generate" | "mutate"
    seed_dir: directory with *.ll files used as mutation seeds
    """
    rng        = random.Random(seed)
    seed_texts = _load_seed_texts(seed_dir)

    for i in range(count):
        if backend == "openai":
            if mode == "mutate" and seed_texts:
                prompt = (
                    cfg.generation.llm_mutate_prompt
                    + "\n\n; Original IR:\n"
                    + rng.choice(seed_texts)
                    + "\n; Mutated IR:\n"
                )
            else:
                prompt = f"{cfg.generation.llm_prompt}\n\n; id: {i}\n"

            result = _openai_generate(prompt, model)
            if result:
                yield _decorate(result + "\n", i, rng, f"ai_{i}")
                continue
            # Fall back to template/local mutation on API failure
            if mode == "mutate" and seed_texts:
                yield _local_mutate_seed(rng.choice(seed_texts), rng)
                continue

        if mode == "mutate" and seed_texts:
            yield _local_mutate_seed(rng.choice(seed_texts), rng)
        else:
            yield _pick_template(i, rng)


def write_generated_ir(
    output_dir: Path,
    count:      int,
    seed:       int,
    backend:    str,
    model:      str,
    mode:       str,
    seed_dir:   Optional[Path] = None,
) -> list[Path]:
    """
    Generate *count* IR files, write them to *output_dir*, and return the
    list of paths created.

    File names include a Unix timestamp so successive runs do not collide.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    created: List[Path] = []

    for idx, snippet in enumerate(
        generate_ir_snippets(count, seed, backend, model, mode, seed_dir)
    ):
        path = output_dir / f"gen_{timestamp}_{idx}.ll"
        path.write_text(snippet, encoding="utf-8")
        created.append(path)

    return created
