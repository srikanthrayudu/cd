FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies (LLVM/Clang + helpers)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates curl git wget ca-certificates \
       clang llvm llvm-dev pkg-config gnupg lsb-release coreutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy project files
COPY . /workspace

# Create a virtualenv and install Python requirements
RUN python3 -m venv .venv \
    && . .venv/bin/activate \
    && python -m pip install --upgrade pip setuptools wheel \
    && if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# Ensure scripts are executable
RUN chmod +x ./run.sh || true

EXPOSE 8501

# Default: run the project's run.sh which launches the pipeline and (optionally) the UI
ENTRYPOINT ["/bin/bash","-lc","source .venv/bin/activate && ./run.sh"]

