#!/usr/bin/env sh
set -eu

# Deterministic, offline template render for the repo-to-video acceptance
# story. Provider-generated scenes can replace these inputs without changing
# the timeline/export contract.
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
OUT="$ROOT/examples/repo-to-video/sag-video-repo-to-video-template.mp4"
mkdir -p "$(dirname "$OUT")"
FONT=${SAG_VIDEO_FONT:-/system/fonts/Roboto-Regular.ttf}
[ -f "$FONT" ] || FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf

ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "color=c=0x10182b:s=1280x720:r=30:d=10" \
  -f lavfi -i "color=c=0x17213a:s=1280x720:r=30:d=10" \
  -f lavfi -i "color=c=0x243b53:s=1280x720:r=30:d=10" \
  -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=30" \
  -filter_complex "[0:v]drawtext=fontfile='$FONT':text='SAG VIDEO':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=250,drawtext=fontfile='$FONT':text='Repository to Video':fontcolor=0x7dd3fc:fontsize=42:x=(w-text_w)/2:y=350[v0];[1:v]drawtext=fontfile='$FONT':text='Evidence  ->  Storyboard  ->  Verified Media':fontcolor=white:fontsize=42:x=(w-text_w)/2:y=300[v1];[2:v]drawtext=fontfile='$FONT':text='Human approval. Canonical timeline. Publish.':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=300[v2];[v0][v1][v2]concat=n=3:v=1:a=0,format=yuv420p[v]" \
  -map "[v]" -map 3:a -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 128k -shortest "$OUT"

echo "$OUT"
