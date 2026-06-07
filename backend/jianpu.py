"""
數字簡譜合成 — 從舊版 app.py 移植的核心邏輯
輸入數字簡譜 + 和弦進行 → 合成 WAV 音頻
"""
import numpy as np
import soundfile as sf
import tempfile
import os
from scipy.signal import butter, sosfilt, lfilter

_RNG = np.random.default_rng(42)

MELODY_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

MELODY_KEY_ROOTS = {
    "C": 60, "C#": 61, "D": 62, "D#": 63, "E": 64,
    "F": 65, "F#": 66, "G": 67, "G#": 68, "A": 69, "A#": 70, "B": 71,
}

JIANPU_INTERVALS = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "7": 11}

TIMBRE_CUTOFF = {
    "鋼琴": 8000.0, "吉他": 6000.0, "長笛": 9000.0,
    "管風琴": 7000.0, "豎琴": 8000.0, "小提琴": 8500.0,
}

_LOWPASS_SOS = butter(4, 8000.0 / (44100 / 2), btype="low", output="sos")

# ── 和弦解析 ──────────────────────────────────────────────────────────────────

_CHORD_ROOTS = [
    ("C#", 1), ("Db", 1), ("D#", 3), ("Eb", 3), ("F#", 6), ("Gb", 6),
    ("G#", 8), ("Ab", 8), ("A#", 10), ("Bb", 10),
    ("C", 0), ("D", 2), ("E", 4), ("F", 5), ("G", 7), ("A", 9), ("B", 11),
]

_CHORD_QUALITIES: dict[str, list[int]] = {
    "maj7": [0, 4, 7, 11], "maj9": [0, 4, 7, 11, 14],
    "M7":   [0, 4, 7, 11],
    "m7b5": [0, 3, 6, 10], "ø":    [0, 3, 6, 10],
    "add9": [0, 4, 7, 14], "add2": [0, 2, 4, 7],
    "sus4": [0, 5, 7],     "sus2": [0, 2, 7], "sus": [0, 5, 7],
    "dim7": [0, 3, 6, 9],  "dim":  [0, 3, 6],
    "aug":  [0, 4, 8],
    "m7":   [0, 3, 7, 10], "m9":  [0, 3, 7, 10, 14],
    "7":    [0, 4, 7, 10], "9":   [0, 4, 7, 10, 14],
    "2":    [0, 2, 4, 7],  "²":   [0, 2, 4, 7],
    "m":    [0, 3, 7],
    "":     [0, 4, 7],
}


def _parse_chord_token(tok: str) -> list[int] | None:
    tok = tok.split("/")[0]
    root_semi = None
    quality_str = tok
    for name, semi in _CHORD_ROOTS:
        if tok.startswith(name):
            root_semi = semi
            quality_str = tok[len(name):]
            break
    if root_semi is None:
        return None
    intervals = _CHORD_QUALITIES.get(quality_str, _CHORD_QUALITIES[""])
    bass = 48 + root_semi
    upper = [60 + root_semi + iv for iv in intervals]
    upper = [n - 12 if n > 76 else n for n in upper]
    return [bass] + upper


def get_diatonic_chords(key: str) -> list[str]:
    """回傳某調的自然音階和弦，格式如 ['G', 'Am', 'Bm', 'C', 'D', 'Em', 'F#dim']"""
    root = MELODY_KEY_ROOTS.get(key, 67) - 60  # relative to C
    # Major scale intervals: W W H W W W H
    scale = [(root + s) % 12 for s in [0, 2, 4, 5, 7, 9, 11]]
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    qualities = ["", "m", "m", "", "", "m", "dim"]
    return [note_names[s] + qualities[i] for i, s in enumerate(scale)]


# ── 音色合成 ──────────────────────────────────────────────────────────────────

