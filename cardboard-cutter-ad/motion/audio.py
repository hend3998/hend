"""Synthesize the 20s music bed + SFX (48 kHz). Writes music.wav, music_ducked.wav, sfx.wav into OUT_DIR.

Usage: python3 audio.py OUT_DIR
"""
import sys
import wave

import numpy as np

SR = 48000
DUR = 20.0
N = int(SR * DUR)
rng = np.random.RandomState(5)
OUT = sys.argv[1]

# voice-over windows (seconds) where the music ducks
VO = [(0.4, 2.6), (7.3, 11.6), (12.8, 14.9), (16.4, 19.4)]


def t_(d):
    return np.arange(int(SR * d)) / SR


def add(buf, sig, at, gain=1.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    buf[i:i + len(sig)] += sig * gain


def bandpass(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))


def env(n, a=0.005, d=0.3):
    t = np.arange(n) / SR
    return np.minimum(1, t / a) * np.exp(-t / d)


def note(name):
    names = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    return 440.0 * 2 ** ((names[name[0]] + 12 * (int(name[-1]) - 4)) / 12.0)


_pl = {}


def pluck(freq, dur=0.9):
    key = round(freq, 2)
    if key not in _pl:
        n = int(SR * dur)
        p = int(SR / freq)
        buf = rng.uniform(-1, 1, p)
        out = np.zeros(n)
        for i in range(n):
            v = buf[i % p]
            out[i] = v
            buf[i % p] = 0.5 * (v + buf[(i + 1) % p]) * 0.996
        out *= np.exp(-np.arange(n) / SR / 0.5)
        _pl[key] = out / (np.abs(out).max() + 1e-9)
    return _pl[key]


def glock(freq, dur=0.7):
    t = t_(dur)
    s = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t / 0.08)
    return s * env(len(t), 0.002, 0.25)


def sine_sweep(f0, f1, dur, decay=0.2):
    t = t_(dur)
    f = f0 + (f1 - f0) * (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(len(t), 0.003, decay)


# ---------------- music ----------------
music = np.zeros(N)
BEAT = 0.5
chords = [
    (["G4", "C4", "E4", "C5"], "C3", ["E5", "G5", "C6", "G5"]),
    (["G4", "D4", "G4", "B4"], "G2", ["D5", "G5", "B5", "G5"]),
    (["A4", "C4", "E4", "A4"], "A2", ["C6", "A5", "E5", "A5"]),
    (["A4", "C4", "F4", "A4"], "F2", ["F5", "A5", "C6", "A5"]),
]
strum = [(0.0, 1.0), (1.0, 0.9), (1.5, 0.6), (2.5, 0.6), (3.0, 0.9), (3.5, 0.6)]
for bar in range(10):
    t0 = bar * 2.0
    uke, bass, mel = chords[bar % 4]
    if bar == 9:
        uke, bass, mel = chords[0]
    for beat, g in strum:
        at = t0 + beat * BEAT
        if at >= 19.5:
            continue
        for si, n in enumerate(uke):
            add(music, pluck(note(n)), at + si * 0.012, 0.16 * g)
    for b in (0, 2):
        at = t0 + b * BEAT
        if at < 19.5:
            tt = t_(0.45)
            add(music, np.sin(2 * np.pi * note(bass) * tt) * env(len(tt), 0.01, 0.3), at, 0.33)
    if t0 >= 3.0:
        for b in (1, 3):  # claps
            at = t0 + b * BEAT
            if at < 19.5:
                add(music, bandpass(rng.randn(int(0.09 * SR)), 900, 4000) * env(int(0.09 * SR), 0.001, 0.03), at, 0.5)
        for b in (0, 2):  # soft kick
            at = t0 + b * BEAT
            if at < 19.5:
                add(music, sine_sweep(140, 45, 0.25, 0.12), at, 0.45)
    for i, n in enumerate(mel):  # glockenspiel motif on the off-beats
        at = t0 + (i * 2 + 1) * BEAT / 2 + (0.0 if bar % 2 == 0 else BEAT / 2)
        if at < 19.5:
            add(music, glock(note(n)), at, 0.12)
# final hit at 19.5
for si, n in enumerate(["C4", "E4", "G4", "C5"]):
    add(music, pluck(note(n), 0.5), 19.5 + si * 0.01, 0.22)
add(music, glock(note("C6"), 0.5), 19.5, 0.25)
add(music, np.sin(2 * np.pi * note("C3") * t_(0.5)) * env(int(0.5 * SR), 0.005, 0.18), 19.5, 0.4)
add(music, bandpass(rng.randn(int(0.5 * SR)), 3000, 12000) * env(int(0.5 * SR), 0.002, 0.12), 19.5, 0.25)

# fades: tiny fade-in, silence tail after the hit settles
fade = np.ones(N)
fade[: int(0.02 * SR)] = np.linspace(0, 1, int(0.02 * SR))
tail = int(19.85 * SR)
fade[tail:] = np.linspace(1, 0, N - tail)
music *= fade

# ducking curve for VO
duck = np.ones(N)
for a, b in VO:
    duck[int(a * SR):int(b * SR)] = 0.0
k = int(0.15 * SR)
duck = np.convolve(duck, np.ones(k) / k, mode="same")
duck = 0.33 + 0.67 * duck  # about -9.6 dB under the voice
music_ducked = music * duck

# ---------------- sfx ----------------
sfx = np.zeros(N)
# boing when the cardboard looks over (~1.5s) and pop when its eyes open (~1.9s)
tt = t_(0.5)
f = 260 + 140 * np.sin(2 * np.pi * 11 * tt) * np.exp(-tt * 5) + 200 * tt
add(sfx, np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(tt), 0.005, 0.25), 1.5, 0.5)
add(sfx, sine_sweep(500, 1300, 0.09, 0.06), 1.9, 0.5)
# whooshes into each transition
for at in (2.8, 6.8, 11.8, 15.8):
    n = int(0.35 * SR)
    w = bandpass(rng.randn(n), 500, 6000) * np.sin(np.linspace(0, np.pi, n)) ** 2
    add(sfx, w, at, 0.35)
