"""
config.py — Central configuration loader.

Reads config.yaml once at import time and exposes strongly-typed dataclasses
so that every other module can import exactly the settings it needs without
touching YAML directly.

Usage:
    from src.config import cfg, ProjectPaths

    paths = ProjectPaths.from_config(cfg, root=Path.cwd())
    paths.ensure_dirs()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Locate and load config.yaml (search project root, then parent dirs)
# ---------------------------------------------------------------------------

def _find_config() -> Path:
    """Walk upward from this file's directory until config.yaml is found."""
    current = Path(__file__).resolve().parent
    for _ in range(6):  # limit search depth
        candidate = current / "config.yaml"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        "config.yaml not found. Expected it at the project root alongside main.py."
    )


def _load_raw() -> dict:
    config_path = _find_config()
    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"config.yaml is malformed — expected a mapping at the top level: {config_path}")
    return data


RAW: dict = _load_raw()


# ---------------------------------------------------------------------------
# Typed section dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PathConfig:
    dataset:    str
    generated:  str
    mutated:    str
    valid:      str
    invalid:    str
    logs:       str
    results:    str
    evaluation: str
    optimized:  str
    diffs:      str

    @staticmethod
    def from_dict(d: dict) -> "PathConfig":
        return PathConfig(
            dataset    = d["dataset"],
            generated  = d["generated"],
            mutated    = d["mutated"],
            valid      = d["valid"],
            invalid    = d["invalid"],
            logs       = d["logs"],
            results    = d["results"],
            evaluation = d["evaluation"],
            optimized  = d["optimized"],
            diffs      = d["diffs"],
        )


@dataclass(frozen=True)
class GenerationConfig:
    count:              int
    seed:               int
    backend:            str
    model:              str
    mode:               str
    llm_prompt:         str
    llm_mutate_prompt:  str

    @staticmethod
    def from_dict(d: dict) -> "GenerationConfig":
        return GenerationConfig(
            count             = int(d["count"]),
            seed              = int(d["seed"]),
            backend           = str(d["backend"]),
            model             = str(d["model"]),
            mode              = str(d["mode"]),
            llm_prompt        = str(d["llm_prompt"]).strip(),
            llm_mutate_prompt = str(d["llm_mutate_prompt"]).strip(),
        )


@dataclass(frozen=True)
class MutationStrategyWeights:
    opcode_swap: float
    dead_code:   float
    block_split: float
    cond_phi:    float
    deep_cfg:    float
    const_tweak: float

    @staticmethod
    def from_dict(d: dict) -> "MutationStrategyWeights":
        return MutationStrategyWeights(
            opcode_swap = float(d["opcode_swap"]),
            dead_code   = float(d["dead_code"]),
            block_split = float(d["block_split"]),
            cond_phi    = float(d["cond_phi"]),
            deep_cfg    = float(d["deep_cfg"]),
            const_tweak = float(d["const_tweak"]),
        )


@dataclass(frozen=True)
class MutationConfig:
    per_file:               int
    per_generated_file:     int
    seed:                   int
    strategy_weights:       MutationStrategyWeights
    max_strategies_per_file: int

    @staticmethod
    def from_dict(d: dict) -> "MutationConfig":
        return MutationConfig(
            per_file               = int(d["per_file"]),
            per_generated_file     = int(d["per_generated_file"]),
            seed                   = int(d["seed"]),
            strategy_weights       = MutationStrategyWeights.from_dict(d["strategy_weights"]),
            max_strategies_per_file = int(d["max_strategies_per_file"]),
        )


@dataclass(frozen=True)
class ValidationConfig:
    assembler_tool:  str
    optimizer_tool:  str
    alive2_tool:     str
    alive2_env_var:  str
    ssa_fix_env_var: str

    @staticmethod
    def from_dict(d: dict) -> "ValidationConfig":
        tools     = d["tools"]
        optional  = d.get("optional_tools", {})
        return ValidationConfig(
            assembler_tool  = str(tools["assembler"]),
            optimizer_tool  = str(tools["optimizer"]),
            alive2_tool     = str(optional.get("alive2", "alive-tv")),
            alive2_env_var  = str(d["alive2_env_var"]),
            ssa_fix_env_var = str(d["ssa_fix_env_var"]),
        )


@dataclass(frozen=True)
class ExecutionTimeouts:
    lli:     int
    compile: int
    link:    int
    run:     int
    emit_ir: int

    @staticmethod
    def from_dict(d: dict) -> "ExecutionTimeouts":
        return ExecutionTimeouts(
            lli     = int(d["lli"]),
            compile = int(d["compile"]),
            link    = int(d["link"]),
            run     = int(d["run"]),
            emit_ir = int(d["emit_ir"]),
        )


