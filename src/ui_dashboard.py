"""
ui_dashboard.py — Streamlit dashboard for the LLVM IR Differential Testing pipeline.

All file paths and directory names are resolved through ``cfg`` (config.yaml) so
nothing is hardcoded here.  The dashboard is split into four pages:

  Overview            — hero KPIs, toolchain health, metrics chart
  Optimization Artifacts — paired O0/O3 binary-size table
  Diff Viewer         — side-by-side IR comparison + unified diff
  Logs                — execution records, triage JSON, raw log files
"""
from __future__ import annotations

import csv
import difflib
import html
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover
    st = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Project root and path resolution via cfg
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

# Import cfg lazily so the module can be imported without a PYTHONPATH change.
sys.path.insert(0, str(ROOT))
from src.config import cfg, ProjectPaths

_PATHS = ProjectPaths.from_config(cfg, ROOT)
_FILES = cfg.reporting.files

RESULTS_DIR  = _PATHS.results_dir
EVAL_DIR     = _PATHS.evaluation_dir
LOGS_DIR     = _PATHS.logs_dir
OPT_IR_DIR   = _PATHS.optimized_dir
DIFF_DIR     = _PATHS.diffs_dir


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _fmt_bytes(n: int | float | None) -> str:
    if n is None:
        return "0 B"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size) < 1024.0:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(_read_text(path))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except json.JSONDecodeError:
            pass
    return rows


def _count_glob(directory: Path, pattern: str) -> int:
    return len(list(directory.glob(pattern))) if directory.exists() else 0


def _tool_ok(name: str) -> bool:
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Dashboard data snapshot
# ---------------------------------------------------------------------------

def _load_snapshot() -> dict[str, Any]:
    """Aggregate all pipeline artefacts into one flat dict for the UI."""
    manifest   = _read_json(RESULTS_DIR / _FILES["run_manifest"])
    metrics    = _read_json(EVAL_DIR    / _FILES["metrics_json"])
    exec_rows  = _read_jsonl(RESULTS_DIR / _FILES["executions"])
    diff_rows  = _read_jsonl(RESULTS_DIR / _FILES["diffs"])
    skip_rows  = _read_jsonl(RESULTS_DIR / _FILES["skipped"])

    # Prefer manifest counts; fall back to counting files on disk
    def _manifest_int(key: str, fallback_dir: Path) -> int:
        v = manifest.get("counts", {}).get(key) or manifest.get(key)
        return int(v) if isinstance(v, (int, float)) else _count_glob(fallback_dir, "*.ll")

    generated = _manifest_int("generated", _PATHS.generated_dir)
    mutated   = _manifest_int("mutated",   _PATHS.mutated_dir)
    valid     = _manifest_int("valid",     _PATHS.valid_dir)
    invalid   = _manifest_int("invalid",   _PATHS.invalid_dir)

    # Binary-size comparisons from execution log
    o0: dict[str, int] = {}
    o3: dict[str, int] = {}
    # Instruction count aggregates
    o0_instr_list: list[int]   = []
    o3_instr_list: list[int]   = []
    instr_pct_list: list[float] = []

    for row in exec_rows:
        name = row.get("name")
        size = row.get("binary_size")
        if name and isinstance(size, (int, float)):
            if row.get("mode") == "O0":
                o0[str(name)] = int(size)
            elif row.get("mode") == "O3":
                o3[str(name)] = int(size)
        # Instruction counts are stored on O0 records
        if row.get("mode") == "O0":
            ic0 = row.get("o0_instr_count")
            ic3 = row.get("o3_instr_count")
            pct = row.get("instr_reduction_pct")
            if isinstance(ic0, (int, float)) and isinstance(ic3, (int, float)):
                o0_instr_list.append(int(ic0))
                o3_instr_list.append(int(ic3))
            if isinstance(pct, (int, float)):
                instr_pct_list.append(float(pct))

    paired        = sorted(set(o0) & set(o3))
    binary_savings= sum(o0[n] - o3[n] for n in paired)
    total_o0      = sum(o0[n] for n in paired)
    reduction_pct = (binary_savings / total_o0 * 100) if total_o0 else 0.0

    run_meta: dict[str, str] = {}
    for k in ("generated_at", "backend", "model", "mode", "scope",
              "gen_count", "mut_per_file", "seed_dir", "test_file"):
        v = manifest.get(k)
        if v is not None:
            run_meta[k] = str(v)

    # Per-strategy diff rates from metrics.json
    strategy_diff_rates: dict[str, float] = {}
    raw_rates = metrics.get("strategy_diff_rates")
    if isinstance(raw_rates, dict):
        strategy_diff_rates = {k: float(v) for k, v in raw_rates.items()
                               if isinstance(v, (int, float))}

    return {
        # Counts
        "generated": generated, "mutated": mutated,
        "valid": valid, "invalid": invalid,
        # Execution
        "executed_total":  len(exec_rows),
        "executed_lli":    sum(1 for r in exec_rows if r.get("mode") == "lli" and not r.get("skipped")),
        "executed_clang":  sum(1 for r in exec_rows if r.get("mode") in ("O0", "O3") and not r.get("skipped")),
        "compile_failed":  sum(1 for r in exec_rows if r.get("reason") == "compile_failed"),
        "timeouts":        sum(1 for r in exec_rows if r.get("reason") == "timeout"),
        "output_mismatches": len(diff_rows),
        "skipped_exec":    len(skip_rows),
        "diff_artifacts":  _count_glob(DIFF_DIR, "*.diff"),
        "optimized_pairs": sum(
            1 for p in OPT_IR_DIR.glob("*.O0.ll")
            if (OPT_IR_DIR / p.name.replace(".O0.ll", ".O3.ll")).exists()
        ) if OPT_IR_DIR.exists() else 0,
        # Binary sizes
        "total_o0_size":       sum(o0.values()),
        "total_o3_size":       sum(o3.values()),
        "paired_binary_cases": len(paired),
        "binary_savings":      binary_savings,
        "binary_reduction_pct": reduction_pct,
        # Instruction counts
        "total_o0_instructions":   sum(o0_instr_list),
        "total_o3_instructions":   sum(o3_instr_list),
        "total_instr_eliminated":  sum(o0_instr_list) - sum(o3_instr_list),
        "avg_instr_reduction_pct": round(sum(instr_pct_list) / len(instr_pct_list), 2) if instr_pct_list else 0.0,
        "files_with_instr_data":   len(o0_instr_list),
        # Strategy rates
        "strategy_diff_rates": strategy_diff_rates,
        # Metadata
        "run_metadata":  run_meta,
        "metrics_raw":   metrics,
    }


