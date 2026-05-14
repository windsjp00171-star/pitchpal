import gradio as gr

# Patch gradio_client 5.9.x bug: boolean JSON schemas crash _json_schema_to_python_type.
# The fix: return "Any" when schema is not a dict (True/False are valid JSON Schema booleans).
try:
    import gradio_client.utils as _gcu
    _orig_schema_fn = _gcu._json_schema_to_python_type
    def _safe_schema_fn(schema, defs=None):
        if not isinstance(schema, dict):
            return "Any"
        return _orig_schema_fn(schema, defs)
    _gcu._json_schema_to_python_type = _safe_schema_fn
except Exception:
    pass

import librosa
import librosa.effects
import soundfile as sf
import numpy as np
import subprocess
import tempfile
import traceback
import os
import shutil
from scipy.signal import butter, sosfilt, lfilter

# ── Supabase 連線（讀環境變數，HF Spaces Secrets 設定）─────────────────────
_sb_client = None

def _get_sb():
    global _sb_client
    if _sb_client is not None:
        return _sb_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if url and key:
        try:
            from supabase import create_client
            _sb_client = create_client(url, key)
        except Exception:
            pass
    return _sb_client


def submit_feedback(filename: str, detected: str, corrected: str,
                    confidence: int, notes: str) -> str:
    if not corrected:
        return "請先選擇正確調性。"
    if corrected == detected:
        return "你選的調性跟偵測結果一樣，不需要回報。"
    sb = _get_sb()
    if sb is None:
        return "⚠️ 資料庫未設定，反饋無法儲存。"
    try:
        sb.table("key_feedback").insert({
            "filename": filename or None,
            "detected": detected,
            "corrected": corrected,
            "confidence": confidence if isinstance(confidence, int) else None,
            "notes": notes or None,
        }).execute()
        return f"感謝回報！已記錄：{detected} → {corrected}"
    except Exception as e:
        return f"儲存失敗：{e}"

MAJOR_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MINOR_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ALL_KEYS = [f"{k} 大調" for k in MAJOR_KEYS] + [f"{k} 小調" for k in MINOR_KEYS]

KEY_DISPLAY = {
    "C#": "C#/Db",
    "D#": "D#/Eb",
    "F#": "F#/Gb",
    "G#": "G#/Ab",
    "A#": "A#/Bb",
}

OUTPUT_FORMATS = ["WAV", "MP3"]
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_AUDIO_MB = 50
MAX_VIDEO_MB = 200
MAX_DURATION_SEC = 600  # 10 minutes

NOTE_MAP = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

GUITAR_KEYS = [("C", 0), ("D", 2), ("E", 4), ("G", 7), ("A", 9)]

CSS = """
.gradio-container { max-width: 980px !important; margin: auto; }
/* Section labels */
.section-header {
    font-size: 0.68em; font-weight: 800; letter-spacing: 0.12em;
    text-transform: uppercase; color: #b07d1a;
    margin-bottom: 4px !important; margin-top: 10px !important;
    border-left: 3px solid #e6a817; padding-left: 8px;
}
/* Palette rows */
.chord-palette button { min-width: 58px !important; font-size: 0.82em !important; padding: 6px 3px !important; }
.note-palette button  { min-width: 42px !important; font-size: 0.9em  !important; padding: 6px 4px !important; font-weight: 700 !important; }
.mod-palette button   { min-width: 50px !important; font-size: 0.78em !important; padding: 5px 3px !important; }
/* Capo monospace */
#capo-box textarea { font-family: monospace; font-size: 0.9em; }
/* Tabs warm underline */
.tab-nav button.selected { border-bottom-color: #e6a817 !important; }
footer { display: none !important; }
"""


def _key_semitone(key_str: str) -> int:
    parts = key_str.split()
    if not parts:
        raise ValueError(f"無法解析 key: {key_str!r}")
    note = parts[0].split("/")[0]
    if note not in NOTE_MAP:
        raise ValueError(f"未知音名: {note!r}")
    return NOTE_MAP[note]


def _resolve_path(file) -> str | None:
    if file is None:
        return None
    if isinstance(file, str):
        return file
    if isinstance(file, dict):
        return file.get("path") or file.get("name")
    if hasattr(file, "path"):
        return file.path
    if hasattr(file, "name"):
        return file.name
    return str(file)


