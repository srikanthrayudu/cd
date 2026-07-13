"""
scripts/generate_varied_binary_sizes.py — Generate IR files with intentionally
varied binary sizes so the O0 vs O3 comparison table always has interesting data.

Design
------
Each file contains:
  1. A @main with a volatile global-blob load followed by an arithmetic chain.
     Chain length and blob size vary deterministically with the file index so
     consecutive files produce gradually different binary sizes.
  2. Optionally an injected dead branch — kept by -O0, eliminated by -O3 —
     increasing the per-file size delta.

All constants (chain lengths, blob sizes, pad counts, seeds, labels) come from
the ``varied_binaries`` section of config.yaml.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from src.config import cfg, ProjectPaths


# ---------------------------------------------------------------------------
# Load the varied_binaries sub-section from config.yaml
# ---------------------------------------------------------------------------

def _load_varied_cfg() -> dict:
    with (ROOT / "config.yaml").open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return raw.get("varied_binaries", {})


VC = _load_varied_cfg()


# ---------------------------------------------------------------------------
# IR builders
# ---------------------------------------------------------------------------

def _build_varied_ir(idx: int, seed: int, label: str) -> str:
    """
    Build one LLVM IR function whose binary size varies predictably with *idx*.

    The arithmetic chain length and global-blob size are both driven by config
    values so the caller can tune how gradually sizes differ between files.
    """
    chain_base   = int(VC.get("chain_base",   6))
    chain_range  = int(VC.get("chain_range",  24))
    chain_stride = int(VC.get("chain_stride", 3))
    blob_base    = int(VC.get("blob_base",    8))
    blob_mod     = int(VC.get("blob_mod",     128))
    blob_scale   = int(VC.get("blob_scale",   4))

    chain_len    = chain_base + ((seed + idx) % chain_range) + (idx % 4) * chain_stride
    blob_len     = blob_base  + ((seed + idx) % blob_mod) * blob_scale
    blob_payload = "A" * max(4, blob_len - 1)
    blob_name    = f"{label}_blob_{seed}"
    base_val     = (seed % 7) + idx + 1

    ops = ("add", "mul", "xor", "sub")
    lines = [
        "define i32 @main() {",
        "entry:",
        f"  %ptr = getelementptr [{blob_len} x i8], [{blob_len} x i8]* @{blob_name}, i32 0, i32 0",
        "  %b0 = load volatile i8, i8* %ptr",
        "  %b1 = zext i8 %b0 to i32",
        f"  %v0 = add i32 {base_val}, %b1",
    ]
    for step in range(1, chain_len + 1):
        op  = ops[step % len(ops)]
        rhs = (seed + idx + step * 3) % 7 + 1
        lines.append(f"  %v{step} = {op} i32 %v{step - 1}, {rhs}")

    lines.append(f"  ret i32 %v{chain_len}")
    lines.append("}")
    lines.append(
        f"@{blob_name} = private unnamed_addr constant "
        f"[{blob_len} x i8] c\"{blob_payload}\\00\""
    )
    return "\n".join(lines) + "\n"


def _inject_dead_branch(ir: str, *, label: str, pad_seed: int, pad_ops: int) -> str:
    """
    Replace ``ret i32 <val>`` with a never-taken conditional that contains
    *pad_ops* dead instructions.  O0 keeps every instruction; O3 deletes them.

    The condition ``icmp eq i32 <seed % 11>, -1`` is always false at runtime.
    """
    lines   = ir.rstrip().splitlines()
    ret_idx = next(
        (i for i, ln in enumerate(lines) if ln.lstrip().startswith("ret i32 ")),
        None,
    )
    if ret_idx is None:
        return ir  # no ret — leave unchanged

    indent    = lines[ret_idx][: len(lines[ret_idx]) - len(lines[ret_idx].lstrip())]
    ret_value = lines[ret_idx].lstrip()[len("ret i32 "):]
    dead_lbl  = f"dead_{label}"
    cont_lbl  = f"cont_{label}"

    branch = [
        f"{indent}%pad_cond = icmp eq i32 {pad_seed % 11}, -1",
        f"{indent}br i1 %pad_cond, label %{dead_lbl}, label %{cont_lbl}",
        "",
    ]
    dead = [f"{dead_lbl}:", f"  %dead0 = add i32 {pad_seed}, 7"]
    for i in range(1, pad_ops):
        op  = "add" if i % 2 else "mul"
        rhs = (pad_seed + i) % 17 + 2
        dead.append(f"  %dead{i} = {op} i32 %dead{i - 1}, {rhs}")
    dead += [f"  br label %{cont_lbl}", "", f"{cont_lbl}:", f"  ret i32 {ret_value}"]

    rewritten = lines[:ret_idx] + branch + dead + lines[ret_idx + 1:]
    return "\n".join(rewritten).rstrip() + "\n"


# ---------------------------------------------------------------------------
# File generation
# ---------------------------------------------------------------------------

def _generate_files(
    paths:  ProjectPaths,
    seed:   int,
    count:  int,
    labels: list[str],
) -> list[Path]:
    """Generate *count* varied IR files into ``valid_ir/`` and return their paths."""
    pad_base  = int(VC.get("pad_base",  4))
    pad_range = int(VC.get("pad_range", 8))

    # Clear stale varied files so the table stays clean
    for path in paths.valid_dir.glob("varied_*.ll"):
        path.unlink()

    created: list[Path] = []
    for idx in range(count):
        file_seed = seed + idx * 101
        label     = labels[idx]
        ir        = _build_varied_ir(idx, file_seed, label)

        # Inject a dead branch into every other file for extra O0/O3 contrast
        if (file_seed + idx) % 2 == 0:
            pad_ops = pad_base + (file_seed % pad_range)
            ir = _inject_dead_branch(ir, label=label, pad_seed=file_seed, pad_ops=pad_ops)

        out_path = paths.valid_dir / f"varied_{idx:02d}_{label}.ll"
        out_path.write_text(ir, encoding="utf-8")
        created.append(out_path)

    return created


# ---------------------------------------------------------------------------
# Result parsing + pretty-print
# ---------------------------------------------------------------------------

def _parse_binary_sizes(executions_path: Path) -> list[tuple[str, int, int]]:
    """Return ``[(name, o0_size, o3_size), …]`` for all paired executions."""
    if not executions_path.exists():
        return []
    o0: dict[str, int] = {}
    o3: dict[str, int] = {}
    for line in executions_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = row.get("name")
        mode = row.get("mode")
        size = row.get("binary_size")
        if name and isinstance(size, (int, float)):
            if mode == "O0":
                o0[str(name)] = int(size)
            elif mode == "O3":
                o3[str(name)] = int(size)
    return [(n, o0[n], o3[n]) for n in sorted(o0) if n in o3]


def _print_table(comparisons: list[tuple[str, int, int]]) -> None:
    if not comparisons:
        print("No paired O0/O3 results found.")
        return
    col = 42
    print(f"{'Program':<{col}} {'O0 (B)':>8} {'O3 (B)':>8} {'Delta':>8}  Direction")
    print("-" * (col + 34))
    for name, o0, o3 in comparisons:
        diff = o0 - o3
        print(f"{name:<{col}} {o0:>8} {o3:>8} {diff:>+8}  {'smaller' if diff >= 0 else 'larger'}")
    total_o0 = sum(o0 for _, o0, _ in comparisons)
    total_o3 = sum(o3 for _, _, o3 in comparisons)
    savings  = total_o0 - total_o3
    pct      = savings / total_o0 * 100 if total_o0 else 0.0
    print("-" * (col + 34))
    print(f"{'TOTAL':<{col}} {total_o0:>8} {total_o3:>8} {savings:>+8}  {pct:.1f}% reduction")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    default_seed   = int(VC.get("seed",  1337))
    default_count  = int(VC.get("count", 10))
    default_labels = list(VC.get("labels", []))

    parser = argparse.ArgumentParser(
        description=(
            "Generate varied IR files and run O0/O3 differential compilation "
            "to produce a binary-size comparison table."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--seed",   type=int,  default=default_seed,  help="Base RNG seed.")
    parser.add_argument("--count",  type=int,  default=default_count, help="Number of files.")
    parser.add_argument("--labels", nargs="*", default=default_labels, help="Labels for file names.")
    parser.add_argument("--no-run", action="store_true",              help="Generate files only; skip compilation.")
    return parser


def main() -> None:
    args  = _build_parser().parse_args()
    paths = ProjectPaths.from_config(cfg, ROOT)
    paths.ensure_dirs()

    # Auto-extend labels if fewer were supplied than --count requests
    labels = list(args.labels)
    while len(labels) < args.count:
        labels.append(f"size_case_{len(labels):02d}")

    created = _generate_files(paths, seed=args.seed, count=args.count, labels=labels)
    print(f"Generated {len(created)} varied IR files → {paths.valid_dir}")
    for p in created:
        print(f"  {p.name}")

    if args.no_run:
        return

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_differential.py")],
        check=True,
    )

    comparisons = _parse_binary_sizes(
        paths.results_dir / cfg.reporting.files["executions"]
    )
    print()
    _print_table(comparisons)


if __name__ == "__main__":
    main()