def _build_size_table() -> list[dict[str, Any]]:
    """Return a list of dicts suitable for st.dataframe, sorted by savings desc."""
    exec_rows = _read_jsonl(RESULTS_DIR / _FILES["executions"])
    o0: dict[str, int] = {}
    o3: dict[str, int] = {}
    for row in exec_rows:
        name = row.get("name")
        size = row.get("binary_size")
        if name and isinstance(size, (int, float)):
            if row.get("mode") == "O0":
                o0[str(name)] = int(size)
            elif row.get("mode") == "O3":
                o3[str(name)] = int(size)
    rows = []
    for name in sorted(o0):
        if name not in o3:
            continue
        savings = o0[name] - o3[name]
        rows.append({
            "Program":        name,
            "O0 (bytes)":     o0[name],
            "O3 (bytes)":     o3[name],
            "Savings (bytes)":savings,
            "Reduction (%)":  round((savings / o0[name] * 100) if o0[name] else 0.0, 2),
            "Direction":      "smaller" if savings >= 0 else "larger",
        })
    return sorted(rows, key=lambda r: -r["Savings (bytes)"])


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_CSS = """
<style>
:root {
    --bg: #08111f;
    --panel: rgba(15,23,42,0.76);
    --border: rgba(148,163,184,0.16);
    --text: #edf4ff;
    --muted: #94a3b8;
    --accent: #7c3aed;
    --green: #22c55e;
    --red: #ef4444;
    --blue: #0ea5e9;
    --amber: #f59e0b;
}
.stApp {
    background:
        radial-gradient(circle at top left, rgba(124,58,237,0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(14,165,233,0.12), transparent 24%),
        linear-gradient(180deg, #07101d 0%, #0b1220 45%, #08111f 100%);
    color: var(--text);
}
section.main > div { padding-top: 1.1rem; max-width: 1500px; }

/* Hero */
.hero { border:1px solid var(--border); border-radius:24px; padding:1.4rem 1.5rem;
        background:linear-gradient(135deg,rgba(15,23,42,.96),rgba(30,41,59,.72));
        box-shadow:0 22px 60px rgba(2,6,23,.34); margin-bottom:1rem; }
.hero h1 { margin:0; color:#f8fafc; font-size:2.1rem; }
.hero p  { margin:.4rem 0 0; color:var(--muted); font-size:.97rem; }
.pill-row { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:.9rem; }
.pill { display:inline-flex; align-items:center; gap:.4rem; padding:.3rem .7rem;
        border-radius:999px; border:1px solid var(--border);
        background:rgba(15,23,42,.64); color:#cbd5e1; font-size:.83rem; }

/* Metric cards */
.mc-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.75rem; }
.mc { padding:.9rem 1rem; border-radius:18px; border:1px solid var(--border);
      background:linear-gradient(180deg,rgba(15,23,42,.95),rgba(15,23,42,.78));
      min-height:88px; }
.mc-label { color:#cbd5e1; font-size:.8rem; letter-spacing:.04em; text-transform:uppercase; }
.mc-value { color:#f8fafc; font-size:1.65rem; font-weight:800; margin-top:.2rem; }
.mc-delta { margin-top:.18rem; font-size:.8rem; }
.mc-delta.ok   { color:#86efac; }
.mc-delta.warn { color:#fbbf24; }
.mc-delta.bad  { color:#fca5a5; }

/* Panels */
.panel { border:1px solid var(--border); border-radius:20px; background:var(--panel);
         box-shadow:0 18px 40px rgba(2,6,23,.18); padding:1rem 1.05rem; margin-bottom:1rem; }
.panel-title    { font-size:1rem; font-weight:700; color:#f8fafc; margin-bottom:.3rem; }
.panel-subtitle { color:var(--muted); font-size:.87rem; margin-bottom:.75rem; }

/* Code panes */
.code-pane { border-radius:18px; overflow:hidden; border:1px solid var(--border); background:#09101c; }
.code-pane-header { padding:.55rem .9rem; border-bottom:1px solid rgba(148,163,184,.12);
                    background:rgba(15,23,42,.96); color:#e2e8f0; font-weight:700; font-size:.87rem; }
.code-pane-body { max-height:680px; overflow:auto; font-family:SFMono-Regular,Consolas,monospace;
                  font-size:.85rem; line-height:1.45; }
.cl  { white-space:pre; padding:.1rem .8rem; border-bottom:1px solid rgba(255,255,255,.04); }
.cl-eq  { color:#dbeafe; }
.cl-del { background:rgba(239,68,68,.18); color:#fecaca; }
.cl-ins { background:rgba(34,197,94,.18);  color:#bbf7d0; }
.cl-mt  { color:rgba(148,163,184,.4); }
</style>
"""


