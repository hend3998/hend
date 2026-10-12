#!/usr/bin/env bash
# Replace the guide voice with a real Gulf female recording.
# Usage: ./add-voiceover.sh vo.wav
#   vo.wav = one 20s take, lines placed at: 0.4s / 9.55s / 10.35s / 11.1s / 11.95s / 13.05s / 16.4s
#   (same timing as stems/voiceover-guide.wav — record over it or line up against it).
# The music ducks automatically under the voice (sidechain).
set -euo pipefail
cd "$(dirname "$0")"
VO="$1"
ffmpeg -y -i stems/video-no-audio.mp4 -i stems/music-full.wav -i stems/sfx.wav -i "$VO" \
  -filter_complex "[3:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=1.5,asplit=2[v][key];[1:a]volume=0.85[m];[m][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=250[md];[2:a]volume=0.7[s];[md][s][v]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 320k -t 20 -movflags +faststart ibtikar-ad-20s-with-vo.mp4
echo "done: ibtikar-ad-20s-with-vo.mp4"
