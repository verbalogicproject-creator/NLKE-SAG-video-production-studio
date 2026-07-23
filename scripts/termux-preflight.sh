#!/data/data/com.termux/files/usr/bin/sh
set -eu

missing=""
for command in node npm python postgres psql initdb pg_ctl ffmpeg ffprobe; do
  if ! command -v "$command" >/dev/null 2>&1; then
    missing="$missing $command"
  fi
done

if [ -n "$missing" ]; then
  echo "missing required commands:$missing" >&2
  exit 1
fi

ffmpeg -hide_banner -filters 2>/dev/null | grep -q drawtext || { echo "FFmpeg drawtext filter is required" >&2; exit 1; }
ffmpeg -hide_banner -filters 2>/dev/null | grep -q subtitles || { echo "FFmpeg subtitles/libass filter is required" >&2; exit 1; }

if ! command -v pnpm >/dev/null 2>&1; then
  echo "warning: pnpm 9.12 is missing; install with: npm install -g pnpm@9.12.0" >&2
fi

if ! command -v whisper-cli >/dev/null 2>&1 && [ -z "${SAG_VIDEO_TRANSCRIPTION_BASE_URL:-}" ]; then
  echo "warning: configure remote transcription or install whisper.cpp before analysis" >&2
fi

echo "Termux preflight passed: $(uname -m), Node $(node -v), Python $(python --version 2>&1)"
