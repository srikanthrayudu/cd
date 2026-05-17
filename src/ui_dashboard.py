from __future__ import annotations

import difflib
import csv
import html
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, cast

try:
    import streamlit as _streamlit
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    _streamlit = None

st: Any = _streamlit

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
EVAL_DIR = ROOT / "evaluation"
LOGS_DIR = ROOT / "logs"
OPT_IR_DIR = RESULTS_DIR / "optimized_ir"
DIFF_DIR = RESULTS_DIR / "code_diffs"


# -----------------------------
# Data helpers
# -----------------------------

def format_bytes(size_bytes: int | float) -> str:
    if size_bytes is None:
        return "0 B"
    size = float(size_bytes)
    if size == 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def get_file_size(filepath: os.PathLike[str] | str) -> int:
    try:
        return os.path.getsize(filepath)
    except OSError:
        return 0


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(read_text_file(path))
    except Exception:
        return {}


def read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    return _load_jsonl_rows(path)


def _load_run_manifest() -> dict[str, int]:
    manifest_path = RESULTS_DIR / "run_manifest.json"
    data = read_json_file(manifest_path) if manifest_path.exists() else {}
    manifest: dict[str, int] = {}
    for key in ("generated", "mutated", "valid", "invalid"):
        value = data.get(key)
        if isinstance(value, int):
            manifest[key] = value
    return manifest


def remove_markdown_section(markdown_text: str, heading: str) -> str:
    lines = markdown_text.splitlines()
    target = heading.strip()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == target:
            start = idx
            break
    if start is None:
        return markdown_text

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break

    trimmed = lines[:start] + lines[end:]
    return "\n".join(trimmed).strip() + "\n"


def load_metrics() -> dict[str, Any]:
    metrics_path = EVAL_DIR / "metrics.json"
    return read_json_file(metrics_path) if metrics_path.exists() else {}


def _count_files(directory: Path, pattern: str) -> int:
    return len(list(directory.glob(pattern))) if directory.exists() else 0


def _sum_file_sizes(paths: Iterable[Path]) -> int:
    return sum(get_file_size(path) for path in paths)


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _count_optimized_pairs() -> int:
    if not OPT_IR_DIR.exists():
        return 0
    count = 0
    for path in OPT_IR_DIR.glob("*.O0.ll"):
        if (OPT_IR_DIR / path.name.replace(".O0.ll", ".O3.ll")).exists():
            count += 1
    return count


