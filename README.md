# LLM-Driven LLVM IR Differential Testing (Prototype)

This is a runnable prototype that follows the architecture in `deep-research-report.md`. It generates LLVM IR (template or LLM-backed), mutates it, validates it, and runs differential testing when LLVM tools are available. When LLVM tools are missing, the pipeline still runs in a safe "dry" mode and records skipped steps.

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
- Writes logs to `logs/` and JSONL results to `results/`
- Generates `evaluation/metrics.json`, `evaluation/metrics.csv`, and `evaluation/metrics.png`
- Generates `results/summary.md`
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
```

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

- This prototype uses template-based IR generation by default. It is structured to allow swapping in an LLM API later.
- If LLVM tools are not installed, validation/execution is skipped and marked in results.
- Optional Alive2 validation: set `ALIVE2_VALIDATE=1` and ensure `alive-tv` is on PATH.
- Optional SSA repair pass: set `SSA_FIX=1` to run `opt -mem2reg` after verification.