def _tone_piano(freq, duration, sr, rng):
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    detune = 1.0 + rng.uniform(-0.002, 0.002)
    f = freq * detune
    t = np.linspace(0, duration, n, endpoint=False)
    harmonics = [(1, 1.0, 3.0), (2, 0.60, 5.0), (3, 0.25, 8.0), (4, 0.10, 12.0), (5, 0.04, 18.0)]
    wave = np.zeros(n, dtype=np.float64)
    for h, amp, decay_rate in harmonics:
        wave += amp * np.sin(2 * np.pi * f * h * t) * np.exp(-decay_rate * np.linspace(0, 1, n))
    env = np.ones(n, dtype=np.float32)
    atk = min(int(0.006 * sr), n)
    env[:atk] *= np.linspace(0, 1, atk) ** 0.5
    fade = min(int(0.015 * sr), n)
    env[n - fade:] *= np.linspace(1, 0, fade)
    return (wave * env * 0.38 * rng.uniform(0.88, 1.12)).astype(np.float32)


def _tone_guitar(freq, duration, sr, rng):
    period = max(2, int(sr / freq))
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    t_imp = np.linspace(0, 1, period)
    impulse = rng.uniform(-1.0, 1.0, period) * 0.6 + (2 * (t_imp % 1.0) - 1) * 0.4
    x = np.zeros(n, dtype=np.float64)
    x[:period] = impulse
    coeff = rng.uniform(0.996, 0.999)
    a = np.zeros(period + 2)
    a[0] = 1.0; a[period] = -coeff * 0.5; a[period + 1] = -coeff * 0.5
    out = lfilter([1.0], a, x)
    out *= np.exp(-0.8 * np.linspace(0, 1, n))
    fade = min(int(0.02 * sr), n)
    out[n - fade:] *= np.linspace(1, 0, fade)
    return (out * 0.70 * rng.uniform(0.85, 1.15)).astype(np.float32)


def _tone_organ(freq, duration, sr, rng):
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0, duration, n, endpoint=False)
    drawbars = [(1, 0.8), (2, 0.6), (3, 0.4), (4, 0.3), (6, 0.2), (8, 0.15)]
    wave = sum(amp * np.sin(2 * np.pi * freq * h * t) for h, amp in drawbars)
    env = np.ones(n, dtype=np.float32)
    atk = min(int(0.008 * sr), n)
    env[:atk] *= np.linspace(0, 1, atk)
    fade = min(int(0.015 * sr), n)
    env[n - fade:] *= np.linspace(1, 0, fade)
    return (wave * env * 0.28).astype(np.float32)


def _tone(freq, duration, sr, timbre, rng):
    if timbre == "吉他":
        return _tone_guitar(freq, duration, sr, rng)
    if timbre == "管風琴":
        return _tone_organ(freq, duration, sr, rng)
    return _tone_piano(freq, duration, sr, rng)


def _rest(duration, sr):
    return np.zeros(int(sr * duration), dtype=np.float32)


