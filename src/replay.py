from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from src.executor import run_clang, run_lli


@dataclass
class ReplayResult:
    name: str
    path: str
    lli: dict
    o0: dict
    o3: dict


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _iter_failure_names(results_dir: Path) -> Iterable[str]:
    triage = _load_json(results_dir / "triage.json")
    samples = triage.get("samples", [])
    if samples:
        for row in samples:
            name = row.get("name")
            if name:
                yield name
        return
    diffs_path = results_dir / "diffs.jsonl"
    if not diffs_path.exists():
        return
    for line in diffs_path.read_text().splitlines():
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
    candidate = valid_dir / f"{name}.ll"
    if candidate.exists():
        return candidate
    matches = list(valid_dir.glob(f"{name}*.ll"))
    return matches[0] if matches else None


def replay_failures(valid_dir: Path, results_dir: Path, limit: int = 10) -> List[ReplayResult]:
    seen = set()
    results: List[ReplayResult] = []
    for name in _iter_failure_names(results_dir):
        if name in seen:
            continue
        seen.add(name)
        path = _resolve_ir_path(valid_dir, name)
        if not path:
            continue
        lli_res = run_lli(path)
        o0_res = run_clang(path, "O0")
        o3_res = run_clang(path, "O3")
        results.append(
            ReplayResult(
                name=name,
                path=str(path),
                lli=lli_res.__dict__,
                o0=o0_res.__dict__,
                o3=o3_res.__dict__,
            )
        )
        if len(results) >= limit:
            break
    return results


def write_replay(results: List[ReplayResult], output_path: Path) -> None:
    payload = [result.__dict__ for result in results]
    output_path.write_text(json.dumps(payload, indent=2) + "\n")

