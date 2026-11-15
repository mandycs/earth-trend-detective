#!/usr/bin/env bash
# One-command render of the 29.5 s submission video.
#   ./render.sh                          -> renders/alibi-30s-nomusic.mp4, or -music.mp4 if assets/music/track.mp3 exists
#   LIVE_URL=https://example.org ./render.sh
#   NOMUSIC=1 ./render.sh                -> force the no-music version even if the track exists
set -euo pipefail
cd "$(dirname "$0")"
TOTAL=29.5
LIVE_URL="${LIVE_URL:-[LIVE_URL]}"
TRACK=assets/music/track.mp3
CUT=assets/music/track-cut.mp3

if [[ -f "$TRACK" && "${NOMUSIC:-0}" != "1" ]]; then
  # 29.5 s, 40 ms fade-in, 1.8 s fade-out, loudness -16 LUFS (submission spec)
  ffmpeg -y -loglevel error -i "$TRACK" -t "$TOTAL" \
    -af "afade=t=in:d=0.04,afade=t=out:st=27.7:d=1.8,loudnorm=I=-16:TP=-1.5:LRA=11" \
    -ar 48000 -c:a libmp3lame -b:a 256k "$CUT"
  python3 build.py --music "$CUT" --live-url "$LIVE_URL"
  OUT=renders/alibi-30s-music.mp4
else
  python3 build.py --live-url "$LIVE_URL"
  OUT=renders/alibi-30s-nomusic.mp4
fi

mkdir -p renders
npx --yes hyperframes@0.9.47 render . -o "$OUT" --fps 30 -q high
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")
echo "rendered $OUT  duration=${D}s"
awk -v d="$D" 'BEGIN { exit !(d <= 29.6) }' || { echo "ERROR: $OUT is longer than 29.6 s" >&2; exit 1; }
