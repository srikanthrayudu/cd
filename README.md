# LLVM IR Differential Testing

A pipeline that generates LLVM IR programs, mutates them, validates them with
LLVM tools, compiles them at **-O0** and **-O3**, and checks whether both
optimisation levels produce identical output.

Binary-size differences between -O0 and -O3 are recorded and reported as a
concrete measure of how much the optimiser shrinks the code.

---

## Architecture

```
config.yaml          ← single source of truth for every tunable value
    │
    ▼
src/config.py        ← loads config.yaml, exposes typed dataclasses (cfg)
    │
    ├── src/ir_generator.py   ← generates IR from templates or an LLM backend
    ├── src/mutator.py        ← applies mutation strategies to IR files
    ├── src/validator.py      ← validates IR with llvm-as + opt (or regex fallback)
    ├── src/executor.py       ← runs lli / clang, measures object-file size
    ├── src/diff_test.py      ← compares runtime outputs and textual IR
    ├── src/metrics.py        ← aggregates counts, sizes, and diffs
    ├── src/reporting.py      ← builds and writes the Markdown summary
    ├── src/triage.py         ← groups failures by reason for quick triage
    ├── src/replay.py         ← re-runs previously failed files
    └── src/pipeline.py       ← orchestrates all of the above
```

**Rule:** every numeric constant, path, tool name, and tunable knob lives in
`config.yaml`.  No hardcoded values appear in any Python file.

---

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run the full pipeline with defaults from config.yaml
python3 main.py

# Override the number of generated files and the backend
python3 main.py --gen-count 20 --backend openai --model gpt-4o-mini

# Test a single IR file (skip generation/mutation)
python3 main.py --file test.ll
```

### Output locations (all relative to the project root)

| Directory / File              | Contents                                 |
| :---------------------------- | :--------------------------------------- |
| `generated_ir/`               | Raw generated *.ll files                 |
| `mutated_ir/`                 | Mutated variants                         |
| `valid_ir/`                   | IR files that passed validation          |
| `invalid_ir/`                 | IR files that failed validation          |
| `results/optimized_ir/`       | Textual IR after opt -O0 / -O3           |
| `results/code_diffs/`         | Unified diffs between O0 and O3 IR       |
| `logs/`                       | Per-file stdout/stderr from lli + clang  |
| `results/executions.jsonl`    | Structured execution records             |
| `results/diffs.jsonl`         | Files where O0 ≠ O3 runtime output       |
| `results/skipped_exec.jsonl`  | Files where LLVM tools were unavailable  |
| `results/run_manifest.json`   | Run metadata for reproducibility         |
| `results/summary.md`          | Human-readable Markdown summary          |
| `results/triage.json`         | Failures grouped by reason               |
| `evaluation/metrics.json`     | All numeric metrics in one JSON file     |
| `evaluation/metrics.csv`      | Same metrics as a single-row CSV         |
| `evaluation/metrics.png`      | Bar chart of key pipeline counts         |

---

## Configuration

All settings live in `config.yaml` at the project root.  The most commonly
changed values are:

```yaml
generation:
  count:   10        # how many IR files to generate
  backend: template  # "template" (no API key) or "openai"
  model:   gpt-4o-mini

mutation:
  per_file: 2        # mutations per dataset file

execution:
  timeouts:
    lli:     5       # seconds
    compile: 5
```

No Python source file needs to be edited to change these values.

---

## Optional: OpenAI-backed generation

Create a `.env` file from the example and add your key:

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...
```

Then run:

```bash
python3 main.py --backend openai --model gpt-4o-mini --gen-count 10
```

---

## Optional: Alive2 semantic validation

If `alive-tv` is on your PATH, enable it with:

```bash
ALIVE2_VALIDATE=1 python3 main.py
```

## Optional: SSA repair pass

If generated IR contains `alloca`/`store` patterns that need promotion:

```bash
SSA_FIX=1 python3 main.py
```

---

## Scripts

| Script                              | Purpose                                    |
| :---------------------------------- | :----------------------------------------- |
| `scripts/run_pipeline.py`           | Thin wrapper around `main.py`              |
| `scripts/run_llm_generation.py`     | Generate IR only (no mutation/validation)  |
| `scripts/mutate_ir.py`              | Mutate an existing IR directory            |
| `scripts/validate_ir.py`            | Validate an IR directory                   |
| `scripts/run_differential.py`       | Run differential testing on `valid_ir/`    |
| `scripts/summary_report.py`         | Re-generate `results/summary.md`           |
| `scripts/triage_report.py`          | Re-generate `results/triage.json`          |
| `scripts/replay_failures.py`        | Re-run files that previously had diffs     |
| `scripts/generate_varied_binary_sizes.py` | Generate intentionally varied binaries |
| `scripts/prepare_dataset.sh`        | Compile C samples into IR seed files       |

---

## Docker

```bash
# Build
docker build -t cd_project:latest .

# Run
docker run --rm -it -p 8501:8501 \
  -v "$(pwd)":/workspace \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  cd_project:latest

# Or with docker-compose
docker compose up --build
```

---

## Design Decisions

- **Template-first** generation works without any API key and produces IR
  that reliably demonstrates constant folding, dead-code elimination, loop
  optimisation, and branch simplification.

- **Dry-run mode**: when LLVM tools are not installed, validation falls back
  to a lightweight regex check and execution is skipped with a note in
  `skipped_exec.jsonl`.  The pipeline always completes.

- **Reproducibility**: every run writes a `run_manifest.json` with the exact
  parameters, seed values, and timestamps used.

- **Separation of concerns**: each module has one job.  The pipeline module
  only orchestrates; it never contains domain logic.