def _extract_audio_from_video(video_path: str) -> str:
    """Use ffmpeg to strip video, return path to extracted WAV."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    result = subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "44100", "-ac", "2", wav_path, "-y"],
        capture_output=True,
    )
    if result.returncode != 0:
        os.remove(wav_path)
        raise ValueError("無法從影片擷取音軌，請確認影片包含音頻。")
    return wav_path


def _prepare_audio(file_path: str) -> tuple[str, bool]:
    """
    Returns (audio_path, needs_cleanup).
    If input is a video, extracts audio first.
    Raises ValueError with user-friendly message on validation failure.
    """
    ext = os.path.splitext(file_path)[1].lower()
    size_mb = os.path.getsize(file_path) / 1024 / 1024

    is_video = ext in VIDEO_EXTS
    limit_mb = MAX_VIDEO_MB if is_video else MAX_AUDIO_MB

    if size_mb > limit_mb:
        kind = "影片" if is_video else "音頻"
        raise ValueError(f"{kind}檔案過大（{size_mb:.0f} MB），上限為 {limit_mb} MB。")

    if is_video:
        if not FFMPEG_AVAILABLE:
            raise ValueError("伺服器未安裝 ffmpeg，無法處理影片檔案。")
        audio_path = _extract_audio_from_video(file_path)
        return audio_path, True

    return file_path, False


def _ks_scores(chroma_mean: np.ndarray) -> tuple[list, list]:
    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    major = [np.corrcoef(np.roll(major_profile, i), chroma_mean)[0, 1] for i in range(12)]
    minor = [np.corrcoef(np.roll(minor_profile, i), chroma_mean)[0, 1] for i in range(12)]
    return major, minor


def detect_key(audio_path: str):
    y, sr = librosa.load(audio_path, mono=True)
    if len(y) == 0:
        raise ValueError("音頻檔案為空或無法讀取。")

    duration = len(y) / sr
    if duration > MAX_DURATION_SEC:
        raise ValueError(f"音頻長度 {duration/60:.1f} 分鐘，超過上限 {MAX_DURATION_SEC//60} 分鐘。")

    # 1. 裁掉首尾靜音
    y, _ = librosa.effects.trim(y, top_db=20)

    # 2. 跳過前後各 10%，分析中間 80%（避免前奏/尾奏干擾）
    n = len(y)
    margin = int(n * 0.10)
    y_core = y[margin: n - margin] if n - 2 * margin > sr else y

    # 3. 多窗口投票：把核心段切成 4 塊，各自算 KS，再平均
    segments = np.array_split(y_core, 4)
    all_major = np.zeros(12)
    all_minor = np.zeros(12)
    for seg in segments:
        if len(seg) < sr // 4:
            continue
        # chroma_cens 比 chroma_cqt 更抗雜訊
        chroma = librosa.feature.chroma_cens(y=seg, sr=sr)
        cm = chroma.mean(axis=1)
        maj, minor = _ks_scores(cm)
        all_major += np.array(maj)
        all_minor += np.array(minor)

    best_major_idx = int(np.argmax(all_major))
    best_minor_idx = int(np.argmax(all_minor))
    best_major_score = all_major[best_major_idx]
    best_minor_score = all_minor[best_minor_idx]

    if best_major_score >= best_minor_score:
        root = MAJOR_KEYS[best_major_idx]
        best_score = best_major_score
        mode = "大調"
    else:
        root = MINOR_KEYS[best_minor_idx]
        best_score = best_minor_score
        mode = "小調"

    display = KEY_DISPLAY.get(root, root)
    key_str = f"{display} {mode}"

    all_scores = list(all_major) + list(all_minor)
    others = [s for s in all_scores if s != best_score]
    margin_score = best_score - float(np.mean(others))
    confidence = int(min(100, max(0, margin_score / (0.35 * 4) * 100)))

    return key_str, confidence


def result_key(detected_key: str, steps: int) -> str:
    if not detected_key:
        return ""
    try:
        src = _key_semitone(detected_key)
    except ValueError:
        return ""
    result_semi = (src + steps) % 12
    mode = "大調" if "大調" in detected_key else "小調"
    root = MAJOR_KEYS[result_semi] if mode == "大調" else MINOR_KEYS[result_semi]
    display = KEY_DISPLAY.get(root, root)
    return f"{display} {mode}"


def capo_suggestions(key_str: str) -> str:
    if not key_str:
        return ""
    try:
        target = _key_semitone(key_str)
    except ValueError:
        return ""
    results = []
    for key_name, key_semi in GUITAR_KEYS:
        capo = (target - key_semi) % 12
        if capo <= 7:
            label = "不夾 Capo" if capo == 0 else f"Capo {capo}"
            results.append((capo, f"{label}  →  用 {key_name} 指型彈奏"))
    results.sort(key=lambda x: x[0])
    if not results:
        return "此 Key 無常用 Capo 組合"
    return "\n".join(r[1] for r in results)


def process_upload(file):
    try:
        if not file:
            return "", "", "—", "", ""
        file_path = _resolve_path(file)
        print(f"[pitchpal] process_upload: type={type(file).__name__}, path={file_path!r}")
        if not file_path:
            return "", "無法取得檔案路徑", "—", "", ""
        if not os.path.exists(file_path):
            return "", f"檔案不存在：{file_path}", "—", "", ""

        filename = os.path.basename(file_path)
        extracted = None
        try:
            audio_path, needs_cleanup = _prepare_audio(file_path)
            if needs_cleanup:
                extracted = audio_path
            key, conf = detect_key(audio_path)
        finally:
            if extracted and os.path.exists(extracted):
                os.remove(extracted)

        rkey = result_key(key, 0)
        capo = capo_suggestions(rkey)
        return filename, key, f"{conf}%", rkey, capo
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"[pitchpal] process_upload error:\n{traceback.format_exc()}")
        return "", msg, "—", "", ""


def on_slider_change(detected_key: str, steps: int):
    rkey = result_key(detected_key, steps)
    capo = capo_suggestions(rkey)
    return rkey, capo


def _safe_stem(name: str, max_len: int = 60) -> str:
    """Sanitise a filename stem: strip path, remove illegal chars, truncate."""
    stem = os.path.splitext(os.path.basename(name))[0]
    stem = "".join(c if c.isalnum() or c in " _-()[]" else "_" for c in stem)
    stem = stem.strip("_ ") or "audio"
    return stem[:max_len]


def _write_wav(y: np.ndarray, sr: int, stem: str = "audio") -> str:
    fd, wav_path = tempfile.mkstemp(suffix=f"__{stem}.wav")
    os.close(fd)
    sf.write(wav_path, y.T if y.ndim > 1 else y, sr)
    return wav_path


def _convert_to_mp3(wav_path: str, stem: str = "audio") -> str:
    fd, out_path = tempfile.mkstemp(suffix=f"__{stem}.mp3")
    os.close(fd)
    subprocess.run(
        ["ffmpeg", "-i", wav_path, "-q:a", "2", out_path, "-y"],
        capture_output=True, check=True,
    )
    return out_path


def transpose_audio(file, detected_key, steps, output_fmt):
    if not file:
        return None, "請先上傳音頻檔案。"

    file_path = _resolve_path(file)
    if not file_path:
        return None, "無法取得檔案路徑。"
    if output_fmt == "MP3" and not FFMPEG_AVAILABLE:
        return None, "輸出 MP3 需要 ffmpeg，目前環境不支援。"

    steps = int(steps)
    direction = f"+{steps}" if steps > 0 else str(steps)
    stem = _safe_stem(file_path)
    if steps != 0:
        stem = f"{stem}_({direction}半音)"

    extracted = wav_path = None
    try:
        audio_path, needs_cleanup = _prepare_audio(file_path)
        if needs_cleanup:
            extracted = audio_path

        y, sr = librosa.load(audio_path, sr=None, mono=False)

        duration = len(y) / sr if y.ndim == 1 else y.shape[1] / sr
        if duration > MAX_DURATION_SEC:
            return None, f"音頻長度 {duration/60:.1f} 分鐘，超過上限 {MAX_DURATION_SEC//60} 分鐘。"

        if steps == 0:
            y_shifted = y
        else:
            _ps = lambda ch: librosa.effects.pitch_shift(
                ch, sr=sr, n_steps=steps, n_fft=8192, bins_per_octave=24)
            if y.ndim == 1:
                y_shifted = _ps(y)
            else:
                y_shifted = np.stack([_ps(y[ch]) for ch in range(y.shape[0])])

        wav_path = _write_wav(y_shifted, sr, stem)

        if output_fmt == "WAV":
            out_path = wav_path
            wav_path = None
        else:
            out_path = _convert_to_mp3(wav_path, stem)

        if steps == 0:
            msg = f"無移調，已輸出為 {output_fmt}。"
        elif detected_key and not detected_key.startswith("偵測失敗"):
            rkey = result_key(detected_key, steps)
            msg = f"移調完成：{detected_key} → {rkey}（{direction} 個半音）｜格式：{output_fmt}"
        else:
            msg = f"移調完成：{direction} 個半音｜格式：{output_fmt}"
        return out_path, msg

    except Exception as e:
        return None, f"處理失敗：{e}"
    finally:
        for p in (extracted, wav_path):
            if p and os.path.exists(p):
                os.remove(p)


# ── 簡譜合成 ──────────────────────────────────────────────────────────────────

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
                       sr: int, rng: np.random.Generator) -> np.ndarray:
    n = int(sr * duration)
    mixed = np.zeros(n, dtype=np.float64)
    for midi in midi_notes:
        freq = 440.0 * (2 ** ((midi - 69) / 12))
        mixed += _tone_piano(freq, duration, sr, rng).astype(np.float64)
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed /= peak
    return (mixed * 0.28).astype(np.float32)


def _synth_chord_sequence(text: str, bpm: int, sr: int,
                          rng: np.random.Generator,
                          beats_per_bar: int = 4) -> np.ndarray:
    """Bar-based chord sequence: 'C Em7 | D | G/B | Em7 D'
    Chords within a bar share beats evenly."""
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
                segments.append(_synth_chord_block(notes, dur, sr, rng))
            else:
                segments.append(np.zeros(int(sr * dur), dtype=np.float32))

    return np.concatenate(segments) if segments else np.zeros(0, dtype=np.float32)


def _lowpass(audio: np.ndarray, sr: int, cutoff: float = 3500.0) -> np.ndarray:
    sos = butter(4, cutoff / (sr / 2), btype="low", output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def _tone_piano(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    # Slight random detuning ±4 cents for natural feel
    detune = 1.0 + rng.uniform(-0.002, 0.002)
    f = freq * detune
    t = np.linspace(0, duration, n, endpoint=False)
    # Warm harmonics — roll off quickly above 3rd partial
    harmonics = [(1, 1.0), (2, 0.40), (3, 0.15), (4, 0.06), (5, 0.02)]
    wave = sum(amp * np.sin(2 * np.pi * f * h * t) for h, amp in harmonics)
    # Percussive attack + exponential decay
    atk = min(int(0.012 * sr), n)
    decay = np.exp(-3.5 * np.linspace(0, 1, n))
    env = decay.astype(np.float32)
    env[:atk] *= np.linspace(0, 1, atk)
    fade = min(int(0.015 * sr), n)
    env[n - fade:] *= np.linspace(1, 0, fade)
    # Random velocity variation ±12%
    vel = rng.uniform(0.88, 1.12)
    return (wave * env * 0.40 * vel).astype(np.float32)


def _tone_guitar(freq: float, duration: float, sr: int, rng: np.random.Generator) -> np.ndarray:
    """Karplus-Strong via IIR filter (scipy.signal.lfilter) — O(n) in C, not Python."""
    period = max(2, int(sr / freq))
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    # Impulse: noise burst for first period, then silence
    x = np.zeros(n, dtype=np.float64)
    x[:period] = rng.uniform(-1.0, 1.0, period)
    coeff = rng.uniform(0.994, 0.998)
    # y[n] = x[n] + coeff*0.5*y[n-period] + coeff*0.5*y[n-period-1]
    a = np.zeros(period + 2)
    a[0] = 1.0
    a[period]     = -coeff * 0.5
    a[period + 1] = -coeff * 0.5
    out = lfilter([1.0], a, x)
    fade = min(int(0.02 * sr), n)
    out[n - fade:] *= np.linspace(1, 0, fade)
    vel = rng.uniform(0.85, 1.15)
    return (out * 0.65 * vel).astype(np.float32)


def _tone(freq: float, duration: float, sr: int, timbre: str, rng: np.random.Generator) -> np.ndarray:
    if timbre == "吉他":
        return _tone_guitar(freq, duration, sr, rng)
    return _tone_piano(freq, duration, sr, rng)


def _rest(duration: float, sr: int) -> np.ndarray:
    return np.zeros(int(sr * duration), dtype=np.float32)


def parse_and_synth(text: str, key: str, bpm: int, octave: int,
                    timbre: str = "鋼琴", chord_text: str = "",
                    beats_per_bar: int = 4) -> str:
    sr = 44100
    beat = 60.0 / bpm
    root_midi = MELODY_KEY_ROOTS.get(key, 60) + (octave - 4) * 12
    rng = np.random.default_rng()

    tokens = text.replace("|", " ").split()
    segments: list[np.ndarray] = []
    last_freq: float | None = None

    for tok in tokens:
        if not tok:
            continue

        # Standalone dash = extend previous note
        if tok.lstrip("-") == "" and last_freq is not None:
            extra = len(tok)
            segments.append(_tone(last_freq, beat * extra, sr, timbre, rng))
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

        sharp = False
        if i < len(tok) and tok[i] == "#":
            sharp = True; i += 1

        oct_shift = 0
        while i < len(tok) and tok[i] in ("'", ","):
            oct_shift += 1 if tok[i] == "'" else -1
            i += 1

        extra_beats = tok[i:].count("-")

        semitone = JIANPU_INTERVALS[note_char] + (1 if sharp else 0)
        midi = root_midi + semitone + oct_shift * 12
        freq = 440.0 * (2 ** ((midi - 69) / 12))
        last_freq = freq
        segments.append(_tone(freq, beat * (1 + extra_beats), sr, timbre, rng))

    has_chords = bool(chord_text and chord_text.strip())

    if not segments and not has_chords:
        raise ValueError("沒有解析到任何音符，請確認輸入格式。")

    if segments:
        melody_audio = np.concatenate(segments)
    else:
        melody_audio = np.zeros(0, dtype=np.float32)

    if has_chords:
        chord_audio = _synth_chord_sequence(chord_text, bpm, sr, rng, beats_per_bar)
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

    audio = _lowpass(audio.astype(np.float32), sr, cutoff=3500.0)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9
    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(out_path, audio, sr)
    return out_path


JIANPU_HELP = """
---
**旋律：數字簡譜格式**

