from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ProjectPaths
DEFAULT_LABELS = [
    "size_case_00",
    "size_case_01",
    "size_case_02",
    "size_case_03",
    "size_case_04",
    "size_case_05",
    "size_case_06",
    "size_case_07",
    "size_case_08",
    "size_case_09",
]


def _clear_ll_files(directory: Path) -> None:
    if not directory.exists():
        return
    for path in directory.glob("*.ll"):
        path.unlink()


def _dead_pad_lines(pad_name: str, pad_seed: int, pad_ops: int) -> list[str]:
    lines = [f"{pad_name}:"]
    lines.append(f"  %pad0 = add i32 {pad_seed}, 1")
    for idx in range(1, pad_ops):
        op = "add" if idx % 2 else "mul"
        rhs = idx + 1 if op == "add" else 2 + (idx % 5)
        prev = f"%pad{idx - 1}"
        lines.append(f"  %pad{idx} = {op} i32 {prev}, {rhs}")
    lines.append(f"  ret i32 %pad{pad_ops - 1}")
    return lines


def _build_varied_ir(idx: int, seed: int, label: str) -> str:
    # Small-to-moderate controllable chains to more reliably yield
    # non-zero O0 vs O3 deltas. Increase the possible chain length and
    # add a bit more variability so some generated programs contain
    # work that's easily removed by -O3 but retained by -O0.
    chain_len = 6 + ((seed + idx) % 24) + (idx % 4) * 3
    base_a = (seed % 7) + idx + 1
    base_b = (seed % 5) + 1

    # Append a small global blob whose size varies with seed+idx to create
    # gradual binary-size differences between O0 and O3 builds. We compute
    # the blob size first so we can reference it in the GEP/load that
    # appears inside @main.
    blob_len = 8 + ((seed + idx) % 128) * 4
    blob_payload = "A" * max(4, blob_len - 1)
    blob_name = f"{label}_blob_{seed}"

    lines = [
        "define i32 @main() {",
        "entry:",
        # Make the global blob an actually-used object by doing a volatile
        # load from it. Volatile loads prevent the optimizer from folding
        # away the access and ensure the global's size is preserved in
        # optimized builds, which makes O3 sizes vary with the blob length.
        f"  %ptr = getelementptr [{blob_len} x i8], [{blob_len} x i8]* @{blob_name}, i32 0, i32 0",
        "  %b0 = load volatile i8, i8* %ptr",
        "  %b1 = zext i8 %b0 to i32",
        f"  %v0 = add i32 {base_a}, %b1",
    ]

    ops = ("add", "mul", "xor", "sub")
    for step in range(1, chain_len + 1):
        op = ops[step % len(ops)]
        rhs = (seed + idx + step * 3) % 7 + 1
        prev = f"%v{step - 1}"
        lines.append(f"  %v{step} = {op} i32 {prev}, {rhs}")

    lines.append(f"  ret i32 %v{chain_len}")
    lines.append("}")
    # Define the global blob after the function; naming uses @ so it matches
    # the GEP used above.
    lines.append(f"@{blob_name} = private unnamed_addr constant [{blob_len} x i8] c\"{blob_payload}\\00\"")
    return "\n".join(lines) + "\n"


def _inject_dead_branch(ir: str, *, pad_name: str, pad_seed: int, pad_ops: int) -> str:
    lines = ir.rstrip().splitlines()
    ret_idx = next((idx for idx, line in enumerate(lines) if line.lstrip().startswith("ret i32 ")), None)
    if ret_idx is None:
        raise ValueError(f"Could not find a return instruction in template for {pad_name}")

    indent = lines[ret_idx][: len(lines[ret_idx]) - len(lines[ret_idx].lstrip())]
    ret_line = lines[ret_idx].lstrip()
    ret_value = ret_line[len("ret i32 ") :]

    dead_label = f"dead_pad_{pad_name}"
    return_label = f"return_pad_{pad_name}"
    branch_block = [
        f"{indent}%pad_cond = icmp eq i32 {pad_seed % 11}, -1",
        f"{indent}br i1 %pad_cond, label %{dead_label}, label %{return_label}",
        "",
    ]
    dead_block = [
        f"{dead_label}:",
        f"  %dead0 = add i32 {pad_seed}, 7",
    ]
    for idx in range(1, pad_ops):
        op = "add" if idx % 2 else "mul"
        rhs = (pad_seed + idx) % 17 + 2
        prev = f"%dead{idx - 1}"
        dead_block.append(f"  %dead{idx} = {op} i32 {prev}, {rhs}")
    dead_block.extend([f"  br label %{return_label}", "", f"{return_label}:", f"  ret i32 {ret_value}"])

    rewritten = lines[:ret_idx] + branch_block + dead_block + lines[ret_idx + 1 :]
    return "\n".join(rewritten).rstrip() + "\n"


