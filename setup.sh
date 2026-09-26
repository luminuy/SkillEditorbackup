#!/usr/bin/env bash
# One-time setup for the clip studio. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install --quiet -r requirements.txt
mkdir -p input projects assets/music
python3 -m clipstudio doctor
