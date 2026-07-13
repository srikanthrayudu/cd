#!/usr/bin/env bash
# run.sh — Bootstrap the virtual environment, run the pipeline, then launch the UI.
#
# Usage:
#   ./run.sh                      # template backend, defaults from config.yaml
#   ./run.sh --backend openai     # OpenAI backend (set OPENAI_API_KEY in .env)
#   ./run.sh --gen-count 20       # generate 20 IR files
#
# Any extra arguments are forwarded verbatim to main.py.

set -euo pipefail

VENV_DIR="$(dirname "$0")/.venv"
REQ_FILE="$(dirname "$0")/requirements.txt"
HASH_FILE="${VENV_DIR}/.requirements.hash"

# ── 1. Create virtualenv if absent ──────────────────────────────────────────
if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[run.sh] Creating virtual environment in ${VENV_DIR}/"
    python3 -m venv "${VENV_DIR}"
fi

# ── 2. Activate ─────────────────────────────────────────────────────────────
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

# Repair a partially-created venv missing pip
python3 -m ensurepip --upgrade >/dev/null 2>&1 || true

# ── 3. Install / skip based on requirements hash ────────────────────────────
CURRENT_HASH="$(sha256sum "${REQ_FILE}" | awk '{print $1}')"
if [[ -f "${HASH_FILE}" && "$(cat "${HASH_FILE}")" == "${CURRENT_HASH}" ]]; then
    echo "[run.sh] Dependencies up-to-date, skipping pip install."
else
    echo "[run.sh] Installing dependencies from requirements.txt ..."
    python3 -m pip install --upgrade pip --quiet
    python3 -m pip install -r "${REQ_FILE}" --quiet
    printf '%s' "${CURRENT_HASH}" > "${HASH_FILE}"
fi

# ── 4. Run the pipeline (forward any CLI args) ───────────────────────────────
echo ""
echo "================================================================"
echo " LLVM IR Differential Testing Pipeline"
echo "================================================================"
python3 -u main.py "$@"

# ── 5. Launch Streamlit UI if available ──────────────────────────────────────
echo ""
echo "================================================================"
echo " Streamlit Dashboard"
echo "================================================================"
if python3 -c "import streamlit" 2>/dev/null; then
    python3 -m streamlit run ui_app.py
else
    echo "[run.sh] streamlit not installed — skipping UI."
    echo "         To enable: pip install streamlit  (or re-run run.sh)"
fi