@dataclass(frozen=True)
class ExecutionConfig:
    interpreter: str
    compiler:    str
    optimizer:   str
    timeouts:    ExecutionTimeouts
    opt_levels:  List[str]

    @staticmethod
    def from_dict(d: dict) -> "ExecutionConfig":
        return ExecutionConfig(
            interpreter = str(d["tools"]["interpreter"]),
            compiler    = str(d["tools"]["compiler"]),
            optimizer   = str(d["tools"]["optimizer"]),
            timeouts    = ExecutionTimeouts.from_dict(d["timeouts"]),
            opt_levels  = [str(lvl) for lvl in d["opt_levels"]],
        )


@dataclass(frozen=True)
class SeedCorpusConfig:
    filename:     str
    chain_length: int

    @staticmethod
    def from_dict(d: dict) -> "SeedCorpusConfig":
        return SeedCorpusConfig(
            filename     = str(d["filename"]),
            chain_length = int(d["chain_length"]),
        )


@dataclass(frozen=True)
class ChartConfig:
    width:  float
    height: float
    dpi:    int
    colors: List[str]

    @staticmethod
    def from_dict(d: dict, colors: List[str]) -> "ChartConfig":
        return ChartConfig(
            width  = float(d["width"]),
            height = float(d["height"]),
            dpi    = int(d["dpi"]),
            colors = colors,
        )


@dataclass(frozen=True)
class ReportingConfig:
    files:            Dict[str, str]
    chart:            ChartConfig
    max_sample_diffs: int

    @staticmethod
    def from_dict(d: dict) -> "ReportingConfig":
        return ReportingConfig(
            files            = {k: str(v) for k, v in d["files"].items()},
            chart            = ChartConfig.from_dict(d["chart"], d.get("chart_colors", [])),
            max_sample_diffs = int(d["max_sample_diffs"]),
        )


@dataclass(frozen=True)
class DecoratorConfig:
    chain_min:    int
    chain_max:    int
    chain_stride: int

    @staticmethod
    def from_dict(d: dict) -> "DecoratorConfig":
        return DecoratorConfig(
            chain_min    = int(d["chain_min"]),
            chain_max    = int(d["chain_max"]),
            chain_stride = int(d["chain_stride"]),
        )


@dataclass(frozen=True)
class TemplateConfig:
    heavy_bias:  float
    heavy_names: List[str]
    weights:     Dict[str, int]
    decorator:   DecoratorConfig

    @staticmethod
    def from_dict(d: dict) -> "TemplateConfig":
        return TemplateConfig(
            heavy_bias  = float(d["heavy_bias"]),
            heavy_names = [str(n) for n in d["heavy_names"]],
            weights     = {k: int(v) for k, v in d.get("weights", {}).items()},
            decorator   = DecoratorConfig.from_dict(d["decorator"]),
        )


# ---------------------------------------------------------------------------
# Top-level Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    paths:       PathConfig
    generation:  GenerationConfig
    mutation:    MutationConfig
    validation:  ValidationConfig
    execution:   ExecutionConfig
    seed_corpus: SeedCorpusConfig
    reporting:   ReportingConfig
    templates:   TemplateConfig

    @staticmethod
    def from_dict(d: dict) -> "Config":
        return Config(
            paths       = PathConfig.from_dict(d["paths"]),
            generation  = GenerationConfig.from_dict(d["generation"]),
            mutation    = MutationConfig.from_dict(d["mutation"]),
            validation  = ValidationConfig.from_dict(d["validation"]),
            execution   = ExecutionConfig.from_dict(d["execution"]),
            seed_corpus = SeedCorpusConfig.from_dict(d["seed_corpus"]),
            reporting   = ReportingConfig.from_dict(d["reporting"]),
            templates   = TemplateConfig.from_dict(d["templates"]),
        )


# Singleton — every module imports this directly.
cfg: Config = Config.from_dict(RAW)


# ---------------------------------------------------------------------------
# ProjectPaths — resolves relative names from config into absolute Paths
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectPaths:
    root:           Path
    dataset_dir:    Path
    generated_dir:  Path
    mutated_dir:    Path
    valid_dir:      Path
    invalid_dir:    Path
    logs_dir:       Path
    results_dir:    Path
    evaluation_dir: Path
    optimized_dir:  Path
    diffs_dir:      Path

    @staticmethod
    def from_config(config: Config, root: Path) -> "ProjectPaths":
        p = config.paths
        return ProjectPaths(
            root           = root,
            dataset_dir    = root / p.dataset,
            generated_dir  = root / p.generated,
            mutated_dir    = root / p.mutated,
            valid_dir      = root / p.valid,
            invalid_dir    = root / p.invalid,
            logs_dir       = root / p.logs,
            results_dir    = root / p.results,
            evaluation_dir = root / p.evaluation,
            optimized_dir  = root / p.optimized,
            diffs_dir      = root / p.diffs,
        )

    def ensure_dirs(self) -> None:
        """Create all project directories if they do not already exist."""
        for directory in (
            self.dataset_dir,
            self.generated_dir,
            self.mutated_dir,
            self.valid_dir,
            self.invalid_dir,
            self.logs_dir,
            self.results_dir,
            self.evaluation_dir,
            self.optimized_dir,
            self.diffs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
