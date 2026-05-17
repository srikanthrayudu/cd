# Setup Guide

This prototype uses Python 3.9+ and optionally LLVM tools.

## Python

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Optional OpenAI backend

You can place your key in a local `.env` file (see `.env.example`).

```bash
cp .env.example .env
```

## Optional LLVM tools

If you have LLVM installed, the pipeline can validate and execute IR (llvm-as, opt, lli, clang).

```bash
sudo apt update
sudo apt install -y llvm clang
```
