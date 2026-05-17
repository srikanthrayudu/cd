from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


@dataclass
class ValidationResult:
    is_valid: bool
    reason: str


def _has_llvm_tools() -> bool:
    return all(shutil.which(tool) for tool in ("llvm-as", "opt"))


def _has_alive2() -> bool:
    return shutil.which("alive-tv") is not None


def _should_fix_ssa() -> bool:
    return os.getenv("SSA_FIX") in {"1", "true", "True"}


def _basic_sanity_check(text: str) -> bool:
    if "define" not in text or "ret" not in text:
        return False
    blocks = re.split(r"\n([a-zA-Z0-9_.]+):\n", "\n" + text)
    if len(blocks) <= 1:
        return True
    for idx in range(2, len(blocks), 2):
        body = blocks[idx]
        if not re.search(r"\b(ret|br)\b", body):
            return False
    return True


def validate_ir(file_path: Path) -> ValidationResult:
    if not file_path.exists():
        return ValidationResult(False, "missing")

    if _has_llvm_tools():
        tmp_bc = file_path.with_suffix(".bc")
        try:
            subprocess.run(
                ["llvm-as", str(file_path), "-o", str(tmp_bc)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["opt", "-verify", str(tmp_bc), "-o", str(tmp_bc)],
                check=True,
                capture_output=True,
                text=True,
            )
            if _should_fix_ssa():
                subprocess.run(
                    ["opt", "-mem2reg", str(tmp_bc), "-o", str(tmp_bc)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            if os.getenv("ALIVE2_VALIDATE") and _has_alive2():
                subprocess.run(
                    ["alive-tv", str(file_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            return ValidationResult(True, "ok")
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else "verify_failed"
            return ValidationResult(False, stderr)
        finally:
            if tmp_bc.exists():
                tmp_bc.unlink()

    # Fallback: light sanity check when LLVM is unavailable.
    text = file_path.read_text(errors="ignore")
    if _basic_sanity_check(text):
        return ValidationResult(True, "tooling_unavailable")
    return ValidationResult(False, "tooling_unavailable")


def validate_directory(input_dir: Path, valid_dir: Path, invalid_dir: Path) -> Tuple[int, int]:
    valid_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir.mkdir(parents=True, exist_ok=True)
    valid_count = 0
    invalid_count = 0
    for file_path in sorted(input_dir.glob("*.ll")):
        result = validate_ir(file_path)
        if result.is_valid:
            file_path.replace(valid_dir / file_path.name)
            valid_count += 1
        else:
            file_path.replace(invalid_dir / file_path.name)
            invalid_count += 1
    return valid_count, invalid_count
