from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


@dataclass
class GenerationConfig:
    count: int = 5
    seed: int = 1337
    backend: str = "template"
    model: str = "gpt-4o-mini"
    mode: str = "generate"
    seed_dir: Optional[Path] = None
    prompt_template: str = (
        "Generate a single valid LLVM IR function. "
        "Return only LLVM IR, no prose.\n"
        "Constraints: SSA form, i32 ops, and end with ret."
    )
    mutate_prompt_template: str = (
        "Mutate the following LLVM IR while keeping it valid. "
        "Return only LLVM IR, no prose.\n"
        "Prefer small edits (opcode swap, constant tweak, or control-flow split)."
    )


TEMPLATES: List[str] = [
    """define i32 @add_const_{id}(i32 %x) {{
entry:
  %v = add i32 %x, {c}
  ret i32 %v
}}\n""",
    """define i32 @mul_const_{id}(i32 %x) {{
entry:
  %v = mul i32 %x, {c}
  ret i32 %v
}}\n""",
    """define i32 @max_{id}(i32 %a, i32 %b) {{
entry:
  %cmp = icmp sgt i32 %a, %b
  br i1 %cmp, label %then, label %else
then:
  br label %merge
else:
  br label %merge
merge:
  %res = phi i32 [ %a, %then ], [ %b, %else ]
  ret i32 %res
}}\n""",
    """define i32 @branch_id_{id}(i32 %x) {{
entry:
  %cmp = icmp sgt i32 %x, {c}
  br i1 %cmp, label %then, label %else
then:
  %a = add i32 %x, 1
  br label %merge
else:
  %b = sub i32 %x, 1
  br label %merge
merge:
  %res = phi i32 [ %a, %then ], [ %b, %else ]
  ret i32 %res
}}\n""",
    """define i32 @loop_sum_{id}(i32 %n) {{
entry:
  %i = alloca i32
  %sum = alloca i32
  store i32 0, i32* %i
  store i32 0, i32* %sum
  br label %loop
loop:
  %i_val = load i32, i32* %i
  %cmp = icmp slt i32 %i_val, %n
  br i1 %cmp, label %body, label %exit
body:
  %sum_val = load i32, i32* %sum
  %sum_next = add i32 %sum_val, %i_val
  store i32 %sum_next, i32* %sum
  %i_next = add i32 %i_val, 1
  store i32 %i_next, i32* %i
  br label %loop
exit:
  %sum_out = load i32, i32* %sum
  ret i32 %sum_out
}}\n""",
]


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
        from openai import OpenAI
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


def _local_mutate_seed(seed_text: str, rng: random.Random) -> str:
    mutated = seed_text
    mutated = mutated.replace(" add ", " sub ", 1) if " add " in mutated else mutated
    if " i32 " in mutated:
        mutated = mutated.replace(" i32 1", f" i32 {rng.randint(2, 9)}", 1)
    if not mutated.endswith("\n"):
        mutated += "\n"
    return mutated


def _pick_template(rng: random.Random, idx: int) -> str:
    template = rng.choice(TEMPLATES)
    const_val = rng.randint(1, 9)
    return template.format(id=idx, c=const_val)


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
                yield result + "\n"
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