def _inject_styles() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Metric card grid
# ---------------------------------------------------------------------------

def _metric_cards(cards: list[dict[str, Any]], per_row: int = 4) -> None:
    """Render a row of metric cards using custom HTML."""
    for start in range(0, len(cards), per_row):
        row   = cards[start: start + per_row]
        cols  = st.columns(len(row))
        for col, c in zip(cols, row):
            tone  = c.get("tone", "ok")
            delta = c.get("delta", "")
            delta_html = (
                f'<div class="mc-delta {tone}">{html.escape(str(delta))}</div>'
                if delta not in (None, "") else ""
            )
            with col:
                st.markdown(
                    f'<div class="mc">'
                    f'<div class="mc-label">{html.escape(str(c["label"]))}</div>'
                    f'<div class="mc-value">{html.escape(str(c["value"]))}</div>'
                    f'{delta_html}</div>',
                    unsafe_allow_html=True,
                )
        if start + per_row < len(cards):
            st.write("")


# ---------------------------------------------------------------------------
# Side-by-side IR diff renderer
# ---------------------------------------------------------------------------

def _render_side_by_side(o0_text: str, o3_text: str) -> None:
    o0_lines = o0_text.splitlines()
    o3_lines = o3_text.splitlines()
    matcher  = difflib.SequenceMatcher(a=o0_lines, b=o3_lines, autojunk=False)

    left: list[str]  = []
    right: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for a, b in zip(o0_lines[i1:i2], o3_lines[j1:j2]):
                left.append(f'<div class="cl cl-eq">{html.escape(a)}</div>')
                right.append(f'<div class="cl cl-eq">{html.escape(b)}</div>')
        elif tag == "replace":
            lc, rc = o0_lines[i1:i2], o3_lines[j1:j2]
            for i in range(max(len(lc), len(rc))):
                l = html.escape(lc[i]) if i < len(lc) else "&nbsp;"
                r = html.escape(rc[i]) if i < len(rc) else "&nbsp;"
                left.append(f'<div class="cl cl-del">{l}</div>')
                right.append(f'<div class="cl cl-ins">{r}</div>')
        elif tag == "delete":
            for a in o0_lines[i1:i2]:
                left.append(f'<div class="cl cl-del">{html.escape(a)}</div>')
                right.append('<div class="cl cl-mt">&nbsp;</div>')
        elif tag == "insert":
            for b in o3_lines[j1:j2]:
                left.append('<div class="cl cl-mt">&nbsp;</div>')
                right.append(f'<div class="cl cl-ins">{html.escape(b)}</div>')

    lh = "".join(left)  or '<div class="cl cl-mt">&nbsp;</div>'
    rh = "".join(right) or '<div class="cl cl-mt">&nbsp;</div>'

    st.markdown(
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem;">'
        f'<div class="code-pane"><div class="code-pane-header">-O0 LLVM IR</div>'
        f'<div class="code-pane-body">{lh}</div></div>'
        f'<div class="code-pane"><div class="code-pane-header">-O3 LLVM IR</div>'
        f'<div class="code-pane-body">{rh}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Page: Overview
# ---------------------------------------------------------------------------

def _page_overview(snap: dict[str, Any]) -> None:
    reduction = snap["binary_reduction_pct"]
    st.markdown(
        f'<div class="hero"><h1>⚙️ LLVM IR Differential Testing Studio</h1>'
        f'<p>IR generation → mutation → validation → O0/O3 differential execution → binary-size analysis.</p>'
        f'<div class="pill-row">'
        f'<span class="pill">📐 config.yaml is the single source of truth</span>'
        f'<span class="pill">🧪 O0/O3 binary-size comparison</span>'
        f'<span class="pill">🔍 Unified diff + side-by-side IR viewer</span>'
        f'<span class="pill">📊 Metrics PNG + CSV + JSON</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    _metric_cards([
        {"label": "Generated",        "value": snap["generated"],          "delta": f"{snap['mutated']} mutated"},
        {"label": "Valid / Invalid",   "value": f"{snap['valid']} / {snap['invalid']}"},
        {"label": "Paired Comparisons","value": snap["paired_binary_cases"],"delta": f"{snap['executed_total']} exec rows"},
        {"label": "Net Savings",       "value": _fmt_bytes(snap["binary_savings"]), "delta": f"{reduction:.2f}% reduction"},
        {"label": "Output Mismatches", "value": snap["output_mismatches"],  "tone": "bad" if snap["output_mismatches"] else "ok",
         "delta": _FILES["diffs"]},
        {"label": "Diff Artifacts",    "value": snap["diff_artifacts"],    "delta": "code_diffs/*.diff"},
        {"label": "Skipped Execs",     "value": snap["skipped_exec"],      "tone": "warn" if snap["skipped_exec"] else "ok",
         "delta": f"{snap['timeouts']} timeouts"},
        {"label": "Compile Failures",  "value": snap["compile_failed"],    "tone": "bad" if snap["compile_failed"] else "ok"},
    ])

    left, right = st.columns([1.2, 0.8], gap="large")
    with left:
        st.markdown(
            '<div class="panel"><div class="panel-title">Pipeline stages</div>'
            '<div class="panel-subtitle">Each stage feeds the next; all paths and tool names come from config.yaml.</div>'
            '<ul style="color:#d9e4f4;margin:.4rem 0 0 1.1rem;">'
            '<li><b>IR Generation</b> — template-based or LLM-backed (openai)</li>'
            '<li><b>Mutation</b> — opcode swap, dead code, CFG splits, loops, calls, vectors</li>'
            '<li><b>Validation</b> — llvm-as + opt verify, or regex fallback</li>'
            '<li><b>Execution</b> — lli (interpret) + clang -O0 / -O3 (compile + run)</li>'
            '<li><b>Analysis</b> — binary-size diff, textual IR diff, instruction count diff</li>'
            '<li><b>Feedback loop</b> — diff-producing files become seeds for next run</li>'
            '</ul></div>',
            unsafe_allow_html=True,
        )
        png_path = EVAL_DIR / _FILES["metrics_png"]
        if png_path.exists():
            st.image(str(png_path), caption="Pipeline snapshot", use_container_width=True)
        else:
            st.info("Run the pipeline to generate evaluation/metrics.png.")

    with right:
        required = [cfg.execution.interpreter, cfg.execution.compiler, cfg.execution.optimizer,
                    cfg.validation.assembler_tool]
        missing  = [t for t in required if not _tool_ok(t)]
        c1, c2 = st.columns(2)
        c1.metric("Tools present", len(required) - len(missing), f"/{len(required)}")
        c2.metric("Missing",       len(missing), ", ".join(missing) or "none")

        meta = snap.get("run_metadata", {})
        if meta:
            st.markdown('<div class="panel"><div class="panel-title">Last run</div></div>',
                        unsafe_allow_html=True)
            for k in ("generated_at", "backend", "model", "mode", "gen_count", "mut_per_file"):
                if k in meta:
                    st.write(f"• **{k}**: `{meta[k]}`")

    # ── Instruction-count stats ────────────────────────────────────────────
    if snap.get("files_with_instr_data", 0) > 0:
        st.markdown("### Instruction-Count Reduction (O0 → O3)")
        _metric_cards([
            {"label": "O0 Instructions",  "value": f"{snap['total_o0_instructions']:,}"},
            {"label": "O3 Instructions",  "value": f"{snap['total_o3_instructions']:,}"},
            {"label": "Eliminated",       "value": f"{snap['total_instr_eliminated']:,}",
             "tone": "ok" if snap["total_instr_eliminated"] > 0 else "warn"},
            {"label": "Avg Reduction",    "value": f"{snap['avg_instr_reduction_pct']:.1f}%",
             "delta": f"across {snap['files_with_instr_data']} files"},
        ])

    # ── Per-strategy diff rate chart ───────────────────────────────────────
    rates = snap.get("strategy_diff_rates", {})
    if rates:
        st.markdown("### Strategy Diff Rates")
        st.caption("How often each mutation strategy produced a behavioural diff (O0 ≠ O3 output)")
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import io

            strategies = sorted(rates, key=lambda k: -rates[k])
            values     = [rates[s] for s in strategies]
            colors     = ["#ef4444" if v > 10 else "#f59e0b" if v > 0 else "#94a3b8" for v in values]

            fig, ax = plt.subplots(figsize=(10, max(3, len(strategies) * 0.5)),
                                   facecolor="#09101c")
            ax.set_facecolor("#09101c")
            bars = ax.barh(strategies, values, color=colors)
            ax.set_xlabel("Diff Rate (%)", color="#cbd5e1")
            ax.tick_params(colors="#cbd5e1")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            for spine in ("left", "bottom"):
                ax.spines[spine].set_color("#334155")
            ax.xaxis.label.set_color("#cbd5e1")
            for bar, val in zip(bars, values):
                ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                        f"{val:.1f}%", va="center", color="#e2e8f0", fontsize=9)
            fig.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
            plt.close(fig)
            buf.seek(0)
            st.image(buf, use_container_width=True)
        except Exception:
            # Fallback: plain table
            st.dataframe(
                [{"Strategy": k, "Diff Rate (%)": v} for k, v in
                 sorted(rates.items(), key=lambda kv: -kv[1])],
                use_container_width=True,
                hide_index=True,
            )


