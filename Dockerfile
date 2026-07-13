# ─────────────────────────────────────────────────────────────────
# Dockerfile — LLVM IR Differential Testing project
#
# Build:  docker build -t cd_project:latest .
# Run:    docker run --rm -it -p 8501:8501 \
#             -v "$(pwd)":/workspace \
#             -e OPENAI_API_KEY="$OPENAI_API_KEY" \
#             cd_project:latest
# ─────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      clang \
      llvm \
      llvm-dev \
 && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────
WORKDIR /workspace

# ── Python dependencies (cached layer) ───────────────────────────
# Copy only the requirements file first so Docker can cache this
# layer and skip reinstalling when only source files change.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Project source ────────────────────────────────────────────────
COPY . .

# Ensure shell scripts are executable
RUN chmod +x run.sh stop.sh

# ── Streamlit port ────────────────────────────────────────────────
EXPOSE 8501

# ── Default command ───────────────────────────────────────────────
# Runs the full pipeline then launches the Streamlit dashboard.
# Override with `docker run ... python3 main.py --help` for custom runs.
CMD ["/bin/bash", "run.sh"]
