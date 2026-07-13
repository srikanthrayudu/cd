"""
tests/test_config.py — Unit tests for src/config.py

Verifies that config.yaml is loaded correctly and that all expected
fields are present with the right types.
"""
import pytest
from pathlib import Path
from src.config import cfg, ProjectPaths


class TestConfigLoads:
    def test_generation_count_is_positive_int(self):
        assert isinstance(cfg.generation.count, int)
        assert cfg.generation.count > 0

    def test_generation_backend_is_known(self):
        assert cfg.generation.backend in ("template", "openai")

    def test_mutation_per_file_is_positive_int(self):
        assert isinstance(cfg.mutation.per_file, int)
        assert cfg.mutation.per_file > 0

    def test_mutation_seed_is_int(self):
        assert isinstance(cfg.mutation.seed, int)

    def test_strategy_weights_are_floats_in_range(self):
        w = cfg.mutation.strategy_weights
        for name in ("opcode_swap", "dead_code", "block_split", "cond_phi", "deep_cfg", "const_tweak"):
            val = getattr(w, name)
            assert isinstance(val, float), f"{name} should be float"
            assert 0.0 <= val <= 1.0,       f"{name} weight out of range: {val}"

    def test_execution_timeouts_are_positive(self):
        t = cfg.execution.timeouts
        for name in ("lli", "compile", "link", "run", "emit_ir"):
            val = getattr(t, name)
            assert isinstance(val, int), f"{name} timeout should be int"
            assert val > 0,              f"{name} timeout must be positive"

    def test_opt_levels_non_empty(self):
        assert len(cfg.execution.opt_levels) >= 2

    def test_reporting_files_has_required_keys(self):
        required = {"executions", "diffs", "skipped", "summary", "triage",
                    "metrics_json", "metrics_csv", "metrics_png", "run_manifest"}
        assert required.issubset(cfg.reporting.files.keys())

    def test_template_heavy_bias_in_range(self):
        assert 0.0 <= cfg.templates.heavy_bias <= 1.0

    def test_seed_corpus_chain_length_positive(self):
        assert cfg.seed_corpus.chain_length > 0

    def test_validation_tool_names_are_strings(self):
        assert isinstance(cfg.validation.assembler_tool, str)
        assert isinstance(cfg.validation.optimizer_tool, str)


class TestProjectPaths:
    def test_from_config_returns_absolute_paths(self, tmp_path):
        paths = ProjectPaths.from_config(cfg, tmp_path)
        for attr in ("dataset_dir", "generated_dir", "mutated_dir", "valid_dir",
                     "invalid_dir", "logs_dir", "results_dir", "evaluation_dir",
                     "optimized_dir", "diffs_dir"):
            p = getattr(paths, attr)
            assert isinstance(p, Path), f"{attr} should be a Path"
            assert p.is_absolute(),     f"{attr} should be absolute"

    def test_ensure_dirs_creates_directories(self, tmp_path):
        paths = ProjectPaths.from_config(cfg, tmp_path)
        paths.ensure_dirs()
        for attr in ("dataset_dir", "generated_dir", "valid_dir", "logs_dir",
                     "results_dir", "evaluation_dir"):
            assert getattr(paths, attr).is_dir(), f"{attr} was not created"