| 輸入 | 意思 | 例子 |
|---|---|---|
| `1` – `7` | Do Re Mi Fa Sol La Ti | `1 2 3` |
| `4#` | 升半音 | `4# 5 6` |
| `1'` | 高八度（加一撇） | `5 6 7 1'` |
| `1,` | 低八度（加一逗） | `3, 4, 5` |
| `1--` | 延音，幾個 `-` = 幾拍 | `5---`（4拍） |
| `0` | 休止符 | `1 2 0 3` |
| `|` | 小節線（裝飾用，可省略） | |

---
**和弦：小節格式**

用 `|` 把和弦分成小節，同一小節的和弦**自動平均分配拍數**：
- `C | G | Am | F` → 每個和弦各佔一整小節（4/4 = 各 4 拍）
- `C G | Am F` → 每小節兩個和弦，各 2 拍
- `C Em7 Am | F` → 第一小節三和弦各約 1.3 拍，第二小節 F 4 拍

支援常見和弦：`C` `Cm` `C7` `Cm7` `Cmaj7` `Csus` `Csus2` `Cdim` `Caug` `C²` `G/B`

---
**範例：遠超過諸天 Intro（G 調，4/4）**

旋律：
```
5 6 7 5 3 - - - | 7 5 6 - | 4# 5 6 4# 2 - | 6 4# 5 -
```
和弦：
```
C Em7 | D | G/B | Em7 D
```
"""

def _submit_feedback(file, detected, conf_str, corrected, notes):
    filename = ""
    if file:
        p = _resolve_path(file)
        filename = os.path.basename(p) if p else ""
    try:
        conf = int(conf_str.replace("%", ""))
    except Exception:
        conf = None
    return submit_feedback(filename, detected, corrected, conf, notes)


def _gen_melody(text, key, bpm, octave, timbre, chord_text, time_sig):
    has_melody = bool(text and text.strip())
    has_chords = bool(chord_text and chord_text.strip())
    if not has_melody and not has_chords:
        return None, "請輸入旋律或和弦進行。"
    beats_per_bar = 3 if time_sig == "3/4" else 4
    try:
        path = parse_and_synth(text or "", key, int(bpm), int(octave), timbre,
                               chord_text or "", beats_per_bar)
        if has_melody and has_chords:
            suffix = "旋律 + 和弦"
        elif has_chords:
            suffix = "和弦進行"
        else:
            suffix = "旋律"
        return path, f"生成完成（{suffix}）｜{time_sig}，調性：{key}，BPM：{bpm}"
    except Exception as e:
        return None, f"生成失敗：{e}"


# ── 和弦調色盤 ────────────────────────────────────────────────────────────────

# (interval from root in semitones, chord quality suffix) for major scale degrees I–VII
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


def play_chord_audio(chord_name: str) -> str | None:
    notes = _parse_chord_token(chord_name)
    if not notes:
        return None
    rng = np.random.default_rng()
    sr = 44100
    audio = _synth_chord_block(notes, 1.5, sr, rng)
    audio = _lowpass(audio, sr)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.85
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, audio, sr)
    return path


def _apply_quality_mod(chord: str, mod: str) -> str:
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
    if mod == "7":
        return root + ("m7" if is_minor else "dim7" if is_dim else "7")
    if mod == "maj7":
        return root + ("m7" if is_minor else "maj7")
    if mod == "sus4":
        return root + "sus4"
    if mod == "add9":
        return root + ("m9" if is_minor else "add9")
    return chord


def on_chord_palette_btn(chord_name: str, chord_text: str, mode: str, quality_mod: str):
    effective = _apply_quality_mod(chord_name, quality_mod)
    audio = play_chord_audio(effective)
    if mode == "加入輸入框":
        sep = " " if chord_text.strip() else ""
        new_text = chord_text.rstrip() + sep + effective
    else:
        new_text = chord_text
    return audio, new_text


def add_barline_to_input(chord_text: str) -> str:
    return chord_text.rstrip() + " |"


_MOD_INIT = {"sharp": False, "high": False, "low": False}


def _mod_sharp_btn(active: bool):
    return gr.Button("# 升 ✓" if active else "# 升",
                     variant="primary" if active else "secondary", size="sm")

def _mod_high_btn(active: bool):
    return gr.Button("' 高八 ✓" if active else "' 高八",
                     variant="primary" if active else "secondary", size="sm")

def _mod_low_btn(active: bool):
    return gr.Button(", 低八 ✓" if active else ", 低八",
                     variant="primary" if active else "secondary", size="sm")


def toggle_sharp(state: dict):
    new_state = {**state, "sharp": not state["sharp"]}
    return new_state, _mod_sharp_btn(new_state["sharp"])


def toggle_high(state: dict):
    new_h = not state["high"]
    new_state = {**state, "high": new_h, "low": False if new_h else state["low"]}
    return new_state, _mod_high_btn(new_state["high"]), _mod_low_btn(new_state["low"])


def toggle_low(state: dict):
    new_l = not state["low"]
    new_state = {**state, "low": new_l, "high": False if new_l else state["high"]}
    return new_state, _mod_high_btn(new_state["high"]), _mod_low_btn(new_state["low"])


def _play_note_with_mods(note_digit: str, key: str, octave: int,
                         timbre: str, state: dict) -> str | None:
    if note_digit == "0" or note_digit not in JIANPU_INTERVALS:
        return None
    sharp = state.get("sharp", False)
    high  = state.get("high",  False)
    low   = state.get("low",   False)
    root_midi = MELODY_KEY_ROOTS.get(key, 60) + (int(octave) - 4) * 12
    semitone = JIANPU_INTERVALS[note_digit] + (1 if sharp else 0)
    oct_shift = (1 if high else 0) - (1 if low else 0)
    midi = root_midi + semitone + oct_shift * 12
    freq = 440.0 * (2 ** ((midi - 69) / 12))
    rng = np.random.default_rng()
    sr = 44100
    audio = _tone(freq, 0.8, sr, timbre, rng)
    audio = _lowpass(audio, sr)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.85
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, audio, sr)
    return path


def _make_note_handler(digit: str):
    def _h(melody_text, mode, key, octave, timbre, state):
        audio = _play_note_with_mods(digit, key, int(octave), timbre, state)
        # Build token: digit [#] [' or ,]
        if digit == "0":
            tok = "0"
        else:
            tok = digit
            if state.get("sharp"):  tok += "#"
            if state.get("high"):   tok += "'"
            if state.get("low"):    tok += ","
        if mode == "加入輸入框":
            sep = " " if melody_text.strip() else ""
            new_text = melody_text.rstrip() + sep + tok
        else:
            new_text = melody_text
        # Sharp resets after each note; octave is sticky
        new_state = {**state, "sharp": False}
        return (audio, new_text, new_state,
                _mod_sharp_btn(False),
                _mod_high_btn(new_state["high"]),
                _mod_low_btn(new_state["low"]))
    return _h


def append_melody_modifier(melody_text: str, char: str) -> str:
    if char in ("-",):
        return melody_text.rstrip() + char
    sep = " " if melody_text.strip() else ""
    return melody_text.rstrip() + sep + char


def download_youtube(url: str, cookies_file: str | None = None):
    if not url or not url.strip():
        return None, "", "—", "—", "", "", "請輸入 YouTube 連結。"
    try:
        import yt_dlp
    except ImportError:
        return None, "", "—", "—", "", "", "yt-dlp 未安裝，請聯絡管理員。"

    # Try clients in order: tv_embedded and mweb bypass bot detection best on cloud IPs
    strategies = [
        {"extractor_args": {"youtube": {"player_client": ["tv_embedded"]}}},
        {"extractor_args": {"youtube": {"player_client": ["mweb"]}}},
        {"extractor_args": {"youtube": {"player_client": ["ios"]}}},
        {"extractor_args": {"youtube": {"player_client": ["android"]}}},
        {"extractor_args": {"youtube": {"player_client": ["web"]}}},
    ]

    tmpdir = tempfile.mkdtemp()
    out_template = os.path.join(tmpdir, "%(id)s.%(ext)s")

    base_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 60,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        },
    }
    if cookies_file and os.path.exists(cookies_file):
        base_opts["cookiefile"] = cookies_file
        print(f"[pitchpal] using cookies: {cookies_file}")

    last_err = None
    info = None
    try:
        for strategy in strategies:
            try:
                ydl_opts = {**base_opts, **strategy}
                client = strategy["extractor_args"]["youtube"]["player_client"][0]
                print(f"[pitchpal] yt-dlp trying client={client}: {url!r}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                break
            except Exception as e:
                last_err = e
                print(f"[pitchpal] client={client} failed: {e}")
                continue

        if info is None:
            msg = str(last_err)
            if "Sign in" in msg or "age" in msg.lower():
                msg = "此影片需要登入或有年齡限制。請匯出瀏覽器 cookies.txt 後上傳再試。"
            elif "Private" in msg or "private" in msg:
                msg = "此影片為私人影片，無法下載。"
            elif "available" in msg.lower() or "geographic" in msg.lower():
                msg = "此影片在當前地區不可用（地區限制）。"
            else:
                msg = f"所有下載方式均失敗：{msg}"
            return None, "", "—", "—", "", "", f"❌ {msg}"

        title = info.get("title", "（未知）")
        duration = info.get("duration", 0)
        if duration and duration > 900:
            return None, "", "—", "—", "", "", f"影片超過 15 分鐘（{duration//60} 分），請換較短的片段。"

        audio_path = None
        for f in os.listdir(tmpdir):
            if f.endswith(".wav"):
                audio_path = os.path.join(tmpdir, f)
                break
        if not audio_path or not os.path.exists(audio_path):
            return None, "", "—", "—", "", "", "音頻擷取失敗，請確認影片可以正常播放。"

        print(f"[pitchpal] yt download ok → {audio_path}")
        key, conf = detect_key(audio_path)
        rkey = result_key(key, 0)
        capo = capo_suggestions(rkey)
        return audio_path, title, key, f"{conf}%", rkey, capo, f"✅ 下載完成：《{title}》｜偵測調性：{key}"

    except Exception as e:
        print(f"[pitchpal] download_youtube error:\n{traceback.format_exc()}")
        return None, "", "—", "—", "", "", f"下載失敗：{e}"
    finally:
        # Clean up tmpdir but keep the wav file if it was returned successfully
        try:
            if info is None:
                shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


UPLOAD_NOTE = """
> **支援格式：** MP3、WAV、M4A、FLAC、MKV、MP4、AVI（影片自動擷取音軌）
> **檔案上限：** 音頻 50 MB｜影片 200 MB｜長度 10 分鐘以內
"""

with gr.Blocks(title="PitchPal", css=CSS) as demo:
    gr.Markdown("""