def _generate_varied_files(paths: ProjectPaths, *, seed: int, count: int, labels: list[str]) -> list[Path]:
    _clear_ll_files(paths.valid_dir)
    rng = random.Random(seed)
    created: list[Path] = []

    for idx in range(count):
        sample_seed = seed + idx * 101
        label = labels[idx] if idx < len(labels) else f"size_case_{idx:02d}"
        ir = _build_varied_ir(idx, sample_seed, label)

        # Occasionally inject an explicit dead branch/pad block that
        # produces more code at -O0 but can be eliminated at -O3. This
        # increases the chance of a non-zero binary-size diff.
        if (sample_seed + idx) % 2 == 0:
            pad_ops = 4 + ((sample_seed) % 8)
            ir = _inject_dead_branch(ir, pad_name=label, pad_seed=sample_seed, pad_ops=pad_ops)

        file_path = paths.valid_dir / f"varied_{idx:02d}_{label}.ll"
        file_path.write_text(ir)
        created.append(file_path)
    return created


def _parse_results(results_path: Path) -> list[tuple[str, int, int]]:
    rows: dict[str, dict[str, int]] = {}
    if not results_path.exists():
        return []
    for line in results_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        name = row.get("name")
        mode = row.get("mode")
        size = row.get("binary_size")
        if not name or mode not in {"O0", "O3"} or size is None:
            continue
        rows.setdefault(str(name), {})[str(mode)] = int(size)
    output: list[tuple[str, int, int]] = []
    for name in sorted(rows):
        data = rows[name]
        if "O0" in data and "O3" in data:
            output.append((name, data["O0"], data["O3"]))
    return output


def _write_summary_markdown(comparisons: list[tuple[str, int, int]], output_path: Path) -> None:
    if not comparisons:
        output_path.write_text("# Varied O0 vs O3 Comparison\n\nNo paired results were produced.\n")
        return

    total_o0 = sum(o0 for _, o0, _ in comparisons)
    total_o3 = sum(o3 for _, _, o3 in comparisons)
    total_diff = total_o0 - total_o3
    reduction_pct = (total_diff / total_o0 * 100) if total_o0 else 0.0

    lines = [
        "# Varied O0 vs O3 Comparison",
        "",
        f"- Paired comparisons: {len(comparisons)}",
        f"- Aggregate O0 size: {total_o0:,} bytes",
        f"- Aggregate O3 size: {total_o3:,} bytes",
        f"- Net savings: {total_diff:,} bytes ({reduction_pct:.2f}% reduction)",
        "",
        "| Program | O0 Size | O3 Size | Diff | Direction |",
        "| :--- | ---: | ---: | ---: | :--- |",
    ]

    for name, o0, o3 in comparisons:
        diff = o0 - o3
        direction = "Smaller" if diff >= 0 else "Larger"
        lines.append(f"| {name} | {o0:,} | {o3:,} | {diff:,} | {direction} |")

    lines.append("")
    output_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 10 varied O0/O3 comparison files and compile them.")
    parser.add_argument("--seed", type=int, default=1337, help="Base seed for deterministic variation")
    parser.add_argument("--count", type=int, default=10, help="Number of files to generate")
    parser.add_argument("--labels", nargs="*", default=DEFAULT_LABELS, help="Labels used in the generated file names")
    parser.add_argument("--no-run", action="store_true", help="Only generate files; do not run differential compilation")
    args = parser.parse_args()

    root = Path.cwd()
    paths = ProjectPaths.from_root(root)
    paths.ensure_dirs()

    labels = args.labels[: args.count]
    if len(labels) < args.count:
        raise SystemExit(f"Need at least {args.count} labels; got {len(labels)}")

    created = _generate_varied_files(paths, seed=args.seed, count=args.count, labels=labels)
    print(f"Generated {len(created)} varied IR files in {paths.valid_dir}")
    for path in created:
        print(f"  - {path.name}")

    if args.no_run:
        return

    subprocess.run([sys.executable, str(ROOT_DIR / "scripts" / "run_differential.py")], check=True)

    comparisons = _parse_results(paths.results_dir / "executions.jsonl")
    _write_summary_markdown(comparisons, paths.results_dir / "summary.md")
    if not comparisons:
        print("No O0/O3 binary size rows were produced.")
        return

    print()
    print("Program\tO0\tO3\tDiff\tDirection")
    for name, o0, o3 in comparisons[: args.count]:
        diff = o0 - o3
        direction = "Smaller" if diff >= 0 else "Larger"
        print(f"{name}\t{o0}\t{o3}\t{diff}\t{direction}")


if __name__ == "__main__":
    main()

