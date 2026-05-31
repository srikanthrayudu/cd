# Architecture

This prototype follows the modular flow described in `deep-research-report.md`:

- Seed corpus in `dataset/`
- Generation in `generated_ir/`
- Mutation in `mutated_ir/`
- Validation into `valid_ir/` and `invalid_ir/`
- Execution with `lli` and `clang` plus differential testing (when LLVM tools are available)
- Logs stored in `logs/` and JSONL results in `results/`
- Run metadata stored in `results/run_manifest.json`
- Metrics stored in `evaluation/metrics.json`, `evaluation/metrics.csv`, and `evaluation/metrics.png`
- Summary report stored in `results/summary.md`
- Triage report stored in `results/triage.json`
- Replay report stored in `results/replay.json`