# ---------------------------------------------------------------------------
# Page: Optimization Artifacts
# ---------------------------------------------------------------------------

def _page_artifacts(snap: dict[str, Any]) -> None:
    st.markdown("## Optimization Artifacts")
    st.caption("Paired -O0 / -O3 binary-size comparisons from results/executions.jsonl")

    rows = _build_size_table()
    if not rows:
        st.info("No paired results yet. Run the pipeline first.")
        return

    total_o0 = sum(r["O0 (bytes)"] for r in rows)
    total_o3 = sum(r["O3 (bytes)"] for r in rows)
    savings  = total_o0 - total_o3
    pct      = (savings / total_o0 * 100) if total_o0 else 0.0

    _metric_cards([
        {"label": "Programs Compared", "value": len(rows)},
        {"label": "Total -O0",         "value": _fmt_bytes(total_o0)},
        {"label": "Total -O3",         "value": _fmt_bytes(total_o3)},
        {"label": "Net Savings",       "value": _fmt_bytes(savings), "delta": f"{pct:.2f}% reduction"},
    ])

    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.markdown("### Top 5 Optimizations")
    st.dataframe(rows[:5], use_container_width=True, hide_index=True)

    summary_path = RESULTS_DIR / _FILES["summary"]
    if summary_path.exists():
        with st.expander("Full summary report (summary.md)", expanded=False):
            st.markdown(_read_text(summary_path))