# ticks for each word in scene 2
for at in (3.3, 4.6, 5.8):
    add(sfx, glock(2093, 0.15), at, 0.35)
# power-on blip (blue ring lights up)
add(sfx, sine_sweep(600, 900, 0.12, 0.08), 3.45, 0.25)
add(sfx, sine_sweep(900, 1350, 0.12, 0.08), 3.57, 0.25)
# soft cutting hum during the cut trace (5.45 - 6.45)
n = int(1.0 * SR)
tt = t_(1.0)
hum = 0.6 * np.sin(2 * np.pi * 150 * tt) + 0.3 * np.sin(2 * np.pi * 300 * tt) + 0.4 * bandpass(rng.randn(n), 1500, 5000)
hum *= np.minimum(1, tt / 0.12) * np.minimum(1, (1.0 - tt) / 0.15)
add(sfx, hum, 5.45, 0.09)
# lift pop + sparkle
add(sfx, sine_sweep(400, 1000, 0.1, 0.07), 6.47, 0.45)


def glitter(at, gain=0.25):
    for i in range(9):
        add(sfx, glock(rng.uniform(2200, 5200), 0.3), at + i * 0.035, gain * (1 - i / 12))


glitter(6.5)
# flat-lay plops
for i, at in enumerate((7.0, 7.07, 7.13, 7.2, 7.27, 7.33)):
    add(sfx, sine_sweep(700 + 60 * i, 250, 0.07, 0.04), at, 0.25)
# assembly snap + rivet pops
add(sfx, bandpass(rng.randn(int(0.04 * SR)), 1500, 8000) * env(int(0.04 * SR), 0.001, 0.01), 8.2, 0.9)
add(sfx, sine_sweep(900, 400, 0.06, 0.04), 8.37, 0.35)
add(sfx, sine_sweep(1000, 450, 0.06, 0.04), 8.53, 0.35)
# marker scribble 8.85 - 9.55
n = int(0.7 * SR)
tt = t_(0.7)
scr = bandpass(rng.randn(n), 2500, 9000) * (0.5 + 0.5 * np.sin(2 * np.pi * 9 * tt)) * np.minimum(1, (0.7 - tt) / 0.1)
add(sfx, scr, 8.85, 0.18)
# reveal sparkles + rocket puff
for at in (9.6, 10.4, 11.2):
    glitter(at, 0.28)
n = int(0.3 * SR)
add(sfx, bandpass(rng.randn(n), 200, 1500) * np.sin(np.linspace(0, np.pi, n)), 9.75, 0.35)
# dino "roar" (tiny, cute)
add(sfx, sine_sweep(420, 300, 0.25, 0.2) * 0.8, 11.3, 0.25)
# wink ting
add(sfx, glock(1568, 0.6), 14.0, 0.4)
add(sfx, glock(2349, 0.6), 14.06, 0.3)
# end card pop-in
add(sfx, sine_sweep(500, 1100, 0.1, 0.08), 18.0, 0.3)


def write(name, x):
    x = np.clip(x, -1, 1)
    st = np.repeat((x * 32767).astype(np.int16)[:, None], 2, axis=1)
    with wave.open(f"{OUT}/{name}", "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())


peak = max(np.abs(music).max(), 1e-9)
write("music.wav", music / peak * 0.6)
write("music_ducked.wav", music_ducked / peak * 0.6)
write("sfx.wav", sfx / max(np.abs(sfx).max(), 1e-9) * 0.6)
print("ok")