<div style="background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);border-radius:12px;padding:22px 28px;margin-bottom:4px">
<h1 style="color:#f0c040;margin:0;font-size:1.8em;letter-spacing:0.04em">🎵 PitchPal</h1>
<p style="color:#a8c5e8;margin:6px 0 0;font-size:0.95em">敬拜帶領者的移調工具 — 辨調、移調、Capo 建議、旋律試聽，一站完成。</p>
</div>
""")

    with gr.Tabs():

        # ── Tab 1：移調工具 ──────────────────────────────────────────────────
        with gr.Tab("🎚️ 移調工具"):
            with gr.Row(equal_height=False):

                # ── 左欄：輸入 ──────────────────────────────────────────────
                with gr.Column(scale=5):

                    # 區塊 1：音源
                    gr.Markdown("**音源**", elem_classes="section-header")
                    with gr.Tabs():
                        with gr.Tab("上傳檔案"):
                            audio_input = gr.Audio(
                                type="filepath",
                                sources=["upload"],
                                show_label=False,
                            )
                            gr.Markdown(
                                "<small>支援 MP3、WAV、M4A、FLAC、MP4、MKV｜音頻 50 MB / 影片 200 MB / 10 分鐘以內</small>",
                            )
                        with gr.Tab("YouTube 連結"):
                            with gr.Row():
                                yt_url_box = gr.Textbox(
                                    placeholder="https://www.youtube.com/watch?v=...",
                                    show_label=False,
                                    scale=4,
                                )
                                yt_btn = gr.Button("下載並分析", scale=1)
                            yt_status_box = gr.Textbox(
                                show_label=False, interactive=False,
                                placeholder="下載狀態…",
                            )
                            with gr.Accordion("遇到下載限制？", open=False):
                                gr.Markdown(
                                    "用 **Get cookies.txt LOCALLY** 擴充套件匯出 YouTube cookies.txt 後上傳，"
                                    "可解決「需要登入」或「年齡限制」的問題。"
                                )
                                yt_cookies_file = gr.File(
                                    label="cookies.txt",
                                    file_types=[".txt"],
                                    type="filepath",
                                )
                            gr.Markdown(
                                "<small>⚠️ 請確認你對該內容擁有合法授權（購買、CCLI 或版權方許可）。本工具僅供移調分析，授權責任由使用者自行承擔。</small>"
                            )

                    # 區塊 2：分析結果
                    gr.Markdown("**分析結果**", elem_classes="section-header")
                    filename_box = gr.Textbox(
                        label="檔案 / 影片名稱",
                        interactive=False,
                        placeholder="上傳或下載後顯示…",
                    )
                    with gr.Row():
                        detected_key_box = gr.Textbox(
                            label="原曲調性",
                            interactive=False,
                            placeholder="自動偵測…",
                            scale=3,
                        )
                        confidence_box = gr.Textbox(
                            label="信心度",
                            interactive=False,
                            value="—",
                            scale=1,
                        )

                    # 區塊 3：移調設定
                    gr.Markdown("**移調設定**", elem_classes="section-header")
                    with gr.Row():
                        steps_slider = gr.Number(
                            label="半音數（+ 升調 / − 降調）",
                            minimum=-12, maximum=12, step=1, value=0, precision=0,
                            scale=2,
                        )
                        result_key_box = gr.Textbox(
                            label="移調後調性",
                            interactive=False,
                            placeholder="—",
                            scale=3,
                        )
                    capo_box = gr.Textbox(
                        label="🎸 Capo 建議（吉他）",
                        interactive=False,
                        lines=3,
                        elem_id="capo-box",
                    )
                    with gr.Row():
                        output_fmt_radio = gr.Radio(
                            label="輸出格式",
                            choices=OUTPUT_FORMATS,
                            value="WAV",
                            scale=1,
                        )
                        transpose_btn = gr.Button(
                            "開始移調", variant="primary", size="lg", scale=2,
                        )

                # ── 右欄：輸出 ──────────────────────────────────────────────
                with gr.Column(scale=5):
                    gr.Markdown("**移調結果**", elem_classes="section-header")
                    status_box = gr.Textbox(
                        label="狀態", interactive=False, placeholder="移調完成後顯示…"
                    )
                    audio_output = gr.Audio(label="移調後音頻", type="filepath")

                    gr.Markdown("<br>")
                    with gr.Accordion("偵測結果不正確？回報給我們 🙏", open=False):
                        gr.Markdown(
                            "調性辨識對清晰樂器準確率較高。人聲為主、有混響或多次轉調的曲目偵測準確率會下降。"
                            "\n\n選擇正確調性後按「回報修正」即可，不需要登入，感謝幫助改善工具。"
                        )
                        feedback_key = gr.Dropdown(
                            label="正確調性", choices=ALL_KEYS, value=None,
                        )
                        feedback_notes = gr.Textbox(
                            label="備註（選填）",
                            placeholder="例如：這首歌有轉調…",
                            lines=1,
                        )
                        feedback_btn = gr.Button("回報修正", variant="secondary")
                        feedback_status = gr.Textbox(label="回報狀態", interactive=False)

            # ── 事件綁定 ────────────────────────────────────────────────────
            yt_btn.click(
                fn=download_youtube,
                inputs=[yt_url_box, yt_cookies_file],
                outputs=[audio_input, filename_box, detected_key_box, confidence_box,
                         result_key_box, capo_box, yt_status_box],
                api_name="download_youtube",
            )
            audio_input.change(
                fn=process_upload,
                inputs=[audio_input],
                outputs=[filename_box, detected_key_box, confidence_box,
                         result_key_box, capo_box],
                api_name="process_upload",
            )
            steps_slider.change(
                fn=on_slider_change,
                inputs=[detected_key_box, steps_slider],
                outputs=[result_key_box, capo_box],
                api_name="on_slider_change",
            )
            transpose_btn.click(
                fn=transpose_audio,
                inputs=[audio_input, detected_key_box, steps_slider, output_fmt_radio],
                outputs=[audio_output, status_box],
                api_name="transpose_audio",
            )
            feedback_btn.click(
                fn=_submit_feedback,
                inputs=[audio_input, detected_key_box, confidence_box,
                        feedback_key, feedback_notes],
                outputs=[feedback_status],
                api_name="submit_feedback",
            )

        # ── Tab 2：旋律試聽 ──────────────────────────────────────────────────
        with gr.Tab("🎼 旋律試聽"):
            mod_state = gr.State(_MOD_INIT)

            # ── 設定列（最頂部，橫向緊湊） ──────────────────────────────────
            gr.Markdown("**設定**", elem_classes="section-header")
            with gr.Row():
                melody_key = gr.Dropdown(
                    label="調性（1=?）", choices=MELODY_KEYS, value="G", scale=1,
                )
                melody_bpm = gr.Slider(
                    label="BPM", minimum=40, maximum=200, step=1, value=80, scale=2,
                )
                melody_octave = gr.Slider(
                    label="八度", minimum=2, maximum=6, step=1, value=4, scale=1,
                )
                melody_timbre = gr.Radio(
                    label="音色", choices=["鋼琴", "吉他"], value="鋼琴", scale=1,
                )
                time_sig_radio = gr.Radio(
                    label="拍號", choices=["4/4", "3/4"], value="4/4", scale=1,
                )

            # ── 旋律調色盤 ────────────────────────────────────────────────
            gr.Markdown("**旋律調色盤**", elem_classes="section-header")
            with gr.Row():
                note_mode = gr.Radio(
                    choices=["只試音", "加入輸入框"], value="只試音",
                    show_label=False, scale=2,
                )
                note_preview = gr.Audio(
                    label="", type="filepath",
                    show_download_button=False, autoplay=True, scale=3,
                )
            with gr.Row(elem_classes="note-palette"):
                note_btn_1 = gr.Button("1", size="sm")
                note_btn_2 = gr.Button("2", size="sm")
                note_btn_3 = gr.Button("3", size="sm")
                note_btn_4 = gr.Button("4", size="sm")
                note_btn_5 = gr.Button("5", size="sm")
                note_btn_6 = gr.Button("6", size="sm")
                note_btn_7 = gr.Button("7", size="sm")
                note_btn_0 = gr.Button("0 休", size="sm")
            with gr.Row(elem_classes="mod-palette"):
                mod_sharp  = gr.Button("# 升",  size="sm", variant="secondary")
                mod_high   = gr.Button("' 高八", size="sm", variant="secondary")
                mod_low    = gr.Button(", 低八", size="sm", variant="secondary")
                mod_extend = gr.Button("- 延音", size="sm")
                mod_bar_m  = gr.Button("| 小節", size="sm")

            # ── 旋律輸入框 ────────────────────────────────────────────────
            melody_input = gr.Textbox(
                label="旋律（數字簡譜，選填）",
                placeholder="5 6 7 5 3 - - - | 7 5 6 - | 4# 5 6 4# 2 - | 6 4# 5 -",
                lines=2,
            )

            # ── 和弦調色盤 ────────────────────────────────────────────────
            gr.Markdown("**和弦調色盤**", elem_classes="section-header")
            with gr.Row():
                chord_mode = gr.Radio(
                    choices=["只試音", "加入輸入框"], value="只試音",
                    show_label=False, scale=2,
                )
                chord_quality_radio = gr.Radio(
                    choices=["基本", "7", "maj7", "sus4", "add9"],
                    value="基本", label="延伸音", scale=3,
                )
                barline_btn = gr.Button("| 小節線", size="sm", scale=1)
                chord_preview = gr.Audio(
                    label="", type="filepath",
                    show_download_button=False, autoplay=True, scale=3,
                )
            _init_chords = get_diatonic_chords("G")
            with gr.Row(elem_classes="chord-palette"):
                chord_btn_1 = gr.Button(_init_chords[0], size="sm")
                chord_btn_2 = gr.Button(_init_chords[1], size="sm")
                chord_btn_3 = gr.Button(_init_chords[2], size="sm")
                chord_btn_4 = gr.Button(_init_chords[3], size="sm")
                chord_btn_5 = gr.Button(_init_chords[4], size="sm")
                chord_btn_6 = gr.Button(_init_chords[5], size="sm")
                chord_btn_7 = gr.Button(_init_chords[6], size="sm")

            # ── 和弦輸入框 ────────────────────────────────────────────────
            chord_input = gr.Textbox(
                label="和弦進行（選填）— 用 | 分小節，同小節和弦平均分拍",
                placeholder="C Em7 | D | G/B | Em7 D",
                lines=2,
            )

            # ── 生成 + 輸出 ───────────────────────────────────────────────
            melody_btn = gr.Button("🎵 生成試聽", variant="primary", size="lg")
            melody_status = gr.Textbox(label="狀態", interactive=False)
            melody_output = gr.Audio(label="試聽音頻", type="filepath")

            # ── 格式說明 ──────────────────────────────────────────────────
            with gr.Accordion("📖 格式說明", open=False):
                gr.Markdown(JIANPU_HELP)

            # ── 事件綁定 ──────────────────────────────────────────────────
            melody_btn.click(
                fn=_gen_melody,
                inputs=[melody_input, melody_key, melody_bpm, melody_octave,
                        melody_timbre, chord_input, time_sig_radio],
                outputs=[melody_output, melody_status],
                api_name="gen_melody",
            )

            # Chord button labels update with key
            def _update_chord_btns(key):
                chords = get_diatonic_chords(key)
                return [gr.Button(value=c) for c in chords]

            melody_key.change(
                fn=_update_chord_btns,
                inputs=[melody_key],
                outputs=[chord_btn_1, chord_btn_2, chord_btn_3,
                         chord_btn_4, chord_btn_5, chord_btn_6, chord_btn_7],
            )

            # Chord buttons
            _chord_btns = [chord_btn_1, chord_btn_2, chord_btn_3,
                           chord_btn_4, chord_btn_5, chord_btn_6, chord_btn_7]
            for _btn in _chord_btns:
                _btn.click(
                    fn=on_chord_palette_btn,
                    inputs=[_btn, chord_input, chord_mode, chord_quality_radio],
                    outputs=[chord_preview, chord_input],
                )

            barline_btn.click(
                fn=add_barline_to_input,
                inputs=[chord_input],
                outputs=[chord_input],
            )

            # Toggle modifier buttons (sharp/high/low)
            mod_sharp.click(
                fn=toggle_sharp,
                inputs=[mod_state],
                outputs=[mod_state, mod_sharp],
            )
            mod_high.click(
                fn=toggle_high,
                inputs=[mod_state],
                outputs=[mod_state, mod_high, mod_low],
            )
            mod_low.click(
                fn=toggle_low,
                inputs=[mod_state],
                outputs=[mod_state, mod_high, mod_low],
            )

            # Note buttons (carry state, output updated state + reset sharp btn)
            _note_btns_digits = [
                (note_btn_1, "1"), (note_btn_2, "2"), (note_btn_3, "3"),
                (note_btn_4, "4"), (note_btn_5, "5"), (note_btn_6, "6"),
                (note_btn_7, "7"), (note_btn_0, "0"),
            ]
            for _nbtn, _digit in _note_btns_digits:
                _nbtn.click(
                    fn=_make_note_handler(_digit),
                    inputs=[melody_input, note_mode, melody_key,
                            melody_octave, melody_timbre, mod_state],
                    outputs=[note_preview, melody_input, mod_state,
                             mod_sharp, mod_high, mod_low],
                )

            # Direct-append modifiers
            mod_extend.click(
                fn=lambda t: append_melody_modifier(t, "-"),
                inputs=[melody_input], outputs=[melody_input],
            )
            mod_bar_m.click(
                fn=lambda t: append_melody_modifier(t, "|"),
                inputs=[melody_input], outputs=[melody_input],
            )

if __name__ == "__main__":
    demo.launch(inbrowser=True)