# ---------------------------------------------------------------------------
# Page: Diff Viewer
# ---------------------------------------------------------------------------

def _page_diff_viewer(snap: dict[str, Any]) -> None:
    st.markdown("## Optimization Diff Viewer")
    st.caption("Unified diff and side-by-side IR comparison for compile-time optimization artifacts")

    if not DIFF_DIR.exists() or not list(DIFF_DIR.glob("*.diff")):
        st.info("No diff artifacts found. Run the pipeline first.")
        return

    diff_files = sorted(DIFF_DIR.glob("*.diff"))
    options    = [f"{p.name}  ({_fmt_bytes(_file_size(p))})" for p in diff_files]
    selected   = st.selectbox("Select comparison", options)
    base_name  = selected.split("  (")[0][:-5]   # strip ".diff" suffix
    o0_path    = OPT_IR_DIR / f"{base_name}.O0.ll"
    o3_path    = OPT_IR_DIR / f"{base_name}.O3.ll"
    diff_path  = DIFF_DIR   / f"{base_name}.diff"

    if not o0_path.exists() or not o3_path.exists():
        st.warning("Optimized IR files for this entry are missing.")
        return

    o0_sz  = _file_size(o0_path)
    o3_sz  = _file_size(o3_path)
    delta  = o0_sz - o3_sz
    reduct = (delta / o0_sz * 100) if o0_sz else 0.0

    _metric_cards([
        {"label": "O0 Size",   "value": _fmt_bytes(o0_sz)},
        {"label": "O3 Size",   "value": _fmt_bytes(o3_sz)},
        {"label": "Change",    "value": _fmt_bytes(abs(delta)),  "delta": "smaller" if delta >= 0 else "larger"},
        {"label": "Reduction", "value": f"{reduct:.2f}%"},
    ])

    if delta >= 0:
        st.success(f"-O3 saved {_fmt_bytes(delta)} ({reduct:.2f}%)")
    else:
        st.warning(f"-O3 expanded the IR by {_fmt_bytes(abs(delta))} ({abs(reduct):.2f}%)")

    _render_side_by_side(_read_text(o0_path), _read_text(o3_path))

    st.markdown("#### Unified diff")
    st.code(_read_text(diff_path) or "# (empty diff)", language="diff")


