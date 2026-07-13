"""
ui_app.py — Streamlit entry point for the LLVM IR Differential Testing dashboard.

Launch with:
    streamlit run ui_app.py

Or use run.sh which handles venv activation and dependency installation first.
"""
from src.ui_dashboard import run_dashboard

run_dashboard()
