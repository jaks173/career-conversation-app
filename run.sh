#!/usr/bin/env bash
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then
  echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
source .venv/bin/activate
python app.py
