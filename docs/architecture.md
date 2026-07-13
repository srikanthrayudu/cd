# Architecture

## Overview

The LLVM IR Differential Testing pipeline generates LLVM IR programs, mutates
them, validates them with LLVM tools, compiles them at `-O0` and `-O3`, and
checks whether both optimisation levels produce identical runtime output.

Binary-size differences between `-O0` and `-O3` are measured and reported as
a concrete, quantitative demonstration of what the optimiser removes.

---

## Directory layout

```
cd/
├── config.yaml                ← single source of truth for every tunable value
├── main.py                    ← CLI entry point
├── ui_app.py                  ← Streamlit dashboard entry point
├── run.sh                     ← bootstrap venv + run pipeline + launch UI
├── stop.sh                    ← kill any running pipeline/UI processes
├── Dockerfile                 ← container image definition
├── docker-compose.yml         ← compose configuration
├── requirements.txt           ← pinned Python dependencies
│
├── src/
│   ├── config.py              ← load config.yaml → typed dataclasses (cfg)
│   ├── templates.py           ← named LLVM IR template strings
│   ├── ir_generator.py        ← generate IR from templates or an LLM backend
│   ├── mutator.py             ← apply mutation strategies to IR files
│   ├── validator.py           ← validate IR with llvm-as + opt (or regex)
│   ├── executor.py            ← run lli / clang, measure object-file size
│   ├── diff_test.py           ← compare runtime outputs and textual IR
│   ├── metrics.py             ← aggregate counts, sizes, diffs → Metrics
│   ├── reporting.py           ← build and write Markdown summary
│   ├── triage.py              ← group failures by reason
│   ├── replay.py              ← re-run previously failed files
│   ├── pipeline.py            ← orchestrate all of the above
│   └── ui_dashboard.py        ← Streamlit pages (Overview, Artifacts, Diffs, Logs)
│
├── scripts/
│   ├── run_pipeline.py        ← thin wrapper around pipeline.run_pipeline
│   ├── run_llm_generation.py  ← generate IR only
│   ├── mutate_ir.py           ← mutate an IR directory
│   ├── validate_ir.py         ← validate generated + mutated IR
│   ├── run_differential.py    ← execution + diff stage only
│   ├── summary_report.py      ← regenerate results/summary.md
│   ├── triage_report.py       ← regenerate results/triage.json
│   ├── replay_failures.py     ← replay diff failures
│   ├── metrics_report.py      ← recompute all evaluation artefacts
│   ├── generate_varied_binary_sizes.py  ← generate intentionally varied binaries
│   └── prepare_dataset.sh     ← compile C samples into IR seed files
│
├── dataset/                   ← seed IR corpus
├── generated_ir/              ← freshly generated *.ll files (staging)
├── mutated_ir/                ← mutated variants (staging)
├── valid_ir/                  ← files that passed validation
├── invalid_ir/                ← files that failed validation
├── logs/                      ← per-file stdout/stderr from lli + clang
├── results/
│   ├── executions.jsonl       ← structured execution records (lli, O0, O3)
│   ├── diffs.jsonl            ← files where O0 ≠ O3 runtime output
│   ├── skipped_exec.jsonl     ← files skipped due to missing tools
│   ├── run_manifest.json      ← run metadata for reproducibility
│   ├── summary.md             ← human-readable Markdown summary
│   ├── triage.json            ← failures grouped by reason
│   ├── optimized_ir/          ← textual IR after opt -O0 / -O3
│   └── code_diffs/            ← unified diffs between O0 and O3 IR
└── evaluation/
    ├── metrics.json           ← all numeric metrics in one JSON file
    ├── metrics.csv            ← same metrics as a single-row CSV
    └── metrics.png            ← bar chart of key pipeline counts
```

---

## Data flow

