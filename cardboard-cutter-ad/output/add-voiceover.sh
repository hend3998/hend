#!/usr/bin/env bash
# Add the recorded Gulf female voice-over to the ad.
# Usage: ./add-voiceover.sh vo.wav   (one take, 20s long, lines placed at the times in the package:
#        0.4s / 7.3s / 12.8s / 16.4s). The music stem is already ducked under those windows.
set -euo pipefail
cd "$(dirname "$0")"
VO="$1"
ffmpeg -y -i stems/video-no-audio.mp4 -i stems/music-ducked-for-vo.wav -i stems/sfx.wav -i "$VO" \
  -filter_complex "[1:a]volume=0.85[m];[2:a]volume=0.75[s];[3:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=1.6[v];[m][s][v]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 320k -t 20 -movflags +faststart ibtikar-ad-20s-with-vo.mp4
echo "done: ibtikar-ad-20s-with-vo.mp4"
