#!/bin/bash
set -euo pipefail

# Create virtualenv if missing
if [[ ! -d ".venv" ]]; then
	echo "Creating virtualenv in .venv"
	python3 -m venv .venv
fi

# Activate virtualenv
# shellcheck source=/dev/null
source .venv/bin/activate

REQ_HASH_FILE=".venv/.requirements.hash"
CURRENT_REQ_HASH="$(sha256sum requirements.txt | awk '{print $1}')"

# Repair a partially created virtualenv that is missing pip.
python3 -m ensurepip --upgrade >/dev/null 2>&1 || true

if [[ -f "$REQ_HASH_FILE" ]] && [[ "$(cat "$REQ_HASH_FILE")" == "$CURRENT_REQ_HASH" ]]; then
	echo "Dependencies are already installed; skipping pip install."
else
	python3 -m pip install --upgrade pip
	python3 -m pip install -r requirements.txt
	printf '%s' "$CURRENT_REQ_HASH" > "$REQ_HASH_FILE"
fi

# Optional: Set up your LLM credentials if running in 'openai' backend.
# export OPENAI_API_KEY="your-api-key"

echo "=========================================================="
echo " Starting LLVM IR Differential Testing Pipeline (Backend) "
echo "=========================================================="
# By default, use the local "template" backend to avoid hitting API failures.
# If you want to use genuine LLM synthesis, run with --backend openai and set OPENAI_API_KEY.
python3 -u main.py --backend template

echo ""
echo "=========================================================="
echo " Starting Streamlit UI Dashboard (if installed) "
echo "=========================================================="
# Only run the Streamlit UI if streamlit is available in the environment
if python3 - <<'PY'
import sys
try:
	import streamlit
except Exception:
	sys.exit(2)
sys.exit(0)
PY
then
	python3 -m streamlit run ui_app.py
else
	echo "streamlit not installed in .venv; skipping UI launch. To run the dashboard, install streamlit:"
	echo "  . .venv/bin/activate && pip install streamlit"
fi