# ---------------------------------------------------------------------------
# Page: Logs
# ---------------------------------------------------------------------------

def _page_logs(snap: dict[str, Any]) -> None:
    st.markdown("## Logs & Executions")
    st.caption("Triage JSON, execution records, and raw per-file logs")

    meta = snap.get("run_metadata", {})
    if meta:
        st.markdown("### Run metadata")
        c1, c2 = st.columns(2)
        items = [(k, meta[k]) for k in
                 ("generated_at", "backend", "model", "mode", "scope",
                  "gen_count", "mut_per_file") if k in meta]
        half = (len(items) + 1) // 2
        with c1:
            for k, v in items[:half]:
                st.write(f"• **{k}**: `{v}`")
        with c2:
            for k, v in items[half:]:
                st.write(f"• **{k}**: `{v}`")

    t1, t2 = st.columns(2)
    with t1:
        st.markdown("#### Triage JSON")
        triage_path = RESULTS_DIR / _FILES["triage"]
        if triage_path.exists():
            st.caption(f"Size: {_fmt_bytes(_file_size(triage_path))}")
            st.json(_read_json(triage_path))
        else:
            st.info("No triage data yet.")

    with t2:
        st.markdown("#### Execution records")
        exec_path = RESULTS_DIR / _FILES["executions"]
        if exec_path.exists():
            rows = _read_jsonl(exec_path)
            st.caption(f"{len(rows)} rows  •  {_fmt_bytes(_file_size(exec_path))}")
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No execution records yet.")

    st.markdown("#### Raw log files")
    if not LOGS_DIR.exists():
        st.info("Logs directory not found.")
        return

    log_files = sorted(p for p in LOGS_DIR.iterdir() if p.suffix in {".out", ".err", ".log"})
    if not log_files:
        st.info("No log files found.")
        return

    options  = [f"{p.name}  ({_fmt_bytes(_file_size(p))})" for p in log_files]
    selected = st.selectbox("Select log file", options)
    name     = selected.split("  (")[0]
    content  = _read_text(LOGS_DIR / name)
    if len(content) > 50_000:
        st.warning("Large file — showing last 50 KB.")
        content = content[-50_000:]
    st.code(content or "(empty)", language="text")

    # CSV metrics
    with st.expander("Raw metrics CSV", expanded=False):
        csv_path = EVAL_DIR / _FILES["metrics_csv"]
        if csv_path.exists():
            try:
                with csv_path.open(newline="", encoding="utf-8") as fh:
                    st.dataframe(list(csv.DictReader(fh)), use_container_width=True, hide_index=True)
            except Exception:
                st.info("Could not parse metrics.csv.")
        else:
            st.info("metrics.csv not found.")