```
config.yaml
    │
    ▼
src/config.py  ──────────────────────────────────┐
    │                                            │ cfg (singleton)
    ▼                                            │
ir_generator.py                                  │
  • picks template from templates.py             │
  • or calls OpenAI API                          │
  • writes generated_ir/*.ll                     │
    │                                            │
    ▼                                            │
mutator.py                                       │
  • opcode swap, dead code, CFG splits, const    │
  • writes mutated_ir/*.ll                       │
    │                                            │
    ▼                                            │
validator.py                                     │
  • llvm-as + opt -passes=verify                 │
  • regex fallback if LLVM tools absent          │
  • moves files to valid_ir/ or invalid_ir/      │
    │                                            │
    ▼                                            │
executor.py  ◄───────────────────────────────────┘
  • run_lli      → interpreter result
  • run_clang    → compile -O0/-O3, measure .o size, run executable
  • emit_optimized_ir → textual IR via opt -S
    │
    ▼
diff_test.py
  • compare_results      → exit code / stdout / stderr match?
  • compare_optimized_ir → unified diff of textual IR
    │
    ▼
metrics.py  →  evaluation/metrics.{json,csv,png}
reporting.py → results/summary.md
triage.py   → results/triage.json
```

---

## Configuration contract

**Rule: every numeric constant, file name, tool name, and tunable knob lives
in `config.yaml`. No Python source file may define these values itself.**

`src/config.py` loads `config.yaml` once at import time into a frozen
dataclass hierarchy. Every other module imports `cfg` from there:

```python
from src.config import cfg

timeout = cfg.execution.timeouts.lli        # int from config.yaml
summary = cfg.reporting.files["summary"]    # "summary.md"
```

`ProjectPaths` resolves the relative directory names from config into
absolute `pathlib.Path` objects anchored at the project root:

```python
from src.config import cfg, ProjectPaths
paths = ProjectPaths.from_config(cfg, Path.cwd())
paths.ensure_dirs()   # creates all directories
```

---

## Key design decisions

### Template-first generation
Templates live in `src/templates.py` as named string constants with
`{id}` and `{c}` format placeholders. They are self-documenting: each
template includes a comment explaining which optimisation it exercises
(constant folding, DCE, LICM, branch simplification, …).

The generator selects templates by weighted sampling. Heavy templates
(those with complex CFGs) are preferred 85 % of the time (configurable
via `templates.heavy_bias`). All weights live in `config.yaml`.

### Size-padding decorator
After selecting a template, `ir_generator._decorate` appends an
arithmetic chain before the `ret` instruction and a dead helper function.
Under `-O0` both are kept, making the binary larger. Under `-O3` the
chain is constant-folded and the dead helper is eliminated, creating a
measurable binary-size delta.

Chain length and helper size are driven by `config.yaml →
templates.decorator`.

### Dry-run / tool-absent mode
When LLVM tools (`llvm-as`, `opt`, `lli`, `clang`) are absent, the
pipeline degrades gracefully:
- Validation falls back to a lightweight regex sanity check.
- Execution is skipped and the file is recorded in `skipped_exec.jsonl`.
- The summary report still renders; it notes which tools are missing.

The pipeline **always completes** — it never aborts due to missing tooling.

### Reproducibility
Every run writes `results/run_manifest.json` containing the exact
parameters used (backend, model, gen_count, mut_per_file, seeds,
timestamps). Re-running with the same manifest parameters produces the
same IR files.

### Separation of concerns
Each module has exactly one job:

| Module | Responsibility |
| :----- | :------------- |
| `config.py` | Load and expose typed configuration |
| `templates.py` | Define IR template strings |
| `ir_generator.py` | Produce IR text |
| `mutator.py` | Transform IR text |
| `validator.py` | Accept or reject IR files |
| `executor.py` | Run tools and capture results |
| `diff_test.py` | Compare two execution results |
| `metrics.py` | Aggregate numbers |
| `reporting.py` | Render a Markdown report |
| `triage.py` | Group failures |
| `replay.py` | Re-execute failed files |
| `pipeline.py` | Orchestrate all of the above |
| `ui_dashboard.py` | Present results in a browser |

`pipeline.py` contains **no domain logic** — only sequencing calls to
the modules above.

---

## Running the pipeline

```bash
# Full pipeline (template backend, defaults from config.yaml)
python3 main.py

# Override count and backend at the command line
python3 main.py --gen-count 20 --backend openai --model gpt-4o-mini

# Test a single IR file (skip generation/mutation)
python3 main.py --file test.ll

# Dashboard only
streamlit run ui_app.py
```

See `README.md` for Docker and script usage.
