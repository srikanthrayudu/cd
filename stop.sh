#!/usr/bin/env bash
# stop.sh — Stop any running pipeline or dashboard processes.

set -euo pipefail

echo "Stopping pipeline (main.py) ..."
pkill -f "python3.*main\.py"     2>/dev/null && echo "  stopped." || echo "  none running."

echo "Stopping Streamlit dashboard (ui_app.py) ..."
pkill -f "streamlit run ui_app"  2>/dev/null && echo "  stopped." || echo "  none running."

echo "Done."