# ---------------------------------------------------------------------------
# Page: Run History
# ---------------------------------------------------------------------------

def _page_history() -> None:
    st.markdown("## Run History")
    st.caption("Metrics appended to results/history.jsonl after every pipeline run")

    history_path = RESULTS_DIR / "history.jsonl"
    if not history_path.exists():
        st.info("No history yet. Run the pipeline at least once to start recording history.")
        return

    rows = _read_jsonl(history_path)
    if not rows:
        st.info("history.jsonl is empty.")
        return

    # Normalise rows for display
    display = []
    for r in rows:
        display.append({
            "Timestamp":          r.get("timestamp", "")[:19].replace("T", " "),
            "Generated":          r.get("generated", 0),
            "Mutated":            r.get("mutated", 0),
            "Valid":              r.get("valid", 0),
            "Diffs":              r.get("diffs", 0),
            "Pairs":              r.get("paired_binary_cases", 0),
            "Savings (bytes)":    r.get("binary_savings", 0),
            "Reduction (%)":      round(float(r.get("binary_reduction_pct", 0)), 2),
            "Compile Failures":   r.get("compile_failed", 0),
            "Timeouts":           r.get("timeouts", 0),
        })

    st.dataframe(display, use_container_width=True, hide_index=True)

    # Trend chart: diffs and savings over runs
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import io

        run_nums    = list(range(1, len(rows) + 1))
        diffs_vals  = [r.get("diffs", 0) for r in rows]
        savings_vals= [r.get("binary_savings", 0) for r in rows]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), facecolor="#09101c")
        for ax in (ax1, ax2):
            ax.set_facecolor("#09101c")
            ax.tick_params(colors="#cbd5e1")
            for spine in ("top", "right"):
                ax.spines[spine].set_visible(False)
            for spine in ("left", "bottom"):
                ax.spines[spine].set_color("#334155")

        ax1.plot(run_nums, diffs_vals,  color="#ef4444", marker="o", linewidth=2, label="Diffs")
        ax1.set_ylabel("Output Diffs", color="#cbd5e1")
        ax1.legend(facecolor="#0f172a", labelcolor="#e2e8f0")

        ax2.plot(run_nums, savings_vals, color="#22c55e", marker="s", linewidth=2, label="Binary Savings (bytes)")
        ax2.set_ylabel("Savings (bytes)", color="#cbd5e1")
        ax2.set_xlabel("Run #", color="#cbd5e1")
        ax2.legend(facecolor="#0f172a", labelcolor="#e2e8f0")

        fig.suptitle("Pipeline Trends Across Runs", color="#f8fafc", fontsize=12)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        st.image(buf, use_container_width=True)
    except Exception:
        pass  # chart is optional — table is already shown above

    # Strategy diff rates per run
    strategy_runs: dict[str, list] = {}
    for r in rows:
        for strat, rate in r.get("strategy_diff_rates", {}).items():
            strategy_runs.setdefault(strat, []).append(rate)

    if strategy_runs:
        st.markdown("### Strategy Diff Rates Over Time")
        st.caption("Each cell is the diff rate (%) for that strategy in that run")
        table = []
        n_runs = len(rows)
        for strat, rates_list in sorted(strategy_runs.items()):
            # Pad with None if strategy didn't appear in every run
            padded = [None] * (n_runs - len(rates_list)) + rates_list
            row_d: dict[str, Any] = {"Strategy": strat}
            for i, v in enumerate(padded, 1):
                row_d[f"Run {i}"] = f"{v:.1f}%" if v is not None else "—"
            table.append(row_d)
        st.dataframe(table, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main dashboard entry point
# ---------------------------------------------------------------------------

def run_dashboard() -> None:
    if st is None:
        raise RuntimeError("streamlit is required. Install it with: pip install streamlit")

    st.set_page_config(
        page_title = "LLVM IR Differential Testing Studio",
        page_icon  = "⚙️",
        layout     = "wide",
        initial_sidebar_state = "expanded",
    )
    _inject_styles()

    # Auto-generate varied sample data on first load so the diff viewer
    # always has something to show even before the user runs the pipeline.
    _marker = RESULTS_DIR / ".varied_generated"
    if not _marker.exists():
        try:
            subprocess.run(
                [sys.executable,
                 str(ROOT / "scripts" / "generate_varied_binary_sizes.py"),
                 "--seed", str(cfg.varied_binaries_seed if hasattr(cfg, "varied_binaries_seed") else 1337),
                 "--count", "10"],
                check=True,
            )
            _marker.parent.mkdir(parents=True, exist_ok=True)
            _marker.write_text("done")
        except Exception as exc:
            st.warning(f"Auto-generation skipped: {exc}")

    snap = _load_snapshot()

    with st.sidebar:
        st.markdown("### ⚙️ LLVM IR Studio")
        st.caption("Navigation")
        page = st.radio(
            "",
            ["Overview", "Optimization Artifacts", "Diff Viewer", "Logs", "Run History"],
            label_visibility="collapsed",
        )
        st.divider()

        # ── Run Pipeline panel ────────────────────────────────────────────
        st.markdown("### ▶ Run Pipeline")
        run_gen_count = st.number_input(
            "IR files to generate",
            min_value=1, max_value=500,
            value=int(cfg.generation.count),
            step=1,
            key="run_gen_count",
        )
        run_backend = st.selectbox(
            "Backend",
            ["template", "openai"],
            index=0 if cfg.generation.backend == "template" else 1,
            key="run_backend",
        )
        run_mode = st.selectbox(
            "Mode",
            ["generate", "mutate"],
            index=0 if cfg.generation.mode == "generate" else 1,
            key="run_mode",
        )

        if st.button("🚀 Run Pipeline", use_container_width=True, key="run_pipeline_btn"):
            cmd = [
                sys.executable, "-u", str(ROOT / "main.py"),
                "--gen-count", str(run_gen_count),
                "--backend",   run_backend,
                "--mode",      run_mode,
            ]
            with st.spinner("Running pipeline…"):
                log_placeholder = st.empty()
                log_lines: list[str] = []
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=str(ROOT),
                    )
                    for line in iter(proc.stdout.readline, ""):  # type: ignore[union-attr]
                        log_lines.append(line.rstrip())
                        log_placeholder.code("\n".join(log_lines[-30:]), language="text")
                    proc.wait()
                    if proc.returncode == 0:
                        st.success("Pipeline completed — refresh the page to see updated results.")
                    else:
                        st.error(f"Pipeline exited with code {proc.returncode}.")
                except Exception as exc:
                    st.error(f"Failed to start pipeline: {exc}")

        st.divider()
        st.caption("Key directories")
        st.write(f"• `{_PATHS.valid_dir.relative_to(ROOT)}`")
        st.write(f"• `{RESULTS_DIR.relative_to(ROOT)}`")
        st.write(f"• `{EVAL_DIR.relative_to(ROOT)}`")
        st.write(f"• `{DIFF_DIR.relative_to(ROOT)}`")

    if page == "Overview":
        _page_overview(snap)
    elif page == "Optimization Artifacts":
        _page_artifacts(snap)
    elif page == "Diff Viewer":
        _page_diff_viewer(snap)
    elif page == "Logs":
        _page_logs(snap)
    elif page == "Run History":
        _page_history()
    else:
        _page_logs(snap)
