#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAMPLES_DIR="$ROOT_DIR/dataset/samples"
OUT_DIR="$ROOT_DIR/dataset/external_ir"

mkdir -p "$OUT_DIR"

if ! command -v clang >/dev/null 2>&1; then
  echo "clang not found; skipping IR generation."
  exit 0
fi

for src in "$SAMPLES_DIR"/*.c; do
  base="$(basename "$src" .c)"
  clang -S -emit-llvm "$src" -O0 -o "$OUT_DIR/$base.ll"
  echo "generated $OUT_DIR/$base.ll"
done

