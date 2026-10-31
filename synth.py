"""簡譜／和弦合成與音色。"""
import os
import tempfile

import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter, sosfilt

from keys import KEY_DISPLAY, MAJOR_KEYS, NOTE_MAP
from tmpfiles import _reg_tmp

_LOWPASS_SOS = butter(4, 8000.0 / (44100 / 2), btype="low", output="sos")

TIMBRE_CUTOFF = {
    "鋼琴": 7000.0,
    "吉他": 9000.0,
    "長笛": 5000.0,
    "管風琴": 6000.0,
    "豎琴": 10000.0,
    "小提琴": 7500.0,
}
_RNG = np.random.default_rng()

JIANPU_INTERVALS = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "7": 11}

MELODY_KEY_ROOTS = {
    "C": 60, "C#": 61, "D": 62, "D#": 63, "E": 64,
    "F": 65, "F#": 66, "G": 67, "G#": 68, "A": 69, "A#": 70, "B": 71,
}

MELODY_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Chord parsing — roots ordered longest-first to avoid C matching C# prefix
_CHORD_ROOTS = [
    ("C#", 1), ("Db", 1), ("D#", 3), ("Eb", 3), ("F#", 6), ("Gb", 6),
    ("G#", 8), ("Ab", 8), ("A#", 10), ("Bb", 10),
    ("C", 0), ("D", 2), ("E", 4), ("F", 5), ("G", 7), ("A", 9), ("B", 11),
]
# Intervals (semitones) for each chord quality suffix
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
    """Return list of MIDI notes for a chord token, or None if unrecognised."""
    # Ignore slash bass note (G/B → G)
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
    # Voicing: root one octave lower (C3), chord tones in C4 range
    bass = 48 + root_semi          # C3 = 48
    upper = [60 + root_semi + iv for iv in intervals]
    # Clamp upper notes to a singable range
    upper = [n - 12 if n > 76 else n for n in upper]
    return [bass] + upper


def _synth_chord_block(midi_notes: list[int], duration: float,
                       sr: int, rng: np.random.Generator,
                       timbre: str = "鋼琴") -> np.ndarray:
    n = int(sr * duration)
    mixed = np.zeros(n, dtype=np.float64)
    for midi in midi_notes:
        freq = 440.0 * (2 ** ((midi - 69) / 12))
        mixed += _tone(freq, duration, sr, timbre, rng).astype(np.float64)
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed /= peak
    return (mixed * 0.28).astype(np.float32)


def _synth_chord_sequence(text: str, bpm: int, sr: int,
                          rng: np.random.Generator,
                          beats_per_bar: int = 4,
                          timbre: str = "鋼琴") -> np.ndarray:
    beat = 60.0 / bpm
    bars = text.split("|")
    segments: list[np.ndarray] = []

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


