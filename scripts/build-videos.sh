#!/usr/bin/env bash
# Turn the raw Playwright recordings into the finished videos.
#
#   ./scripts/build-videos.sh
#
# Two jobs:
#   1. side-by-side pairs (the two-window recordings) become one video, A on the
#      left and B on the right, so live messaging is visible in a single file.
#   2. everything becomes .mp4 (H.264). Playwright records VP8 in .webm, which
#      QuickTime and half the world will not open.
#
# ffmpeg runs in a container: the host has none, and the copy bundled with
# Playwright is stripped down to `scale` and VP8 — no hstack, no libx264.
#
# Input:  frontend/videos-raw/*.webm   (written by the recordings)
# Output: videos/*.mp4

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW="$ROOT/frontend/videos-raw"
OUT="$ROOT/videos"
FFMPEG_IMAGE="${FFMPEG_IMAGE:-jrottenberg/ffmpeg:7-ubuntu}"

# Half-width each: 2 x 960 = 1920, which is a sane size to actually watch.
PANE_W=960
PANE_H=600
FPS=25
CRF=23

[ -d "$RAW" ] || { echo "no $RAW — run the recordings first:"; echo "  docker compose exec -T frontend npx playwright test -c playwright.videos.config.ts"; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"

ff() {
  docker run --rm -v "$RAW:/raw:ro" -v "$OUT:/out" "$FFMPEG_IMAGE" "$@"
}

# VP8 in, H.264 out, dimensions rounded to even numbers (H.264 requires it).
to_mp4() {
  ff -hide_banner -loglevel error -y -i "/raw/$1" \
    -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=$FPS" \
    -c:v libx264 -preset slow -crf "$CRF" -pix_fmt yuv420p \
    -movflags +faststart "/out/${1%.webm}.mp4"
}

# A on the left, B on the right.
#
# tpad clones the last frame of each input before stacking: the two recordings do
# not stop at the same millisecond, and without the pad hstack either truncates
# the shorter side or holds a stale frame.
side_by_side() {
  local base="$1"
  ff -hide_banner -loglevel error -y \
    -i "/raw/${base}__A.webm" -i "/raw/${base}__B.webm" \
    -filter_complex "\
      [0:v]scale=${PANE_W}:${PANE_H}:force_original_aspect_ratio=decrease,\
pad=${PANE_W}:${PANE_H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=${FPS},tpad=stop_mode=clone:stop_duration=3[a];\
      [1:v]scale=${PANE_W}:${PANE_H}:force_original_aspect_ratio=decrease,\
pad=${PANE_W}:${PANE_H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=${FPS},tpad=stop_mode=clone:stop_duration=3[b];\
      [a][b]hstack=inputs=2[v]" \
    -map "[v]" -shortest \
    -c:v libx264 -preset slow -crf "$CRF" -pix_fmt yuv420p \
    -movflags +faststart "/out/${base}-side-by-side.mp4"
}

made=0
for f in "$RAW"/*.webm; do
  name="$(basename "$f")"

  # Playwright's own per-context hashes, and the recorder smoke test.
  case "$name" in
    page@*|00-smoke*) continue ;;
  esac

  base="${name%__A.webm}"
  if [ "$name" != "$base" ] && [ -f "$RAW/${base}__B.webm" ]; then
    side_by_side "$base"
    made=$((made + 1))
    echo "  side-by-side  ${base}"
  elif [[ "$name" == *__[AB].webm ]]; then
    continue # half a pair with no partner
  else
    to_mp4 "$name"
    made=$((made + 1))
    echo "  single        ${name%.webm}"
  fi
done

echo
echo "$made videos in $OUT"
ls -1sh "$OUT"