#!/usr/bin/env bash
# Installs engine dependencies in Claude Code on the web / fresh containers.
set -uo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}"
python3 -c "import imageio_ffmpeg, faster_whisper, pythainlp, PIL" 2>/dev/null && exit 0
python3 -m pip install --quiet -r requirements.txt >/dev/null 2>&1 || echo "clipstudio: pip install failed — run: bash setup.sh"
exit 0
