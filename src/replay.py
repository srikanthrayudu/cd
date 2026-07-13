"""
replay.py — Re-execute previously failed IR files.

Reads failure names from ``triage.json`` (or ``diffs.jsonl`` as a fallback),
locates the corresponding *.ll files in *valid_dir*, and re-runs them through
lli + clang so the results can be compared again without re-running the whole
pipeline.

Useful for investigating specific failures interactively.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from src.config import cfg
from src.executor import run_clang, run_lli


@dataclass
class ReplayResult:
    """Aggregated replay result for one IR file."""
    name: str
    path: str
    lli:  dict
    o0:   dict
    o3:   dict


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _iter_failure_names(results_dir: Path) -> Iterable[str]:
    """Yield the names of files that had differential failures."""
    file_names = cfg.reporting.files

    # Prefer the triage.json summary (produced by build_triage)
    triage = _load_json(results_dir / file_names["triage"])
    samples = triage.get("samples", [])
    if samples:
        for row in samples:
            name = row.get("name")
            if name:
                yield name
        return

    # Fall back to reading diffs.jsonl directly
    diffs_path = results_dir / file_names["diffs"]
    if not diffs_path.exists():
        return
    for line in diffs_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = row.get("name")
        if name:
            yield name


def _resolve_ir_path(valid_dir: Path, name: str) -> Optional[Path]:
    """Find the *.ll file for *name* in *valid_dir*."""
    exact = valid_dir / f"{name}.ll"
    if exact.exists():
        return exact
    matches = list(valid_dir.glob(f"{name}*.ll"))
    return matches[0] if matches else None


def replay_failures(
    valid_dir:   Path,
    results_dir: Path,
    limit:       int = 10,
) -> list[ReplayResult]:
    """
    Re-run the failed IR files found in *results_dir* and return a list of
    :class:`ReplayResult` objects.

    Parameters
    ----------
    valid_dir:   directory containing the *.ll files
    results_dir: directory containing triage.json / diffs.jsonl
    limit:       maximum number of files to replay
    """
    seen:    set   = set()
    results: List[ReplayResult] = []

    for name in _iter_failure_names(results_dir):
        if name in seen:
            continue
        seen.add(name)

        ir_path = _resolve_ir_path(valid_dir, name)
        if not ir_path:
            continue

        lli_res  = run_lli(ir_path)
        o0_res   = run_clang(ir_path, cfg.execution.opt_levels[0])
        o3_res   = run_clang(ir_path, cfg.execution.opt_levels[1])

        results.append(ReplayResult(
            name = name,
            path = str(ir_path),
            lli  = lli_res.__dict__,
            o0   = o0_res.__dict__,
            o3   = o3_res.__dict__,
        ))

        if len(results) >= limit:
            break

    return results


def write_replay(results: List[ReplayResult], output_path: Path) -> None:
    """Write *results* as a pretty-printed JSON file."""
    payload = [r.__dict__ for r in results]
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