def _lowpass(audio: np.ndarray, sr: int, cutoff: float = 8000.0) -> np.ndarray:
    sos = _LOWPASS_SOS if (sr == 44100 and cutoff == 8000.0) else butter(4, cutoff / (sr / 2), btype="low", output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def _tone_piano(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    detune = 1.0 + rng.uniform(-0.002, 0.002)
    f = freq * detune
    t = np.linspace(0, duration, n, endpoint=False)
    # Bright attack harmonics that decay at different rates
    harmonics = [(1, 1.0, 3.0), (2, 0.60, 5.0), (3, 0.25, 8.0), (4, 0.10, 12.0), (5, 0.04, 18.0)]
    wave = np.zeros(n, dtype=np.float64)
    for h, amp, decay_rate in harmonics:
        harmonic_decay = np.exp(-decay_rate * np.linspace(0, 1, n))
        wave += amp * np.sin(2 * np.pi * f * h * t) * harmonic_decay
    # Sharp percussive attack
    atk = min(int(0.006 * sr), n)
    env = np.ones(n, dtype=np.float32)
    env[:atk] *= np.linspace(0, 1, atk) ** 0.5
    fade = min(int(0.015 * sr), n)
    env[n - fade:] *= np.linspace(1, 0, fade)
    vel = rng.uniform(0.88, 1.12)
    return (wave * env * 0.38 * vel).astype(np.float32)


def _tone_guitar(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """Karplus-Strong with brighter excitation for a more distinct plucked sound."""
    period = max(2, int(sr / freq))
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    # Brighter impulse: mix noise + sawtooth burst for more high-freq content
    t_imp = np.linspace(0, 1, period)
    impulse = rng.uniform(-1.0, 1.0, period) * 0.6 + (2 * (t_imp % 1.0) - 1) * 0.4
    x = np.zeros(n, dtype=np.float64)
    x[:period] = impulse
    coeff = rng.uniform(0.996, 0.999)
    a = np.zeros(period + 2)
    a[0] = 1.0
    a[period]     = -coeff * 0.5
    a[period + 1] = -coeff * 0.5
    out = lfilter([1.0], a, x)
    # Body resonance: slight low-mid boost
    out *= np.exp(-0.8 * np.linspace(0, 1, n))
    fade = min(int(0.02 * sr), n)
    out[n - fade:] *= np.linspace(1, 0, fade)
    vel = rng.uniform(0.85, 1.15)
    return (out * 0.70 * vel).astype(np.float32)


def _tone_flute(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """清亮長笛：以基音為主，緩慢起音，輕微顫音。"""
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0, duration, n, endpoint=False)
    # Slight vibrato
    vibrato = 1.0 + 0.003 * np.sin(2 * np.pi * 5.5 * t)
    f = freq * vibrato
    # Mostly fundamental, soft 2nd harmonic, tiny 3rd
    wave = (np.sin(2 * np.pi * np.cumsum(f) / sr)
            + 0.18 * np.sin(2 * np.pi * 2 * freq * t)
            + 0.04 * np.sin(2 * np.pi * 3 * freq * t))
    # Slow breath attack
    atk = min(int(0.06 * sr), n)
    env = np.ones(n, dtype=np.float32)
    env[:atk] *= np.linspace(0, 1, atk) ** 1.5
    fade = min(int(0.02 * sr), n)
    env[n - fade:] *= np.linspace(1, 0, fade)
    # Slight breathiness via noise
    breath = rng.uniform(-1, 1, n) * 0.04
    vel = rng.uniform(0.90, 1.10)
    return ((wave + breath) * env * 0.42 * vel).astype(np.float32)


def _tone_organ(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """管風琴：鋸齒波諧波，持音不衰減，教會感。"""
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0, duration, n, endpoint=False)
    # Drawbar-style harmonic mixing (fundamental + octaves + 5th)
    drawbars = [(1, 0.8), (2, 0.6), (3, 0.4), (4, 0.3), (6, 0.2), (8, 0.15)]
    wave = sum(amp * np.sin(2 * np.pi * freq * h * t) for h, amp in drawbars)
    # Hard on/off with tiny fade
    env = np.ones(n, dtype=np.float32)
    atk = min(int(0.008 * sr), n)
    env[:atk] *= np.linspace(0, 1, atk)
    fade = min(int(0.015 * sr), n)
    env[n - fade:] *= np.linspace(1, 0, fade)
    return (wave * env * 0.28).astype(np.float32)


def _tone_harp(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """豎琴：Karplus-Strong，快速衰減，高頻清脆。"""
    period = max(2, int(sr / freq))
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    x = np.zeros(n, dtype=np.float64)
    x[:period] = rng.uniform(-1.0, 1.0, period)
    x[:period] += np.sin(np.linspace(0, np.pi, period)) * 0.5
    # Slower decay so it rings (was 0.988–0.993, now closer to guitar)
    coeff = rng.uniform(0.994, 0.997)
    a = np.zeros(period + 2)
    a[0] = 1.0
    a[period]     = -coeff * 0.5
    a[period + 1] = -coeff * 0.5
    out = lfilter([1.0], a, x)
    # Gentler decay — let it ring naturally, only slight extra envelope
    out *= np.exp(-1.0 * np.linspace(0, 1, n))
    # Short echo (~25ms) for body resonance
    echo_delay = int(0.025 * sr)
    if echo_delay < n:
        out[echo_delay:] += out[:-echo_delay] * 0.18
    fade = min(int(0.02 * sr), n)
    out[n - fade:] *= np.linspace(1, 0, fade)
    vel = rng.uniform(0.85, 1.15)
    return (out * 0.72 * vel).astype(np.float32)


def _tone_violin(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """小提琴：帶弓擦雜訊的鋸齒波，緩慢起音，顫音。"""
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0, duration, n, endpoint=False)
    # Vibrato builds up gradually
    vib_depth = np.clip(np.linspace(0, 0.008, n), 0, 0.008)
    phase = np.cumsum(2 * np.pi * freq * (1.0 + vib_depth * np.sin(2 * np.pi * 5.8 * t)) / sr)
    # Sawtooth via harmonic sum — bowed string character
    harmonics = [(1, 1.0), (2, 0.45), (3, 0.28), (4, 0.18), (5, 0.12), (6, 0.08)]
    wave = sum(amp * np.sin(h * phase) for h, amp in harmonics)
    # Bow noise: bandpass noise that fades after attack
    noise_raw = rng.uniform(-1, 1, n)
    # Simple bandpass: highpass then lowpass
    b_hp, a_hp = butter(2, 800 / (sr / 2), btype="high")
    b_lp, a_lp = butter(2, 3000 / (sr / 2), btype="low")
    bow_noise = lfilter(b_lp, a_lp, lfilter(b_hp, a_hp, noise_raw))
    noise_env = np.exp(-6.0 * np.linspace(0, 1, n)) * 0.35  # fades quickly
    # Slow bow attack
    atk = min(int(0.06 * sr), n)
    env = np.ones(n, dtype=np.float32)
    env[:atk] *= np.linspace(0, 1, atk) ** 1.5
    fade = min(int(0.03 * sr), n)
    env[n - fade:] *= np.linspace(1, 0, fade)
    combined = (wave + bow_noise * noise_env) * env
    vel = rng.uniform(0.88, 1.12)
    return (combined * 0.24 * vel).astype(np.float32)


def _tone(freq: float, duration: float, sr: int, timbre: str, rng: np.random.Generator) -> np.ndarray:
    if timbre == "吉他":
        return _tone_guitar(freq, duration, sr, rng)
    if timbre == "長笛":
        return _tone_flute(freq, duration, sr, rng)
    if timbre == "管風琴":
        return _tone_organ(freq, duration, sr, rng)
    if timbre == "豎琴":
        return _tone_harp(freq, duration, sr, rng)
    if timbre == "小提琴":
        return _tone_violin(freq, duration, sr, rng)
    return _tone_piano(freq, duration, sr, rng)


def _rest(duration: float, sr: int) -> np.ndarray:
    return np.zeros(int(sr * duration), dtype=np.float32)


def _click_track(total_samples: int, bpm: int, sr: int,
                 beats_per_bar: int = 4, vol: float = 0.18) -> np.ndarray:
    beat_samples = int(sr * 60.0 / bpm)
    click = np.zeros(total_samples, dtype=np.float32)
    pos = 0
    beat_idx = 0
    while pos < total_samples:
        # 強拍用 1000Hz，弱拍用 800Hz
        freq = 1000.0 if (beat_idx % beats_per_bar == 0) else 800.0
        dur = int(0.02 * sr)  # 20ms click
        t = np.linspace(0, 0.02, dur, endpoint=False)
        burst = np.sin(2 * np.pi * freq * t) * np.exp(-80 * t)
        end = min(pos + dur, total_samples)
        click[pos:end] += burst[:end - pos]
        pos += beat_samples
        beat_idx += 1
    return click * vol


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

        # Standalone dash = extend previous note
        if tok.lstrip("-") == "" and last_freq is not None:
            extra = len(tok)
            segments.append(_tone(last_freq, beat * extra, sr, timbre, _RNG))
            continue

        # Rest
        if tok[0] == "0":
            extra = tok.count("-")
            segments.append(_rest(beat * (1 + extra), sr))
            last_freq = None
            continue

        # Note token: digit [#] [' or ,]* [-]*
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

        # _ = 八分音符 (0.5拍), __ = 十六分音符 (0.25拍), . = 附點(×1.5), 無 = 四分音符
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

    if segments:
        melody_audio = np.concatenate(segments)
    else:
        melody_audio = np.zeros(0, dtype=np.float32)

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
        click = _click_track(len(audio), bpm, sr, beats_per_bar, metronome_vol)
        audio = audio + click
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9
    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    _reg_tmp(out_path)
    sf.write(out_path, audio, sr)
    return out_path


DIATONIC_DEGREES = [(0, ""), (2, "m"), (4, "m"), (5, ""), (7, ""), (9, "m"), (11, "dim")]


def get_diatonic_chords(key: str) -> list[str]:
    root_semi = NOTE_MAP.get(key, 0)
    result = []
    for interval, quality in DIATONIC_DEGREES:
        semi = (root_semi + interval) % 12
        name = MAJOR_KEYS[semi]
        display = KEY_DISPLAY.get(name, name).split("/")[0]
        result.append(f"{display}{quality}")
    return result


def _write_normalized(audio: np.ndarray, sr: int) -> str:
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.85
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    _reg_tmp(path)
    sf.write(path, audio, sr)
    return path


def play_chord_audio(chord_name: str) -> str | None:
    notes = _parse_chord_token(chord_name)
    if not notes:
        return None
    sr = 44100
    audio = _synth_chord_block(notes, 1.5, sr, _RNG)
    audio = _lowpass(audio, sr)
    return _write_normalized(audio, sr)


def _apply_quality_mod(chord: str, mod: str) -> str:
    mod = mod.split()[0]  # strip the Chinese label ("7 藍調" → "7")
    if mod == "基本":
        return chord
    root = chord
    is_minor = is_dim = False
    for name, _ in _CHORD_ROOTS:
        if chord.startswith(name):
            root = name
            q = chord[len(name):]
            is_minor = q.startswith("m") and "maj" not in q
            is_dim = "dim" in q
            break
    if mod == "m":
        return root + "m"
    if mod == "m7":
        return root + "m7"
    if mod == "7":
        return root + ("dim7" if is_dim else "7")
    if mod == "maj7":
        return root + "maj7"
    if mod == "sus4":
        return root + "sus4"
    if mod == "sus2":
        return root + "sus2"
    if mod == "add9":
        return root + ("m9" if is_minor else "add9")
    if mod == "dim":
        return root + "dim"
    return chord




# ── 介面用的短音檔：聽節拍、聽音階 ─────────────────────────────────────────────

def click_audio(bpm: int, min_seconds: float = 12.0) -> str | None:
    """以指定 BPM 打節拍（每 4 拍一個重音），至少 min_seconds 秒。"""
    if not bpm or bpm < 30 or bpm > 300:
        return None
    sr = 44100
    beats = max(8, int(np.ceil(min_seconds * bpm / 60.0 / 4)) * 4)
    total = int(sr * 60.0 / bpm * beats)
    return _write_normalized(_click_track(total, bpm, sr, 4, 1.0), sr)


def beat_phase(onset: np.ndarray, period: float) -> float:
    """在 onset 強度上找節拍格線的起點（以 frame 計）：讓格線落點的平均 onset 最大。"""
    best, best_score = 0.0, -1.0
    for ph in np.arange(0.0, period, 0.25):
        idx = np.round(ph + np.arange(int((len(onset) - ph) // period) + 1) * period).astype(int)
        idx = idx[idx < len(onset)]
        if len(idx) == 0:
            continue
        score = float(onset[idx].mean())
        if score > best_score:
            best, best_score = float(ph), score
    return best


def tonic_hz(key_str: str | None) -> float | None:
    """調性（如 "G 大調"）的主音頻率，落在 G2–F#3，適合當低音參考。"""
    parts = (key_str or "").split()
    if len(parts) < 2 or parts[0].split("/")[0] not in NOTE_MAP:
        return None
    root = NOTE_MAP[parts[0].split("/")[0]]
    midi = 48 + root if root <= 6 else 36 + root
    return 440.0 * 2 ** ((midi - 69) / 12)


def metro_phase(audio_path: str | None, bpm: int, seconds: int = 90) -> float | None:
    """節拍格線的起點（秒，從檔案開頭算起）：格線 t = phase + k * 60/bpm 會落在歌的拍點上。
    取歌中段約 90 秒的 onset 來對齊。"""
    if not audio_path or not bpm or bpm < 30 or bpm > 300:
        return None
    import librosa
    from analysis import HOP, SR
    y, sr = librosa.load(audio_path, sr=SR, mono=True)
    n = min(len(y), int(seconds * sr))
    start = (len(y) - n) // 2
    onset = librosa.onset.onset_strength(y=y[start:start + n], sr=sr, hop_length=HOP)
    period_frames = 60.0 * sr / (HOP * bpm)
    local = beat_phase(onset, period_frames) * HOP / sr
    period = 60.0 / bpm
    return float((start / sr + local) % period)


def scale_audio(key_str: str) -> str | None:
    """由主音開始往上唱一個八度的音階（大調／自然小調），讓人聽出這個調。"""
    parts = (key_str or "").split()
    if len(parts) < 2 or parts[0].split("/")[0] not in NOTE_MAP:
        return None
    root = NOTE_MAP[parts[0].split("/")[0]]
    intervals = (0, 2, 4, 5, 7, 9, 11, 12) if parts[1] == "大調" else (0, 2, 3, 5, 7, 8, 10, 12)
    base = 60 + root if root <= 6 else 48 + root      # 落在人聲與吉他舒適的範圍
    sr = 44100
    segs = []
    for k, iv in enumerate(intervals):
        dur = 0.6 if k < len(intervals) - 1 else 1.4
        segs.append(_tone(440.0 * 2 ** ((base + iv - 69) / 12), dur, sr, "鋼琴", _RNG))
    return _write_normalized(_lowpass(np.concatenate(segs).astype(np.float32), sr), sr)
