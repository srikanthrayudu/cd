"""
src — LLVM IR Differential Testing package.

Public API summary
------------------
config:       cfg (Config singleton), ProjectPaths
ir_generator: write_generated_ir, generate_ir_snippets
mutator:      mutate_files
validator:    validate_ir, validate_directory
executor:     run_lli, run_clang, emit_optimized_ir, ExecutionResult
diff_test:    compare_results, compare_optimized_ir, DiffResult, CodeDiffResult
metrics:      compute_metrics, write_metrics, write_csv, write_bar_chart, Metrics
reporting:    build_summary, write_summary, SummaryReport
triage:       build_triage, write_triage, TriageReport
replay:       replay_failures, write_replay, ReplayResult
pipeline:     run_pipeline
"""
