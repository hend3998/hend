"""Build a GUIDE voice-over track with espeak-ng (offline) and mix it into the ad.

This is a timing/guide track, not a studio voice: replace it with a real Gulf female recording
using output/add-voiceover.sh when available.

Usage: python3 voiceover.py OUTPUT_DIR WORK_DIR
"""
import os
import subprocess
import sys

OUT, WORK = sys.argv[1], sys.argv[2]
os.makedirs(WORK, exist_ok=True)

# (text with diacritics for correct pronunciation, start s, max duration s)
LINES = [
    ("تَخَيَّلِي شِنُو نِقْدَرْ نْسَوِّي فِيه!", 0.4, 2.2),
    ("صَارُوخْ؟", 9.55, 0.75),
    ("قَلْعَة؟", 10.35, 0.7),
    ("أَوْ دَيْنَاصُورْ؟", 11.1, 0.85),
    ("خَلِّ الْخَيَالْ يِخْتَارْ!", 11.95, 1.0),
    ("مُتْعَة يِصْنَعُونْهَا بْإِيدْهُمْ!", 13.05, 1.9),
    ("اِبْدَؤُوا مُغَامَرَةَ الْإِبْدَاعْ مَعَ ابْتِكَارْ!", 16.4, 3.0),
]


def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode())


parts = []
for i, (txt, start, maxd) in enumerate(LINES):
    raw = f"{WORK}/l{i}.wav"
    subprocess.run(["espeak-ng", "-v", "ar+f4", "-s", "165", "-p", "68", "-a", "180", "-w", raw, txt], check=True)
    d = dur(raw)
    tempo = max(1.0, d / maxd)
    fx = f"aresample=48000,atempo={min(2.0, tempo):.3f},highpass=f=120,equalizer=f=3000:t=q:w=1:g=3,acompressor=threshold=-18dB:ratio=3:attack=5:release=80"
    seg = f"{WORK}/s{i}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", fx, "-ac", "1", seg], check=True)
    parts.append((seg, start))
    print(f"line {i}: {d:.2f}s -> tempo {tempo:.2f}")

# place lines on a 20s timeline
inputs, labels, filt = [], [], []
for i, (seg, start) in enumerate(parts):
    inputs += ["-i", seg]
    ms = int(start * 1000)
    filt.append(f"[{i}:a]adelay={ms}|{ms}[d{i}]")
    labels.append(f"[d{i}]")
filt.append("".join(labels) + f"amix=inputs={len(parts)}:normalize=0,apad,atrim=0:20[vo]")
vo = f"{OUT}/stems/voiceover-guide.wav"
subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[vo]", "-ar", "48000", "-ac", "1", vo], check=True)

# mix: music ducks under the voice (sidechain), then loudness-normalise for social platforms
mix = (
    "[3:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=1.5,asplit=2[v][key];"
    "[1:a]volume=0.85[m];"
    "[m][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=250[md];"
    "[2:a]volume=0.7[s];"
    "[md][s][v]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
)
subprocess.run([
    "ffmpeg", "-v", "error", "-y", "-i", f"{OUT}/stems/video-no-audio.mp4", "-i", f"{OUT}/stems/music-full.wav",
    "-i", f"{OUT}/stems/sfx.wav", "-i", vo, "-filter_complex", mix, "-map", "0:v", "-map", "[a]",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-t", "20", "-movflags", "+faststart",
    f"{OUT}/ibtikar-ad-20s-guide-vo.mp4"], check=True)
print("ok")
