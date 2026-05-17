#!/bin/bash

echo "=========================================================="
echo " Stopping LLVM IR Differential Testing Pipeline and UI... "
echo "=========================================================="

# Kill any main.py processes
pkill -f "python3 -u main.py" || echo "No main.py processes running."

# Kill any streamlit processes for ui_app.py
pkill -f "streamlit run ui_app.py" || echo "No Streamlit UI processes running."

echo "All related processes have been stopped."

