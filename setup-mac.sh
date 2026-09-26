#!/usr/bin/env bash
# macOS setup (Apple Silicon or Intel). Safe to re-run.
#   bash setup-mac.sh
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required: https://brew.sh  (then re-run this script)"; exit 1
fi
# ffmpeg from Homebrew includes libass (Thai captions), VideoToolbox (fast Mac encoding) and ffprobe
brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
PY="$(brew --prefix python@3.12)/bin/python3.12"

# project-local virtualenv (keeps the system Python clean)
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet faster-whisper pythainlp Pillow numpy
if [ "$(uname -m)" = "arm64" ]; then
  python -m pip install --quiet mlx-whisper || echo "mlx-whisper failed to install — faster-whisper (CPU) will be used"
fi

# Kanit fonts for CapCut / Final Cut / Resolve titles
mkdir -p "$HOME/Library/Fonts"
cp -n assets/fonts/Kanit-*.ttf "$HOME/Library/Fonts/" 2>/dev/null || true

mkdir -p input projects assets/music
python -m clipstudio sfx >/dev/null
python -m clipstudio doctor
echo
echo "Done. Every new terminal:  source .venv/bin/activate"