def _tool_available(tool: str) -> bool:
    search_paths = [Path(part) for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    candidates = [tool]
    if os.name == "nt" and Path(tool).suffix == "":
        pathext = [ext.strip().lower() for ext in os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(os.pathsep) if ext.strip()]
        candidates = [tool + ext for ext in pathext] or [f"{tool}.exe"]
    for directory in search_paths:
        for candidate in candidates:
            candidate_path = directory / candidate
            if candidate_path.exists() and os.access(candidate_path, os.X_OK):
                return True
    return False


def build_dashboard_snapshot() -> dict[str, Any]:
    metrics = load_metrics()
    manifest = _load_run_manifest()
    execution_rows = _load_jsonl_rows(RESULTS_DIR / "executions.jsonl")
    diff_rows = _load_jsonl_rows(RESULTS_DIR / "diffs.jsonl")
    skipped_rows = _load_jsonl_rows(RESULTS_DIR / "skipped_exec.jsonl")

    generated_files = int(manifest.get("generated", _count_files(ROOT / "generated_ir", "*.ll")) or 0)
    mutated_files = int(manifest.get("mutated", _count_files(ROOT / "mutated_ir", "*.ll")) or 0)
    valid_files = int(manifest.get("valid", _count_files(ROOT / "valid_ir", "*.ll")) or 0)
    invalid_files = int(manifest.get("invalid", _count_files(ROOT / "invalid_ir", "*.ll")) or 0)

    staging_generated = _count_files(ROOT / "generated_ir", "*.ll")
    staging_mutated = _count_files(ROOT / "mutated_ir", "*.ll")
    staging_valid = _count_files(ROOT / "valid_ir", "*.ll")
    staging_invalid = _count_files(ROOT / "invalid_ir", "*.ll")

    executed_total = len(execution_rows)
    executed_lli = sum(1 for row in execution_rows if row.get("mode") == "lli" and not row.get("skipped"))
    executed_clang = sum(1 for row in execution_rows if row.get("mode") in {"O0", "O3"} and not row.get("skipped"))
    compile_failed = sum(1 for row in execution_rows if row.get("reason") == "compile_failed")
    timeouts = sum(1 for row in execution_rows if row.get("reason") == "timeout")
    skipped_exec = len(skipped_rows)
    output_mismatches = len(diff_rows)
    optimization_artifacts = _count_files(DIFF_DIR, "*.diff")
    optimized_pairs = _count_optimized_pairs()

    execution_cases = len({row.get("name") for row in execution_rows if row.get("name")})

    total_o0_size = sum(row.get("binary_size") or 0 for row in execution_rows if row.get("mode") == "O0")
    total_o3_size = sum(row.get("binary_size") or 0 for row in execution_rows if row.get("mode") == "O3")
    comparisons = build_binary_size_comparison()
    paired_binary_cases = len(comparisons)
    binary_savings = sum(row["Savings (bytes)"] for row in comparisons)
    paired_o0_total = sum(row["O0 (bytes)"] for row in comparisons)
    binary_reduction_pct = (binary_savings / paired_o0_total * 100) if paired_o0_total else 0.0

    return {
        "generated": generated_files,
        "mutated": mutated_files,
        "valid": valid_files,
        "invalid": invalid_files,
        "executed_total": executed_total,
        "executed_lli": executed_lli,
        "executed_clang": executed_clang,
        "compile_failed": compile_failed,
        "timeouts": timeouts,
        "skipped_exec": skipped_exec,
        "output_mismatches": output_mismatches,
        "optimization_artifacts": optimization_artifacts,
        "execution_cases": execution_cases,
        "optimized_pairs": optimized_pairs,
        "staging_generated": staging_generated,
        "staging_mutated": staging_mutated,
        "staging_valid": staging_valid,
        "staging_invalid": staging_invalid,
        "total_o0_size": total_o0_size,
        "total_o3_size": total_o3_size,
        "paired_binary_cases": paired_binary_cases,
        "binary_savings": binary_savings,
        "binary_reduction_pct": binary_reduction_pct,
        "metrics_raw": metrics,
    }


def _metric_value(metrics: dict[str, Any], *keys: str, default: Any = 0) -> Any:
    for key in keys:
        if key in metrics:
            return metrics[key]
    return default


def build_binary_size_comparison() -> list[dict[str, Any]]:
    execution_rows = _load_jsonl_rows(RESULTS_DIR / "executions.jsonl")
    if not execution_rows:
        return []

    o0_sizes: dict[str, int] = {}
    o3_sizes: dict[str, int] = {}
    for row in execution_rows:
        if row.get("skipped"):
            continue
        name = row.get("name")
        mode = row.get("mode")
        binary_size = row.get("binary_size")
        if not name or binary_size is None:
            continue
        binary_size_int = int(cast(int, binary_size))
        if mode == "O0":
            o0_sizes[str(name)] = binary_size_int
        elif mode == "O3":
            o3_sizes[str(name)] = binary_size_int

    rows: list[dict[str, Any]] = []
    for name in sorted(o0_sizes.keys()):
        if name not in o3_sizes:
            continue
        o0_size = o0_sizes[name]
        o3_size = o3_sizes[name]
        savings = o0_size - o3_size
        rows.append(
            {
                "Program": name,
                "O0 (bytes)": o0_size,
                "O3 (bytes)": o3_size,
                "Savings (bytes)": savings,
                "Reduction (%)": (savings / o0_size * 100) if o0_size else 0,
                "Direction": "Smaller" if savings >= 0 else "Larger",
            }
        )

    if not rows:
        return []

    return sorted(rows, key=lambda row: (-(row["Savings (bytes)"]), row["Program"]))


# -----------------------------
# UI helpers
# -----------------------------

def inject_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg: #08111f;
                --panel: rgba(15, 23, 42, 0.76);
                --panel-border: rgba(148, 163, 184, 0.16);
                --panel-strong: rgba(15, 23, 42, 0.96);
                --text: #edf4ff;
                --muted: #94a3b8;
                --accent: #7c3aed;
                --accent-2: #0ea5e9;
                --accent-3: #22c55e;
                --warn: #f59e0b;
                --danger: #ef4444;
            }
            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(124, 58, 237, 0.18), transparent 28%),
                    radial-gradient(circle at top right, rgba(14, 165, 233, 0.12), transparent 24%),
                    linear-gradient(180deg, #07101d 0%, #0b1220 45%, #08111f 100%);
                color: var(--text);
            }
            section.main > div {
                padding-top: 1.1rem;
                max-width: 1500px;
            }
            .hero {
                border: 1px solid var(--panel-border);
                border-radius: 24px;
                padding: 1.4rem 1.5rem;
                background: linear-gradient(135deg, rgba(15,23,42,0.96), rgba(30,41,59,0.72));
                box-shadow: 0 22px 60px rgba(2, 6, 23, 0.34);
                margin-bottom: 1rem;
            }
            .hero h1 {
                margin: 0;
                color: #f8fafc;
                font-size: 2.2rem;
                line-height: 1.1;
            }
            .hero p {
                margin: 0.45rem 0 0;
                color: var(--muted);
                font-size: 0.98rem;
            }
            .pill-row {
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin-top: 0.9rem;
            }
            .pill {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                padding: 0.32rem 0.72rem;
                border-radius: 999px;
                border: 1px solid rgba(148, 163, 184, 0.18);
                background: rgba(15, 23, 42, 0.64);
                color: #cbd5e1;
                font-size: 0.84rem;
            }
            .hero-kpis {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 0.75rem;
                margin-top: 1rem;
            }
            .panel {
                border: 1px solid var(--panel-border);
                border-radius: 20px;
                background: var(--panel);
                box-shadow: 0 18px 40px rgba(2, 6, 23, 0.18);
                padding: 1rem 1.05rem;
                margin-bottom: 1rem;
            }
            .panel-title {
                font-size: 1.02rem;
                font-weight: 700;
                color: #f8fafc;
                margin-bottom: 0.35rem;
            }
            .panel-subtitle {
                color: var(--muted);
                font-size: 0.88rem;
                margin-bottom: 0.8rem;
            }
            .panel ul {
                margin: 0.4rem 0 0 1.15rem;
                color: #d9e4f4;
            }
            .panel li {
                margin-bottom: 0.35rem;
            }
            .metric-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 0.75rem;
            }
            .metric-card {
                padding: 0.95rem 1rem;
                border-radius: 18px;
                border: 1px solid rgba(148, 163, 184, 0.16);
                background: linear-gradient(180deg, rgba(15,23,42,0.95), rgba(15,23,42,0.78));
                min-height: 96px;
            }
            .metric-label {
                color: #cbd5e1;
                font-size: 0.82rem;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .metric-value {
                color: #f8fafc;
                font-size: 1.7rem;
                font-weight: 800;
                margin-top: 0.25rem;
            }
            .metric-delta {
                margin-top: 0.2rem;
                font-size: 0.82rem;
                color: #86efac;
            }
            .metric-delta.warn { color: #fbbf24; }
            .metric-delta.danger { color: #fca5a5; }
            .comparison-chip {
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
                padding: 0.2rem 0.6rem;
                border-radius: 999px;
                border: 1px solid rgba(148,163,184,0.16);
                background: rgba(15,23,42,0.7);
                color: #dbeafe;
                font-size: 0.78rem;
                margin-left: 0.4rem;
            }
            .info-card {
                border-radius: 18px;
                border: 1px solid rgba(148, 163, 184, 0.16);
                background: rgba(15, 23, 42, 0.78);
                padding: 1rem;
            }
            .section-heading {
                margin-top: 1.2rem;
                margin-bottom: 0.7rem;
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                gap: 1rem;
            }
            .section-heading h2 {
                margin: 0;
                color: #f8fafc;
                font-size: 1.25rem;
            }
            .section-heading span {
                color: var(--muted);
                font-size: 0.86rem;
            }
            .code-pane {
                border-radius: 18px;
                overflow: hidden;
                border: 1px solid rgba(148, 163, 184, 0.16);
                background: #09101c;
            }
            .code-pane-header {
                padding: 0.6rem 0.9rem;
                border-bottom: 1px solid rgba(148, 163, 184, 0.12);
                background: rgba(15, 23, 42, 0.96);
                color: #e2e8f0;
                font-weight: 700;
                font-size: 0.88rem;
            }
            .code-pane-body {
                max-height: 720px;
                overflow: auto;
                font-family: SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
                font-size: 0.86rem;
                line-height: 1.45;
            }
            .code-line {
                white-space: pre;
                padding: 0.12rem 0.85rem;
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }
            .code-equal { color: #dbeafe; }
            .code-del { background: rgba(239,68,68,0.18); color: #fecaca; }
            .code-ins { background: rgba(34,197,94,0.18); color: #bbf7d0; }
            .code-empty { color: rgba(148,163,184,0.45); }
            .sidebar-card {
                border-radius: 18px;
                border: 1px solid rgba(148, 163, 184, 0.14);
                background: rgba(15, 23, 42, 0.7);
                padding: 0.9rem;
            }
            .sidebar-card h3 {
                margin: 0 0 0.35rem;
                color: #f8fafc;
                font-size: 0.98rem;
            }
            .sidebar-card p {
                margin: 0;
                color: var(--muted);
                font-size: 0.85rem;
                line-height: 1.5;
            }
            .table-note {
                color: var(--muted);
                font-size: 0.84rem;
                margin-top: -0.25rem;
                margin-bottom: 0.8rem;
            }
            .info-strip {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.75rem;
                margin: 0.9rem 0 1rem;
            }
            .info-item {
                border: 1px solid rgba(148, 163, 184, 0.14);
                border-radius: 18px;
                background: rgba(15, 23, 42, 0.74);
                padding: 0.9rem 1rem;
            }
            .info-item h4 {
                margin: 0 0 0.25rem;
                font-size: 0.9rem;
                color: #f8fafc;
            }
            .info-item p {
                margin: 0;
                color: var(--muted);
                font-size: 0.84rem;
                line-height: 1.45;
            }
            .stMetric {
                background: rgba(15,23,42,0.38);
                border-radius: 16px;
                padding: 0.25rem 0.3rem;
                border: 1px solid rgba(148,163,184,0.08);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metric_cards(cards: Iterable[dict[str, Any]], per_row: int = 4) -> None:
    cards = list(cards)
    if not cards:
        return
    for start in range(0, len(cards), per_row):
        row = cards[start : start + per_row]
        cols = st.columns(len(row))
        for col, card in zip(cols, row):
            delta = card.get("delta")
            delta_class = "metric-delta"
            if isinstance(delta, str) and delta.startswith("-"):
                delta_class += " danger"
            elif isinstance(delta, str) and ("warn" in delta.lower() or card.get("tone") == "warn"):
                delta_class += " warn"
            with col:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-label">{html.escape(str(card['label']))}</div>
                        <div class="metric-value">{html.escape(str(card['value']))}</div>
                        {f'<div class="{delta_class}">{html.escape(str(delta))}</div>' if delta not in (None, "") else ""}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        if start + per_row < len(cards):
            st.write("")


def render_consistency_matrix(metrics: dict[str, Any]) -> None:
    matrix_rows = [
        {
            "Metric": "Generated IR",
            "Authoritative source": "evaluation/metrics.json",
            "Count": metrics.get("generated", 0),
            "Secondary view": f"generated_ir staging: {metrics.get('staging_generated', 0)}",
            "Why it matters": "Generated IR is reported from metrics.json; staging folders can be empty after cleanup.",
        },
        {
            "Metric": "Mutated IR",
            "Authoritative source": "evaluation/metrics.json",
            "Count": metrics.get("mutated", 0),
            "Secondary view": f"mutated_ir staging: {metrics.get('staging_mutated', 0)}",
            "Why it matters": "Mutations are counted before cleanup, so filesystem counts may drift.",
        },
        {
            "Metric": "Valid IR",
            "Authoritative source": "evaluation/metrics.json",
            "Count": metrics.get("valid", 0),
            "Secondary view": f"valid_ir staging: {metrics.get('staging_valid', 0)}",
            "Why it matters": "This is the stable validation result used by the rest of the dashboard.",
        },
        {
            "Metric": "Invalid IR",
            "Authoritative source": "evaluation/metrics.json",
            "Count": metrics.get("invalid", 0),
            "Secondary view": f"invalid_ir staging: {metrics.get('staging_invalid', 0)}",
            "Why it matters": "Invalid artifacts are tracked separately from validated files.",
        },
        {
            "Metric": "Execution rows",
            "Authoritative source": "results/executions.jsonl",
            "Count": metrics.get("executed_total", 0),
            "Secondary view": f"{metrics.get('execution_cases', 0)} unique test cases",
            "Why it matters": "Each test case writes lli, O0, and O3 records, so rows exceed cases.",
        },
        {
            "Metric": "Output mismatches",
            "Authoritative source": "results/diffs.jsonl",
            "Count": metrics.get("output_mismatches", 0),
            "Secondary view": f"{metrics.get('skipped_exec', 0)} skipped execution cases",
            "Why it matters": "This is the semantic mismatch count from execution comparison.",
        },
        {
            "Metric": "Optimization diff artifacts",
            "Authoritative source": "results/code_diffs/*.diff",
            "Count": metrics.get("optimization_artifacts", 0),
            "Secondary view": f"{metrics.get('optimized_pairs', 0)} O0/O3 pairs",
            "Why it matters": "These are compile-time comparison artifacts, not runtime mismatches.",
        },
        {
            "Metric": "Binary savings window",
            "Authoritative source": "results/optimized_ir/*.ll",
            "Count": format_bytes(int(metrics.get("total_o0_size", 0) or 0) - int(metrics.get("total_o3_size", 0) or 0)),
            "Secondary view": f"O0 {format_bytes(int(metrics.get('total_o0_size', 0) or 0))} / O3 {format_bytes(int(metrics.get('total_o3_size', 0) or 0))}",
            "Why it matters": "Shows aggregate optimization savings across the paired artifacts.",
        },
    ]
    st.dataframe(matrix_rows, use_container_width=True, hide_index=True)


def render_binary_size_matrix(rows: list[dict[str, Any]], *, title: str, subtitle: str) -> None:
    if not rows:
        st.info("No optimized IR artifacts are available yet. Run the pipeline first.")
        return

    total_o0 = sum(item["O0 (bytes)"] for item in rows)
    total_o3 = sum(item["O3 (bytes)"] for item in rows)
    total_savings = sum(item["Savings (bytes)"] for item in rows)
    reduction_pct = (total_savings / total_o0 * 100) if total_o0 else 0.0

    render_metric_cards(
        [
            {"label": "Programs Compared", "value": len(rows)},
            {"label": "Total O0", "value": format_bytes(total_o0)},
            {"label": "Total O3", "value": format_bytes(total_o3)},
            {"label": "Total Savings", "value": format_bytes(total_savings), "delta": f"{reduction_pct:.2f}% reduction"},
        ]
    )

    st.markdown(
        f'<div class="panel"><div class="panel-title">{html.escape(title)}</div><div class="panel-subtitle">{html.escape(subtitle)}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="table-note">Aggregate savings across the paired sample set: <strong>{format_bytes(total_savings)}</strong> ({reduction_pct:.2f}% reduction).</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    top = rows[:5]
    st.markdown(
        '<div class="panel"><div class="panel-title">Top optimizations</div><div class="panel-subtitle">Largest `-O3` size reductions in the current corpus.</div></div>',
        unsafe_allow_html=True,
    )
    st.dataframe(top, use_container_width=True, hide_index=True)


def render_summary_panel(metrics: dict[str, Any]) -> None:
    generated = int(metrics.get("generated", 0) or 0)
    mutated = int(metrics.get("mutated", 0) or 0)
    valid = int(metrics.get("valid", 0) or 0)
    invalid = int(metrics.get("invalid", 0) or 0)
    executed_total = int(metrics.get("executed_total", 0) or 0)
    execution_cases = int(metrics.get("execution_cases", 0) or 0)
    compile_failed = int(metrics.get("compile_failed", 0) or 0)
    timeouts = int(metrics.get("timeouts", 0) or 0)
    output_mismatches = int(metrics.get("output_mismatches", 0) or 0)
    optimization_artifacts = int(metrics.get("optimization_artifacts", 0) or 0)
    skipped_exec = int(metrics.get("skipped_exec", 0) or 0)

    o0_total = int(metrics.get("total_o0_size", 0) or 0)
    o3_total = int(metrics.get("total_o3_size", 0) or 0)
    total_savings = o0_total - o3_total
    savings_pct = float(metrics.get("binary_reduction_pct", (total_savings / o0_total * 100) if o0_total else 0.0) or 0.0)
    paired_binary_cases = int(metrics.get("paired_binary_cases", 0) or 0)
    binary_savings = int(metrics.get("binary_savings", total_savings) or total_savings)
    comparison_count = max(paired_binary_cases, len(build_binary_size_comparison()))

    render_metric_cards(
        [
            {"label": "Generated IR", "value": generated, "delta": f"{mutated} mutated"},
            {"label": "Validation", "value": f"{valid}/{generated}" if generated else "0/0", "delta": f"{invalid} invalid"},
            {"label": "Paired Comparisons", "value": comparison_count, "delta": f"{execution_cases} execution cases"},
            {"label": "Net Savings", "value": format_bytes(binary_savings), "delta": f"{savings_pct:.2f}% reduction"},
            {"label": "Output Mismatches", "value": output_mismatches, "delta": "results/diffs.jsonl"},
            {"label": "Diff Artifacts", "value": optimization_artifacts, "delta": "results/code_diffs/*.diff"},
            {"label": "Skipped Execs", "value": skipped_exec, "delta": f"{timeouts} timeouts"},
            {"label": "Compiler Failures", "value": compile_failed, "delta": f"{executed_total} total execution rows"},
        ]
    )

    st.caption("The canonical counts come from `evaluation/metrics.json` and `results/*.jsonl`; `generated_ir/` and `mutated_ir/` are staging areas only.")


def render_info_strip(items: list[dict[str, str]]) -> None:
    if not items:
        return
    html_rows = "".join(
        f"<div class='info-item'><h4>{html.escape(item['title'])}</h4><p>{html.escape(item['text'])}</p></div>"
        for item in items
    )
    st.markdown(f"<div class='info-strip'>{html_rows}</div>", unsafe_allow_html=True)


def render_hero(metrics: dict[str, Any]) -> None:
    comparison_count = int(metrics.get("paired_binary_cases", 0) or 0)
    reduction_pct = float(metrics.get("binary_reduction_pct", 0.0) or 0.0)
    st.markdown(
        f"""
        <div class="hero">
            <h1>LLVM IR Optimization & Validation Studio</h1>
            <p>A polished control room for curated IR generation, stable validation, paired O0/O3 analysis, and visible optimization savings.</p>
            <div class="pill-row">
                <span class="pill">✨ Stable metrics from `evaluation/metrics.json`</span>
                <span class="pill">🧪 Output mismatches stay separate from optimization diffs</span>
                <span class="pill">⚙️ `results/code_diffs/` tracks comparison artifacts</span>
                <span class="pill">📈 `generated_ir/` and `mutated_ir/` are staging only</span>
            </div>
            <div class="hero-kpis">
                <div class="metric-card"><div class="metric-label">Paired Comparisons</div><div class="metric-value">{comparison_count}</div></div>
                <div class="metric-card"><div class="metric-label">Net Reduction</div><div class="metric-value">{reduction_pct:.2f}%</div></div>
                <div class="metric-card"><div class="metric-label">Optimized Pairs</div><div class="metric-value">{int(metrics.get('optimized_pairs', 0) or 0)}</div></div>
                <div class="metric-card"><div class="metric-label">Skipped Execs</div><div class="metric-value">{int(metrics.get('skipped_exec', 0) or 0)}</div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_side_by_side_ir(o0_text: str, o3_text: str) -> None:
    o0_lines = o0_text.splitlines()
    o3_lines = o3_text.splitlines()
    matcher = difflib.SequenceMatcher(a=o0_lines, b=o3_lines)

    left_rows: list[str] = []
    right_rows: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for left, right in zip(o0_lines[i1:i2], o3_lines[j1:j2]):
                esc_left = html.escape(left)
                esc_right = html.escape(right)
                left_rows.append(f'<div class="code-line code-equal">{esc_left}</div>')
                right_rows.append(f'<div class="code-line code-equal">{esc_right}</div>')
        elif tag == "replace":
            left_chunk = o0_lines[i1:i2]
            right_chunk = o3_lines[j1:j2]
            max_len = max(len(left_chunk), len(right_chunk))
            for idx in range(max_len):
                left = html.escape(left_chunk[idx]) if idx < len(left_chunk) else ""
                right = html.escape(right_chunk[idx]) if idx < len(right_chunk) else ""
                left_rows.append(f'<div class="code-line code-del">{left or "&nbsp;"}</div>')
                right_rows.append(f'<div class="code-line code-ins">{right or "&nbsp;"}</div>')
        elif tag == "delete":
            for left in o0_lines[i1:i2]:
                left_rows.append(f'<div class="code-line code-del">{html.escape(left)}</div>')
                right_rows.append('<div class="code-line code-empty">&nbsp;</div>')
        elif tag == "insert":
            for right in o3_lines[j1:j2]:
                left_rows.append('<div class="code-line code-empty">&nbsp;</div>')
                right_rows.append(f'<div class="code-line code-ins">{html.escape(right)}</div>')

    left_html = "".join(left_rows) or '<div class="code-line code-empty">&nbsp;</div>'
    right_html = "".join(right_rows) or '<div class="code-line code-empty">&nbsp;</div>'

    st.markdown(
        f"""
        <div class="panel">
            <div class="section-heading">
                <h2>Side-by-side IR Comparison</h2>
                <span>Highlighted differences between -O0 and -O3</span>
            </div>
            <div class="metric-grid" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
                <div class="code-pane">
                    <div class="code-pane-header">-O0 LLVM IR</div>
                    <div class="code-pane-body">{left_html}</div>
                </div>
                <div class="code-pane">
                    <div class="code-pane-header">-O3 LLVM IR</div>
                    <div class="code-pane-body">{right_html}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# Page sections
# -----------------------------

def render_overview(metrics: dict[str, Any]) -> None:
    render_hero(metrics)
    render_info_strip(
        [
            {"title": "Value demonstrated", "text": "Shows real optimization savings with paired -O0/-O3 comparisons and consistent source-of-truth metrics."},
            {"title": "Quality gate", "text": "Separates valid, invalid, skipped, and mismatched outcomes so the demo reads like a production workflow."},
            {"title": "Evidence trail", "text": "Surfaces summary markdown, binary pairs, and logs in one place for quick stakeholder review."},
        ]
    )

    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        st.markdown(
            """
            <div class="panel">
                <div class="panel-title">What this system does</div>
                <div class="panel-subtitle">A curated LLVM pipeline that generates comparable workloads, validates them, and reports clear optimization value.</div>
                <ul>
                    <li>Generates LLVM IR using a curated catalog of optimization-focused templates or an LLM backend.</li>
                    <li>Validates SSA form and records invalid artifacts separately for traceability.</li>
                    <li>Runs differential execution with LLVM tools when available.</li>
                    <li>Tracks binary savings, diffs, and toolchain health in one consistent view.</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="panel">
                <div class="panel-title">Current pipeline health</div>
                <div class="panel-subtitle">Quick read on the latest generated artifacts, validation results, and comparison quality.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_summary_panel(metrics)

    with right:
        st.markdown(
            """
            <div class="panel">
                <div class="panel-title">Environment snapshot</div>
                <div class="panel-subtitle">Useful runtime and toolchain checks for a repeatable demo.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        required_tools = ["llvm-as", "opt", "lli", "clang"]
        missing_tools = [tool for tool in required_tools if not _tool_available(tool)]
        cols = st.columns(2)
        cols[0].metric("LLVM tools present", len(required_tools) - len(missing_tools), f"/{len(required_tools)} required")
        cols[1].metric("Missing tools", len(missing_tools), ", ".join(missing_tools) if missing_tools else "none")

        if (EVAL_DIR / "metrics.png").exists():
            st.image(str(EVAL_DIR / "metrics.png"), caption="Optimization metrics overview", use_container_width=True)
        else:
            st.info("No metrics plot available yet. Run the pipeline to generate `evaluation/metrics.png`.")


def render_metrics_page(metrics: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <h2>Metrics & Summary</h2>
            <span>Stable counts, source-of-truth matrix, and optimization outcomes</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_consistency_matrix(metrics)
    st.write("")
    render_summary_panel(metrics)
    render_info_strip(
        [
            {"title": "Executive view", "text": "Highlights the headline numbers first so the audience immediately sees what improved."},
            {"title": "Source of truth", "text": "Keeps the stable metrics separate from staging folders and intermediate artifacts."},
            {"title": "Optimization proof", "text": "Reinforces savings with paired binary comparisons, not just raw execution counts."},
        ]
    )


    col1, col2 = st.columns([1.15, 0.85], gap="large")
    with col1:
        st.markdown('<div class="panel"><div class="panel-title">Pipeline summary</div><div class="panel-subtitle">Rendered from `results/summary.md` with executive-friendly comparison framing.</div></div>', unsafe_allow_html=True)
        summary_path = RESULTS_DIR / "summary.md"
        if summary_path.exists():
            summary_text = read_text_file(summary_path)
            summary_text = remove_markdown_section(
                summary_text,
                "## Paired Binary Size Comparisons (-O0 vs -O3)",
            )
            st.markdown(summary_text)
        else:
            st.info("No summary report found yet. Run the pipeline first.")

    with col2:
        st.markdown('<div class="panel"><div class="panel-title">Metrics chart</div><div class="panel-subtitle">Rendered from `evaluation/metrics.png` with a cleaner executive snapshot.</div></div>', unsafe_allow_html=True)
        metrics_png = EVAL_DIR / "metrics.png"
        if metrics_png.exists():
            st.image(str(metrics_png), use_container_width=True)
        else:
            st.info("No metrics chart found.")

        with st.expander("Raw metrics CSV", expanded=False):
            metrics_csv = EVAL_DIR / "metrics.csv"
            if metrics_csv.exists():
                st.markdown(f"**Size:** `{format_bytes(get_file_size(metrics_csv))}`")
                try:
                    with metrics_csv.open(newline="", encoding="utf-8") as handle:
                        reader = csv.DictReader(handle)
                        st.dataframe(list(reader), use_container_width=True, hide_index=True)
                except Exception:
                    st.info("metrics.csv exists but could not be loaded.")
            else:
                st.info("metrics.csv not found.")


def render_artifacts_page(metrics: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <h2>Optimization Artifacts</h2>
            <span>Paired `-O0` / `-O3` comparisons and textual diff artifacts</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_summary_panel(metrics)

    render_binary_size_matrix(
        build_binary_size_comparison(),
        title="Paired Binary Size Comparisons (-O0 vs -O3)",
        subtitle="This table comes from paired `results/optimized_ir/*.O0.ll` and `results/optimized_ir/*.O3.ll` files.",
    )

    if (RESULTS_DIR / "summary.md").exists():
        with st.expander("Project summary markdown", expanded=False):
            st.markdown(read_text_file(RESULTS_DIR / "summary.md"))


def render_logs_page(metrics: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <h2>Logs & Executions</h2>
            <span>Triage output, execution traces, and system logs</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_summary_panel(metrics)

    triage_path = RESULTS_DIR / "triage.json"
    executions_path = RESULTS_DIR / "executions.jsonl"

    top_cols = st.columns(2)
    with top_cols[0]:
        st.markdown('<div class="panel"><div class="panel-title">Triage results</div><div class="panel-subtitle">Structured findings from differential analysis.</div></div>', unsafe_allow_html=True)
        if triage_path.exists():
            st.markdown(f"**Size:** `{format_bytes(get_file_size(triage_path))}`")
            try:
                st.json(read_json_file(triage_path))
            except Exception:
                st.error("Failed to parse triage.json.")
        else:
            st.info("No triage data found yet.")

    with top_cols[1]:
        st.markdown('<div class="panel"><div class="panel-title">Automated executions</div><div class="panel-subtitle">JSONL execution records from the pipeline.</div></div>', unsafe_allow_html=True)
        if executions_path.exists():
            st.markdown(f"**Size:** `{format_bytes(get_file_size(executions_path))}`")
            df_exec = read_jsonl_file(executions_path)
            if df_exec:
                st.dataframe(df_exec, use_container_width=True, hide_index=True)
            else:
                st.info("No execution rows found.")
        else:
            st.info("No execution data found yet.")

    st.markdown('<div class="panel"><div class="panel-title">System execution logs</div><div class="panel-subtitle">Select a `.log`, `.out`, or `.err` file to inspect.</div></div>', unsafe_allow_html=True)
    if not LOGS_DIR.exists():
        st.info("Logs directory not found.")
        return

    log_files = sorted([p for p in LOGS_DIR.iterdir() if p.suffix in {".log", ".out", ".err"}])
    if not log_files:
        st.info("No logs found.")
        return

    options = [f"{p.name} ({format_bytes(get_file_size(p))})" for p in log_files]
    selected = st.selectbox("Select log file", options)
    selected_name = selected.split(" (")[0]
    selected_path = LOGS_DIR / selected_name
    content = read_text_file(selected_path)

    st.markdown(f"**📄 {selected_name}** • **Size:** `{format_bytes(get_file_size(selected_path))}`")
    if len(content) > 50000:
        st.warning("Large log file detected. Showing the last 50 KB only.")
        content = content[-50000:]
    st.code(content or "(empty file)", language="text")


def render_diff_page(metrics: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="section-heading">
            <h2>Optimization Diff Viewer</h2>
            <span>Unified diff plus side-by-side IR viewer for compile-time optimization artifacts</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_summary_panel(metrics)

    if not DIFF_DIR.exists():
        st.info("Comparison directory not found. Run the pipeline first.")
        return

    diff_files = sorted(DIFF_DIR.glob("*.diff"))
    if not diff_files:
        st.info("No diff artifacts found yet.")
        return

    options = [f"{p.name} ({format_bytes(get_file_size(p))})" for p in diff_files]
    selected = st.selectbox("Select comparison view", options, index=0)

    selected_name = selected.split(" (")[0]
    base_name = selected_name[:-5]
    o0_path = OPT_IR_DIR / f"{base_name}.O0.ll"
    o3_path = OPT_IR_DIR / f"{base_name}.O3.ll"
    diff_path = DIFF_DIR / selected_name

    if not o0_path.exists() or not o3_path.exists():
        st.info("One or both optimized IR artifacts are missing.")
        return

    o0_size = get_file_size(o0_path)
    o3_size = get_file_size(o3_path)
    savings = o0_size - o3_size
    reduction = (savings / o0_size * 100) if o0_size else 0
    direction = "smaller" if savings >= 0 else "larger"

    render_metric_cards(
        [
            {"label": "O0 Size", "value": format_bytes(o0_size)},
            {"label": "O3 Size", "value": format_bytes(o3_size)},
            {"label": "Change", "value": format_bytes(abs(savings)), "delta": "Smaller" if savings >= 0 else "Larger"},
            {"label": "Reduction", "value": f"{reduction:.2f}%"},
        ]
    )

    st.markdown(
        f'<div class="panel"><div class="panel-title">Selected comparison</div><div class="panel-subtitle">`{html.escape(base_name)}` is {direction} under `-O3` by <strong>{format_bytes(abs(savings))}</strong> ({abs(reduction):.2f}%).</div></div>',
        unsafe_allow_html=True,
    )

    if savings >= 0:
        st.success(f"-O3 saved {format_bytes(savings)} ({reduction:.2f}%).")
    else:
        st.warning(f"-O3 expanded the IR by {format_bytes(abs(savings))} ({abs(reduction):.2f}%).")

    render_side_by_side_ir(read_text_file(o0_path), read_text_file(o3_path))

    st.markdown('<div class="panel"><div class="panel-title">Unified diff</div><div class="panel-subtitle">Raw optimization comparison artifact for the selected program.</div></div>', unsafe_allow_html=True)
    if diff_path.exists():
        st.markdown(f"**Size:** `{format_bytes(get_file_size(diff_path))}`")
        st.code(read_text_file(diff_path), language="diff")
    else:
        st.info("Diff artifact not found.")

    with st.expander("All files summary", expanded=False):
        all_df = build_all_ir_comparisons()
        if all_df is None or not all_df:
            st.info("No compiled binaries available yet.")
        else:
            avg_reduction = (sum(row["Reduction (%)"] for row in all_df) / len(all_df)) if all_df else 0.0
            render_metric_cards(
                [
                    {"label": "Total Files", "value": len(all_df)},
                    {"label": "Optimized Smaller", "value": sum(1 for row in all_df if row["Savings (bytes)"] >= 0)},
                    {"label": "Expanded Larger", "value": sum(1 for row in all_df if row["Savings (bytes)"] < 0)},
                    {"label": "Avg Reduction", "value": f"{avg_reduction:.2f}%"},
                ]
            )
            st.dataframe(all_df, use_container_width=True, hide_index=True)


def build_all_ir_comparisons() -> list[dict[str, Any]]:
    return build_binary_size_comparison()


def _combined_execution_count(metrics: dict[str, Any]) -> int:
    return int(metrics.get("executed_total", 0) or 0)


# -----------------------------
# Main app
# -----------------------------

def run_dashboard() -> None:
    if st is None:
        raise RuntimeError("streamlit is required to run the dashboard")

    st.set_page_config(
        page_title="LLVM IR Differential Testing Studio",
        page_icon="⚙️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_styles()
    # Auto-generate a varied sample set on first dashboard load to ensure
    # the O0/O3 comparisons show gradual deltas. A marker file prevents
    # re-running on every reload.
    marker = ROOT / "results" / ".varied_generated"
    try:
        if not marker.exists():
            cmd = [sys.executable, str(ROOT / "scripts" / "generate_varied_binary_sizes.py"), "--seed", "1337", "--count", "10"]
            subprocess.run(cmd, check=True)
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("done")
            except Exception:
                pass
    except Exception as exc:  # don't break the dashboard if generation fails
        try:
            st.warning(f"Auto-generation failed: {exc}")
        except Exception:
            pass

    metrics = build_dashboard_snapshot()

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-card">
                <h3>LLVM IR Studio</h3>
                <p>A focused dashboard for generation, validation, execution, and optimization analysis.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Navigation")
        page = st.radio(
            "",
            ["Overview", "Optimization Artifacts", "Optimization Diff Viewer", "Logs"],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("Workspace hints")
        st.write(f"• Generated IR: `{(ROOT / 'generated_ir').as_posix()}`")
        st.write(f"• Logs: `{LOGS_DIR.as_posix()}`")
        st.write(f"• Comparisons: `{DIFF_DIR.as_posix()}`")

    if page == "Overview":
        render_overview(metrics)
    elif page == "Optimization Artifacts":
        render_artifacts_page(metrics)
    elif page == "Optimization Diff Viewer":
        render_diff_page(metrics)
    else:
        render_logs_page(metrics)


if __name__ == "__main__":
    run_dashboard()

