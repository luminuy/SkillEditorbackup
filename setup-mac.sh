#!/usr/bin/env bash
# macOS setup (Apple Silicon or Intel). Safe to re-run.
#   bash setup-mac.sh           # Homebrew ffmpeg (VideoToolbox, ffprobe) — best, but on older macOS
#                               # Homebrew may compile everything from source (can take hours)
#   bash setup-mac.sh --quick   # no Homebrew: prebuilt ffmpeg from pip (imageio-ffmpeg) — ready in minutes
set -euo pipefail
cd "$(dirname "$0")"

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

if [ "$QUICK" = "0" ]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found — using --quick mode (prebuilt ffmpeg from pip)."
    QUICK=1
  fi
fi

if [ "$QUICK" = "0" ]; then
  # ffmpeg from Homebrew includes libass (Thai captions), VideoToolbox (fast Mac encoding) and ffprobe
  brew list ffmpeg >/dev/null 2>&1 || brew install ffmpeg
  brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
  PY="$(brew --prefix python@3.12)/bin/python3.12"
else
  # any Python 3.9+ works (macOS ships python3 with the Command Line Tools: xcode-select --install)
  PY="$(command -v python3 || true)"
  if [ -z "$PY" ]; then
    echo "python3 not found. Run: xcode-select --install   (or install Python from https://www.python.org/downloads/macos/)"
    exit 1
  fi
  "$PY" -c 'import sys; assert sys.version_info >= (3, 9), "Python 3.9+ required"'
fi

# project-local virtualenv (keeps the system Python clean)
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet faster-whisper pythainlp Pillow numpy
if [ "$QUICK" = "1" ]; then
  python -m pip install --quiet imageio-ffmpeg   # static ffmpeg with libass; no ffprobe (engine has a fallback)
fi
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