def _lowpass(audio, sr, cutoff=8000.0):
    sos = _LOWPASS_SOS if (sr == 44100 and cutoff == 8000.0) else butter(4, cutoff / (sr / 2), btype="low", output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def _synth_chord_block(midi_notes, duration, sr, rng, timbre="鋼琴"):
    n = int(sr * duration)
    mixed = np.zeros(n, dtype=np.float64)
    for midi in midi_notes:
        freq = 440.0 * (2 ** ((midi - 69) / 12))
        mixed += _tone(freq, duration, sr, timbre, rng).astype(np.float64)
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed /= peak
    return (mixed * 0.28).astype(np.float32)


def _synth_chord_sequence(text, bpm, sr, rng, beats_per_bar=4, timbre="鋼琴"):
    beat = 60.0 / bpm
    bars = text.split("|")
    segments = []
    for bar in bars:
        chords = [t for t in bar.split() if t]
        if not chords:
            continue
        dur = beat * beats_per_bar / len(chords)
        for tok in chords:
            notes = _parse_chord_token(tok)
            if notes:
                segments.append(_synth_chord_block(notes, dur, sr, rng, timbre))
            else:
                segments.append(np.zeros(int(sr * dur), dtype=np.float32))
    return np.concatenate(segments) if segments else np.zeros(0, dtype=np.float32)


def _click_track(total_samples, bpm, sr, beats_per_bar=4, vol=0.18):
    beat_samples = int(sr * 60.0 / bpm)
    click = np.zeros(total_samples, dtype=np.float32)
    pos, beat_idx = 0, 0
    while pos < total_samples:
        freq = 1000.0 if (beat_idx % beats_per_bar == 0) else 800.0
        dur = int(0.02 * sr)
        t = np.linspace(0, 0.02, dur, endpoint=False)
        burst = np.sin(2 * np.pi * freq * t) * np.exp(-80 * t)
        end = min(pos + dur, total_samples)
        click[pos:end] += burst[:end - pos]
        pos += beat_samples; beat_idx += 1
    return click * vol


# ── 主合成函式 ────────────────────────────────────────────────────────────────

def parse_and_synth(text: str, key: str, bpm: int, octave: int,
                    timbre: str = "鋼琴", chord_text: str = "",
                    beats_per_bar: int = 4,
                    metronome: bool = False,
                    metronome_vol: float = 0.18) -> str:
    sr = 44100
    beat = 60.0 / bpm
    root_midi = MELODY_KEY_ROOTS.get(key, 60) + (octave - 4) * 12

    tokens = text.replace("|", " ").split()
    segments: list[np.ndarray] = []
    last_freq: float | None = None

    for tok in tokens:
        if not tok:
            continue
        if tok.lstrip("-") == "" and last_freq is not None:
            segments.append(_tone(last_freq, beat * len(tok), sr, timbre, _RNG))
            continue
        if tok[0] == "0":
            segments.append(_rest(beat * (1 + tok.count("-")), sr))
            last_freq = None
            continue

        i = 0
        if tok[i] not in JIANPU_INTERVALS:
            continue
        note_char = tok[i]; i += 1

        sharp = flat = False
        if i < len(tok) and tok[i] == "#":
            sharp = True; i += 1
        elif i < len(tok) and tok[i] == "b":
            flat = True; i += 1

        oct_shift = 0
        while i < len(tok) and tok[i] in ("'", ","):
            oct_shift += 1 if tok[i] == "'" else -1
            i += 1

        suffix = tok[i:]
        underscores = suffix.count("_")
        extra_beats = suffix.count("-")
        dotted = "." in suffix

        if underscores >= 2:
            duration = beat * 0.25
        elif underscores == 1:
            duration = beat * 0.5
        else:
            duration = beat * (1 + extra_beats)
        if dotted:
            duration *= 1.5

        semitone = JIANPU_INTERVALS[note_char] + (1 if sharp else -1 if flat else 0)
        midi = root_midi + semitone + oct_shift * 12
        freq = 440.0 * (2 ** ((midi - 69) / 12))
        last_freq = freq
        segments.append(_tone(freq, duration, sr, timbre, _RNG))

    has_chords = bool(chord_text and chord_text.strip())
    if not segments and not has_chords:
        raise ValueError("沒有解析到任何音符，請確認輸入格式。")

    melody_audio = np.concatenate(segments) if segments else np.zeros(0, dtype=np.float32)

    if has_chords:
        chord_audio = _synth_chord_sequence(chord_text, bpm, sr, _RNG, beats_per_bar, timbre)
        if len(melody_audio) == 0:
            audio = chord_audio
        else:
            ml, cl = len(melody_audio), len(chord_audio)
            if cl < ml:
                chord_audio = np.pad(chord_audio, (0, ml - cl))
            elif cl > ml:
                melody_audio = np.pad(melody_audio, (0, cl - ml))
            audio = melody_audio * 0.72 + chord_audio
    else:
        audio = melody_audio

    cutoff = TIMBRE_CUTOFF.get(timbre, 8000.0)
    audio = _lowpass(audio.astype(np.float32), sr, cutoff=cutoff)
    if metronome and len(audio) > 0:
        audio = audio + _click_track(len(audio), bpm, sr, beats_per_bar, metronome_vol)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9

    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(out_path, audio, sr)
    return out_path
