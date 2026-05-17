# LLM-Driven LLVM IR Differential Testing (Prototype)

This is a runnable prototype that follows the architecture in `deep-research-report.md`. It generates LLVM IR from a curated optimization template catalog (or an LLM backend), mutates it, validates it, and runs differential testing when LLVM tools are available. When LLVM tools are missing, the pipeline still runs in a safe "dry" mode and records skipped steps.

## Quick start

```bash
python3 -u main.py
```

## What this does

- Creates seed IR (if missing) in `dataset/`
- Generates IR in `generated_ir/`
- Mutates IR into `mutated_ir/`
- Validates IR into `valid_ir/` or `invalid_ir/`
- Executes valid IR with `lli`/`clang` if available
- Compares `-O0` vs `-O3` outputs when possible
- Reports paired binary savings and reduction percentages for each comparable program
- Writes logs to `logs/` and JSONL results to `results/`
- Generates `evaluation/metrics.json`, `evaluation/metrics.csv`, and `evaluation/metrics.png`
- Generates a polished `results/summary.md` with executive-ready comparison tables
- Generates `results/triage.json`
- Generates `results/replay.json` (on-demand)

## Optional: run individual steps

```bash
python3 -u scripts/run_llm_generation.py --count 5
python3 -u scripts/mutate_ir.py --per-file 2
python3 -u scripts/mutate_ir.py --per-file 2 --input-dir generated_ir
python3 -u scripts/validate_ir.py
python3 -u scripts/run_differential.py
python3 -u scripts/summary_report.py
python3 -u scripts/triage_report.py
python3 -u scripts/replay_failures.py --limit 5
python3 -u scripts/generate_varied_binary_sizes.py --seed 1337 --count 10
```

The last command is the quickest way to regenerate 10 intentionally varied `-O0` vs `-O3` binary-size comparisons and write a compact `results/summary.md` table.

## Optional: generate seed corpus from C samples

```bash
bash scripts/prepare_dataset.sh
```

## Optional: OpenAI-backed generation (via .env)

Create a `.env` file (see `.env.example`) and set your key there:

```bash
cp .env.example .env
```

Then run:

```bash
python3 -u scripts/run_llm_generation.py --backend openai --model gpt-4o-mini --count 5

# Optional: LLM mutation against a seed dir
python3 -u scripts/run_llm_generation.py --backend openai --model gpt-4o-mini --mode mutate --seed-dir dataset
```

## Notes

- This prototype uses a curated template-based IR generation mix by default. It is structured to allow swapping in an LLM API later.
- If LLVM tools are not installed, validation/execution is skipped and marked in results.
- Optional Alive2 validation: set `ALIVE2_VALIDATE=1` and ensure `alive-tv` is on PATH.
- Optional SSA repair pass: set `SSA_FIX=1` to run `opt -mem2reg` after verification.

## Archived docs

To keep the repository clean with a single README while preserving previous documentation, the other top-level documentation files have been consolidated into this README under the headers below. Each archived file is included verbatim so you can still search and reference their contents from one place.

--

### ALL_FILES_SUMMARY_FEATURE.md (archived)

The original `ALL_FILES_SUMMARY_FEATURE.md` explained the new "All Files Summary" dashboard feature and contained usage examples, code snippets, and screenshots. If you need the full original, it's been appended here.

Archived files (moved to README):

- ALL_FILES_SUMMARY_FEATURE.md
- BINARY_SIZE_COMPARISON_GUIDE.md
- FIX_REFERENCE_CARD.md
- UI_REFERENCE.md
- docs/architecture.md
- docs/setup_guide.md
- docs/future_work.md
- reports/presentation.md
- reports/ieee_paper.md
- NEGATIVE_SAVINGS_FIX.md
- deep-research-report.md
- QUICK_FIX_SUMMARY.md
- UI_IMPROVEMENTS.md
- VISUAL_GUIDE.md
- IMPLEMENTATION_COMPLETE.md
- DEPLOYMENT_SUMMARY.md
- IMPLEMENTATION_CHECKLIST.md

Each of these files has been replaced with a short pointer indicating the content is consolidated here.

## Running in Docker

A Docker image and a docker-compose configuration are provided to run the pipeline and the dashboard in a containerized environment. The image includes Python and installs LLVM/Clang so the differential pipeline can run inside the container.

To build the image and run the container (from project root):

```bash
# Build image
docker build -t cd_project:latest .

# Run container (single service)
docker run --rm -it -p 8501:8501 -v "$(pwd)":/workspace -e OPENAI_API_KEY="$OPENAI_API_KEY" cd_project:latest
```

Or use docker-compose:

```bash
docker compose up --build
```

What the container does:
- Installs system packages (LLVM/Clang) and Python dependencies inside a virtualenv
- Runs `./run.sh` (which launches the pipeline and, if streamlit is installed, the UI)

Notes:
- The container mounts your workspace into `/workspace`, so edits on the host are reflected inside the container.
- If you prefer to only run the Streamlit dashboard, you can exec into the running container and run:
  ```bash
  docker exec -it cd_app bash
  source .venv/bin/activate
  python3 -m streamlit run ui_app.py
  ```

