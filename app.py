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
import threading
import base64
import io
import time
import atexit
from scipy.signal import butter, sosfilt, lfilter

# ── Temp file cleanup ────────────────────────────────────────────────────────
_tmp_lock = threading.Lock()
_tmp_paths: list[tuple[float, str]] = []   # (created_time, path)

def _reg_tmp(path: str) -> str:
    with _tmp_lock:
        _tmp_paths.append((time.time(), path))
    return path

def _sweep_tmp(max_age: float = 7200.0):
    cutoff = time.time() - max_age
    with _tmp_lock:
        survivors = []
        for ts, p in _tmp_paths:
            if ts < cutoff:
                try: os.remove(p)
                except OSError: pass
            else:
                survivors.append((ts, p))
        _tmp_paths[:] = survivors

@atexit.register
def _cleanup_all_tmp():
    with _tmp_lock:
        for _, p in _tmp_paths:
            try: os.remove(p)
            except OSError: pass

def _start_sweep_thread():
    def _loop():
        while True:
            time.sleep(3600)
            _sweep_tmp()
    t = threading.Thread(target=_loop, daemon=True)
    t.start()

_start_sweep_thread()

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
FFMPEG_CONVERT_EXTS = {".opus", ".ogg", ".webm", ".aac", ".wma", ".flac"}
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
/* Tabs */
.tab-nav button {
    border: 1px solid #d1d5db !important;
    border-radius: 8px 8px 0 0 !important;
    margin-right: 3px !important;
    box-shadow: 0 -1px 4px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04) !important;
    transition: box-shadow 0.12s, background 0.12s !important;
}
.tab-nav button:hover {
    box-shadow: 0 -2px 8px rgba(0,0,0,0.13), 0 1px 3px rgba(0,0,0,0.07) !important;
    background: #f9f6f0 !important;
}
.tab-nav button.selected {
    border-bottom-color: transparent !important;
    border-top: 2px solid #e6a817 !important;
    box-shadow: 0 -3px 10px rgba(230,168,23,0.18), 0 1px 0 #fff !important;
    background: #fff !important;
    font-weight: 700 !important;
}
/* Button shadows */
button.lg, button.primary {
    box-shadow: 0 3px 8px rgba(0,0,0,0.18), 0 1px 3px rgba(0,0,0,0.12) !important;
    transition: box-shadow 0.12s, transform 0.1s !important;
}
button.lg:hover, button.primary:hover {
    box-shadow: 0 5px 14px rgba(0,0,0,0.22), 0 2px 5px rgba(0,0,0,0.14) !important;
    transform: translateY(-1px) !important;
}
button.lg:active, button.primary:active {
    box-shadow: 0 1px 3px rgba(0,0,0,0.15) !important;
    transform: translateY(1px) !important;
}
footer { display: none !important; }
/* Mobile responsive */
@media (max-width: 768px) {
    .gradio-container { padding: 6px !important; }
    /* Stack two-column rows vertically */
    .gr-row { flex-wrap: wrap !important; }
    .gr-row > .gr-column { min-width: 100% !important; flex: 1 1 100% !important; }
    /* Palette buttons: wrap and shrink */
    .chord-palette, .note-palette, .mod-palette {
        flex-wrap: wrap !important;
        gap: 4px !important;
    }
    .chord-palette button { min-width: 44px !important; flex: 1 1 auto !important; }
    .note-palette button  { min-width: 36px !important; flex: 1 1 auto !important; }
    .mod-palette button   { min-width: 52px !important; flex: 1 1 auto !important; }
    /* Bigger touch targets */
    button { min-height: 40px !important; }
}
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

    if is_video or ext in FFMPEG_CONVERT_EXTS:
        if not FFMPEG_AVAILABLE:
            if is_video:
                raise ValueError("伺服器未安裝 ffmpeg，無法處理影片檔案。")
            # Fallback: let librosa try directly
            return file_path, False
        audio_path = _extract_audio_from_video(file_path)
        return audio_path, True

    return file_path, False


_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                       2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                       2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
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


def _ks_scores(chroma_mean: np.ndarray) -> tuple[list, list]:
    major = [np.corrcoef(np.roll(_KS_MAJOR, i), chroma_mean)[0, 1] for i in range(12)]
    minor = [np.corrcoef(np.roll(_KS_MINOR, i), chroma_mean)[0, 1] for i in range(12)]
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


def _conf_display(conf: int) -> str:
    if conf >= 70:
        return f"🟢 {conf}%"
    elif conf >= 40:
        return f"🟡 {conf}%"
    else:
        return f"🔴 {conf}%"


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
        return filename, key, _conf_display(conf), rkey, capo
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
    return _reg_tmp(wav_path)


def _convert_to_mp3(wav_path: str, stem: str = "audio") -> str:
    fd, out_path = tempfile.mkstemp(suffix=f"__{stem}.mp3")
    os.close(fd)
    subprocess.run(
        ["ffmpeg", "-i", wav_path, "-q:a", "2", out_path, "-y"],
        capture_output=True, check=True,
    )
    return _reg_tmp(out_path)


def transpose_audio(file, detected_key, steps, output_fmt, key_override="（使用自動偵測）"):
    if not file:
        return None, "請先上傳音頻檔案。"
    effective_key = detected_key if (not key_override or key_override == "（使用自動偵測）") else key_override

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
                ch, sr=sr, n_steps=steps, bins_per_octave=12)
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
        elif effective_key and not effective_key.startswith("偵測失敗"):
            rkey = result_key(effective_key, steps)
            src_label = effective_key + ("（手動修正）" if key_override and key_override != "（使用自動偵測）" else "")
            msg = f"移調完成：{src_label} → {rkey}（{direction} 個半音）｜格式：{output_fmt}"
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


JIANPU_HELP = """
---
**旋律：數字簡譜格式**

| 輸入 | 意思 | 例子 |
|---|---|---|
| `1` – `7` | Do Re Mi Fa Sol La Ti | `1 2 3` |
| `4#` | 升半音 | `4# 5 6` |
| `1'` | 高八度（加一撇） | `5 6 7 1'` |
| `1,` | 低八度（加一逗） | `3, 4, 5` |
| `1_` | 八分音符（半拍） | `6_ 6_ 6_ 7_` |
| `1__` | 十六分音符（¼拍） | `6__ 7__ 1_` |
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
        conf = int("".join(c for c in conf_str if c.isdigit()))
    except ValueError:
        conf = None
    return submit_feedback(filename, detected, corrected, conf, notes)


def _gen_melody(text, key, bpm, octave, timbre, chord_text, time_sig, metronome, metronome_vol):
    has_melody = bool(text and text.strip())
    has_chords = bool(chord_text and chord_text.strip())
    if not has_melody and not has_chords:
        return None, "請輸入旋律或和弦進行。"
    beats_per_bar = 3 if time_sig == "3/4" else 4
    try:
        path = parse_and_synth(text or "", key, int(bpm), int(octave), timbre,
                               chord_text or "", beats_per_bar, bool(metronome), float(metronome_vol))
        if has_melody and has_chords:
            suffix = "旋律 + 和弦"
        elif has_chords:
            suffix = "和弦進行"
        else:
            suffix = "旋律"
        return path, f"生成完成（{suffix}）｜{time_sig}，調性：{key}，BPM：{bpm}"
    except Exception as e:
        return None, f"生成失敗：{e}"


# ── 音頻轉譜 ──────────────────────────────────────────────────────────────────

_CHORD_TEMPLATES: dict[str, np.ndarray] = {}

def _build_chord_templates():
    qualities = {
        "":    [0, 4, 7],
        "m":   [0, 3, 7],
        "7":   [0, 4, 7, 10],
        "m7":  [0, 3, 7, 10],
        "maj7":[0, 4, 7, 11],
        "dim": [0, 3, 6],
        "sus4":[0, 5, 7],
        "sus2":[0, 2, 7],
    }
    roots = [("C",0),("C#",1),("D",2),("D#",3),("E",4),("F",5),
             ("F#",6),("G",7),("G#",8),("A",9),("A#",10),("B",11)]
    for root, semi in roots:
        for q, ivs in qualities.items():
            tmpl = np.zeros(12)
            for iv in ivs:
                tmpl[(semi + iv) % 12] = 1.0
            tmpl /= np.linalg.norm(tmpl)
            name = root + q
            _CHORD_TEMPLATES[name] = tmpl

_build_chord_templates()


def _midi_to_jianpu(midi: int, root_midi: int) -> str:
    diff = midi - root_midi
    oct_shift = 0
    while diff < 0:
        diff += 12; oct_shift -= 1
    while diff >= 12:
        diff -= 12; oct_shift += 1
    iv_to_digit = {0:"1",2:"2",4:"3",5:"4",7:"5",9:"6",11:"7"}
    # chromatic: snap to nearest scale tone
    snapped = min(iv_to_digit.keys(), key=lambda x: abs(x - diff))
    sharp = (diff not in iv_to_digit) and diff == snapped + 1
    digit = iv_to_digit[snapped]
    suffix = "#" if sharp else ""
    if oct_shift > 0:
        suffix += "'" * oct_shift
    elif oct_shift < 0:
        suffix += "," * (-oct_shift)
    return digit + suffix


def transcribe_audio(audio_path: str, key: str) -> tuple[str, str, str]:
    """音頻 → 旋律簡譜 + 和弦譜（粗稿）"""
    if not audio_path:
        return "", "", "請先上傳音頻。"
    try:
        y, sr = librosa.load(audio_path, mono=True, duration=120)
        root_midi = MELODY_KEY_ROOTS.get(key, 60)

        # ── 旋律：pyin 基頻偵測 ──
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"),
            sr=sr, hop_length=512,
        )
        hop_sec = 512 / sr
        notes = []
        prev_digit = None
        prev_dur = 0.0
        beat_sec = 0.5  # assume eighth note grid ~120bpm as default

        for freq, voiced in zip(f0, voiced_flag):
            if voiced and freq is not None and not np.isnan(freq):
                midi = int(round(librosa.hz_to_midi(freq)))
                digit = _midi_to_jianpu(midi, root_midi)
                if digit == prev_digit:
                    prev_dur += hop_sec
                else:
                    if prev_digit is not None:
                        beats = max(1, round(prev_dur / beat_sec))
                        ext = "-" * (beats - 1)
                        notes.append(prev_digit + ext)
                    prev_digit = digit
                    prev_dur = hop_sec
            else:
                if prev_digit is not None:
                    beats = max(1, round(prev_dur / beat_sec))
                    ext = "-" * (beats - 1)
                    notes.append(prev_digit + ext)
                    prev_digit = None
                    prev_dur = 0.0

        if prev_digit:
            beats = max(1, round(prev_dur / beat_sec))
            notes.append(prev_digit + "-" * (beats - 1))

        melody_text = " ".join(notes) if notes else "（未偵測到旋律）"

        # ── 和弦：每小節 chroma 模板比對 ──
        hop = 2048
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
        frames_per_bar = max(1, int(2.0 * sr / hop))  # ~2 sec per bar
        chord_bars = []
        for start in range(0, chroma.shape[1], frames_per_bar):
            chunk = chroma[:, start:start + frames_per_bar].mean(axis=1)
            norm = np.linalg.norm(chunk)
            if norm < 0.01:
                continue
            chunk /= norm
            best = max(_CHORD_TEMPLATES.items(), key=lambda kv: np.dot(kv[1], chunk))
            chord_bars.append(best[0])

        # Group into bars of 4
        chord_lines = []
        for i in range(0, len(chord_bars), 4):
            chord_lines.append(" | ".join(chord_bars[i:i+4]))
        chord_text = "\n".join(chord_lines) if chord_lines else "（未偵測到和弦）"

        return melody_text, chord_text, f"轉譜完成（調性：{key}）⚠️ 為粗稿，請手動校正"
    except Exception as e:
        return "", "", f"錯誤：{e}"


# ── 和弦調色盤 ────────────────────────────────────────────────────────────────

def _audio_html(path: str | None) -> str:
    if not path:
        return ""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    uid = os.urandom(4).hex()
    return (
        f'<audio id="pp{uid}" style="display:none">'
        f'<source src="data:audio/wav;base64,{b64}" type="audio/wav">'
        f'</audio>'
        f'<script>'
        f'(function(){{'
        f'  var a=document.getElementById("pp{uid}");'
        f'  if(a)a.play().catch(function(){{}});'
        f'}})();'
        f'</script>'
    )


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


def on_chord_palette_btn(chord_name: str, chord_text: str, mode: str, quality_mod: str):
    effective = _apply_quality_mod(chord_name, quality_mod)
    path = play_chord_audio(effective)
    if mode == "加入輸入框":
        sep = " " if chord_text.strip() else ""
        new_text = chord_text.rstrip() + sep + effective
    else:
        new_text = chord_text
    return path, new_text


def add_barline_to_input(chord_text: str) -> str:
    return chord_text.rstrip() + " |"


_MOD_INIT = {"sharp": False, "flat": False, "high": False, "low": False}


def _mod_sharp_btn(active: bool):
    return gr.Button("# 升 ✓" if active else "# 升",
                     variant="primary" if active else "secondary", size="sm")

def _mod_flat_btn(active: bool):
    return gr.Button("b 降 ✓" if active else "b 降",
                     variant="primary" if active else "secondary", size="sm")

def _mod_high_btn(active: bool):
    return gr.Button("' 高八 ✓" if active else "' 高八",
                     variant="primary" if active else "secondary", size="sm")

def _mod_low_btn(active: bool):
    return gr.Button(", 低八 ✓" if active else ", 低八",
                     variant="primary" if active else "secondary", size="sm")


def toggle_sharp(state: dict):
    new_s = not state["sharp"]
    new_state = {**state, "sharp": new_s, "flat": False if new_s else state["flat"]}
    return new_state, _mod_sharp_btn(new_state["sharp"]), _mod_flat_btn(new_state["flat"])


def toggle_flat(state: dict):
    new_f = not state["flat"]
    new_state = {**state, "flat": new_f, "sharp": False if new_f else state["sharp"]}
    return new_state, _mod_sharp_btn(new_state["sharp"]), _mod_flat_btn(new_state["flat"])


def toggle_high(state: dict):
    new_h = not state["high"]
    new_state = {**state, "high": new_h, "low": False if new_h else state["low"]}
    return new_state, _mod_high_btn(new_state["high"]), _mod_low_btn(new_state["low"])


def toggle_low(state: dict):
    new_l = not state["low"]
    new_state = {**state, "low": new_l, "high": False if new_l else state["high"]}
    return new_state, _mod_high_btn(new_state["high"]), _mod_low_btn(new_state["low"])


_CQ_LABELS = ["基本", "m 小調", "m7 小七", "7 藍調", "maj7 大七", "sus4 掛四", "sus2 掛二", "add9 加九", "dim 減"]


def _cq_btn(label: str, active: bool):
    return gr.Button(
        label + (" ✓" if active else ""),
        variant="primary" if active else "secondary", size="sm",
    )


def _make_cq_handler(selected: str):
    def _h(state):
        return [selected] + [_cq_btn(lbl, lbl == selected) for lbl in _CQ_LABELS]
    return _h


def _play_note_with_mods(note_digit: str, key: str, octave: int,
                         timbre: str, state: dict) -> str | None:
    if note_digit == "0" or note_digit not in JIANPU_INTERVALS:
        return None
    sharp = state.get("sharp", False)
    flat  = state.get("flat",  False)
    high  = state.get("high",  False)
    low   = state.get("low",   False)
    root_midi = MELODY_KEY_ROOTS.get(key, 60) + (int(octave) - 4) * 12
    semitone = JIANPU_INTERVALS[note_digit] + (1 if sharp else -1 if flat else 0)
    oct_shift = (1 if high else 0) - (1 if low else 0)
    midi = root_midi + semitone + oct_shift * 12
    freq = 440.0 * (2 ** ((midi - 69) / 12))
    sr = 44100
    audio = _tone(freq, 0.8, sr, timbre, _RNG)
    audio = _lowpass(audio, sr, cutoff=TIMBRE_CUTOFF.get(timbre, 8000.0))
    return _write_normalized(audio, sr)


def _make_note_handler(digit: str):
    def _h(melody_text, mode, key, octave, timbre, state):
        path = _play_note_with_mods(digit, key, int(octave), timbre, state)
        tok = "0" if digit == "0" else digit
        if digit != "0":
            if state.get("sharp"):   tok += "#"
            elif state.get("flat"):  tok += "b"
            if state.get("high"):    tok += "'"
            if state.get("low"):     tok += ","
        if mode == "加入輸入框":
            sep = " " if melody_text.strip() else ""
            new_text = melody_text.rstrip() + sep + tok
        else:
            new_text = melody_text
        return path, new_text
    return _h


def append_melody_modifier(melody_text: str, char: str) -> str:
    if char in ("-", "_", "__", "."):
        if not melody_text.strip():
            return melody_text
        return melody_text.rstrip() + char
    sep = " " if melody_text.strip() else ""
    return melody_text.rstrip() + sep + char


_YT_STRATEGIES = [
    ("tv_embedded", True),
    ("mweb",        True),
    ("ios",         False),
    ("android",     False),
    ("web",         False),
]

_YT_TIMEOUT_SEC = 90


def _yt_download_worker(url: str, opts: dict, result: list):
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(opts) as ydl:
            result.append((ydl.extract_info(url, download=True), None))
    except Exception as e:
        result.append((None, e))


def download_youtube(url: str, cookies_file: str | None = None):
    if not url or not url.strip():
        return None, "", "—", "—", "", "", "請輸入 YouTube 連結。"
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return None, "", "—", "—", "", "", "yt-dlp 未安裝，請聯絡管理員。"

    tmpdir = tempfile.mkdtemp()
    out_template = os.path.join(tmpdir, "%(id)s.%(ext)s")

    base_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        },
    }
    if cookies_file and os.path.exists(cookies_file):
        base_opts["cookiefile"] = cookies_file

    info = None
    last_err = None

    try:
        deadline = time.time() + _YT_TIMEOUT_SEC
        for client, skip_wp in _YT_STRATEGIES:
            if time.time() > deadline:
                last_err = Exception("整體下載超時（90 秒）")
                break
            extra: dict = {"extractor_args": {"youtube": {"player_client": [client]}}}
            if skip_wp:
                extra["extractor_args"]["youtube"]["skip"] = ["webpage"]
            opts = {**base_opts, **extra}
            result: list = []
            t = threading.Thread(target=_yt_download_worker, args=(url, opts, result), daemon=True)
            t.start()
            remaining = max(1.0, deadline - time.time())
            t.join(timeout=min(30.0, remaining))
            if result:
                got_info, err = result[0]
                if got_info is not None:
                    info = got_info
                    break
                last_err = err
            else:
                last_err = Exception(f"client={client} 無回應（超時）")

        if info is None:
            msg = str(last_err) if last_err else "未知錯誤"
            if "Sign in" in msg or "age" in msg.lower() or "login" in msg.lower():
                tip = "此影片需要登入或年齡限制，請上傳 cookies.txt 後再試。"
            elif "private" in msg.lower():
                tip = "此影片為私人影片，無法存取。"
            elif "geographic" in msg.lower() or "available" in msg.lower():
                tip = "此影片有地區限制，伺服器所在地無法存取。"
            elif "超時" in msg or "無回應" in msg:
                tip = "連線超時，YouTube 在雲端伺服器上有封鎖，建議直接上傳音檔。"
            else:
                tip = f"所有方式均失敗：{msg[:120]}"
            return None, "", "—", "—", "", "", f"❌ {tip}"

        title = info.get("title", "（未知）")
        duration = info.get("duration", 0)
        if duration and duration > 900:
            return None, "", "—", "—", "", "", f"影片超過 15 分鐘（{duration//60} 分），請改用較短片段。"

        audio_path = None
        for f in os.listdir(tmpdir):
            if f.endswith(".wav"):
                audio_path = os.path.join(tmpdir, f)
                break
        if not audio_path:
            return None, "", "—", "—", "", "", "音頻擷取失敗，請確認影片包含音軌。"

        _reg_tmp(audio_path)
        key, conf = detect_key(audio_path)
        rkey = result_key(key, 0)
        capo = capo_suggestions(rkey)
        return audio_path, title, key, _conf_display(conf), rkey, capo, f"✅ 完成：《{title}》｜偵測調性：{key}"

    except Exception as e:
        print(f"[pitchpal] download_youtube error:\n{traceback.format_exc()}")
        return None, "", "—", "—", "", "", f"下載失敗：{e}"
    finally:
        if info is None:
            shutil.rmtree(tmpdir, ignore_errors=True)



with gr.Blocks(title="PitchPal", css=CSS) as demo:
    gr.Markdown("""
<div style="background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);border-radius:12px;padding:22px 28px;margin-bottom:4px">
<h1 style="color:#f0c040;margin:0;font-size:1.8em;letter-spacing:0.04em">🎵 PitchPal</h1>
<p style="color:#a8c5e8;margin:6px 0 0;font-size:0.95em">調 KEY 工具 — 辨調、調 KEY、Capo 建議、旋律試聽，一站完成。</p>
</div>
""")

    with gr.Tabs():

        # ── Tab 1：調 KEY 工具 ──────────────────────────────────────────────────
        with gr.Tab("🎚️ 調 KEY 工具"):

            # ── 上排：音源 | 分析結果（並排） ───────────────────────────────
            with gr.Row(equal_height=False):

                # 左：音源
                with gr.Column(scale=5):
                    gr.Markdown("**📂 音源**", elem_classes="section-header")
                    audio_input = gr.Audio(
                        type="filepath",
                        sources=["upload"],
                        show_label=False,
                    )
                    gr.Markdown(
                        "<small>支援 MP3、WAV、M4A、FLAC、MP4、MKV｜音頻 50 MB / 影片 200 MB / 10 分鐘以內</small>",
                    )
                    with gr.Accordion("🔗 YouTube 連結（實驗性）", open=False):
                        gr.Markdown(
                            "<small>⚠️ 雲端伺服器 IP 常被 YouTube 封鎖，成功率約 40–60%，不穩定屬正常現象。"
                            "建議優先使用上方直接上傳音檔。</small>"
                        )
                        with gr.Row():
                            yt_url_box = gr.Textbox(
                                placeholder="https://www.youtube.com/watch?v=...",
                                show_label=False,
                                scale=4,
                            )
                            yt_btn = gr.Button("▶ 分析", variant="secondary", scale=1)
                        yt_status_box = gr.Textbox(
                            show_label=False, interactive=False,
                            placeholder="狀態…",
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
                            "<small>請確認你對該內容擁有合法授權（購買、CCLI 或版權方許可）。本工具僅供移調分析，授權責任由使用者自行承擔。</small>"
                        )

                # 右：分析結果
                with gr.Column(scale=5):
                    gr.Markdown("**🔍 分析結果**", elem_classes="section-header")
                    filename_box = gr.Textbox(
                        label="檔案 / 影片名稱",
                        interactive=False,
                        placeholder="上傳或下載後顯示…",
                    )
                    with gr.Row():
                        detected_key_box = gr.Textbox(
                            label="原曲調性（自動偵測）",
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
                    key_override = gr.Dropdown(
                        label="手動修正原 Key（偵測有誤時使用）",
                        choices=["（使用自動偵測）"] + ALL_KEYS,
                        value="（使用自動偵測）",
                    )
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

            # ── 下排：移調設定 | 音檔生成（並排） ──────────────────────────
            with gr.Row(equal_height=False):

                # 左：移調設定
                with gr.Column(scale=5):
                    gr.Markdown("**🎚️ 調 KEY 設定**", elem_classes="section-header")
                    steps_slider = gr.Slider(
                        label="移調半音數　　− 降調  ←  0  →  + 升調",
                        minimum=-12, maximum=12, step=1, value=0,
                    )
                    result_key_box = gr.Textbox(
                        label="移調後調性",
                        interactive=False,
                        placeholder="—",
                    )
                    capo_box = gr.Textbox(
                        label="🎸 Capo 建議（吉他）",
                        interactive=False,
                        lines=3,
                        elem_id="capo-box",
                    )

                # 右：音檔生成
                with gr.Column(scale=5):
                    gr.Markdown("**💾 音檔生成**", elem_classes="section-header")
                    output_fmt_radio = gr.Radio(
                        label="輸出格式",
                        choices=OUTPUT_FORMATS,
                        value="WAV",
                    )
                    transpose_btn = gr.Button(
                        "開始移調", variant="primary", size="lg",
                    )
                    status_box = gr.Textbox(
                        label="狀態", interactive=False, placeholder="移調完成後顯示…"
                    )
                    audio_output = gr.Audio(label="移調後音頻", type="filepath")

            # ── 事件綁定 ────────────────────────────────────────────────────
            yt_btn.click(
                fn=download_youtube,
                inputs=[yt_url_box, yt_cookies_file],
                outputs=[audio_input, filename_box, detected_key_box, confidence_box,
                         result_key_box, capo_box, yt_status_box],
                api_name="download_youtube",
                show_progress="minimal",
            )
            audio_input.change(
                fn=process_upload,
                inputs=[audio_input],
                outputs=[filename_box, detected_key_box, confidence_box,
                         result_key_box, capo_box],
                api_name="process_upload",
                show_progress="minimal",
            )
            def _on_slider_with_override(detected_key, steps, override):
                effective_key = detected_key if (not override or override == "（使用自動偵測）") else override
                return on_slider_change(effective_key, steps)

            steps_slider.change(
                fn=_on_slider_with_override,
                inputs=[detected_key_box, steps_slider, key_override],
                outputs=[result_key_box, capo_box],
                api_name="on_slider_change",
            )
            key_override.change(
                fn=_on_slider_with_override,
                inputs=[detected_key_box, steps_slider, key_override],
                outputs=[result_key_box, capo_box],
            )
            transpose_btn.click(
                fn=transpose_audio,
                inputs=[audio_input, detected_key_box, steps_slider, output_fmt_radio, key_override],
                outputs=[audio_output, status_box],
                api_name="transpose_audio",
                show_progress="minimal",
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

            # ── 範例（折疊在最上） ────────────────────────────────────────
            with gr.Accordion("📖 輸入範例 & 格式說明", open=False):
                gr.Markdown(JIANPU_HELP)

            # ── 步驟一：旋律 + 和弦並排 ──────────────────────────────────
            gr.Markdown(
                "<div style='color:#6b7280;font-size:0.85em;margin:10px 0 4px'>步驟一：填入旋律或和弦（兩者皆選填，可單獨使用）</div>"
            )
            with gr.Row(equal_height=False):

                # ── 旋律欄 ────────────────────────────────────────────────
                with gr.Column(scale=5):
                    gr.Markdown("**🎵 旋律**", elem_classes="section-header")
                    note_preview = gr.Audio(label="試音", autoplay=True, visible=True)
                    with gr.Row():
                        note_mode = gr.Radio(
                            choices=["只試音", "加入輸入框"], value="只試音",
                            show_label=False, scale=2,
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
                    gr.Markdown("<div style='font-size:0.72em;color:#9ca3af;margin:6px 0 2px'>半音</div>")
                    with gr.Row(elem_classes="mod-palette"):
                        mod_sharp = gr.Button("# 升",  size="sm", variant="secondary")
                        mod_flat  = gr.Button("b 降",  size="sm", variant="secondary")
                    gr.Markdown("<div style='font-size:0.72em;color:#9ca3af;margin:6px 0 2px'>八度</div>")
                    with gr.Row(elem_classes="mod-palette"):
                        mod_high  = gr.Button("' 高八", size="sm", variant="secondary")
                        mod_low   = gr.Button(", 低八", size="sm", variant="secondary")
                    gr.Markdown("<div style='font-size:0.72em;color:#9ca3af;margin:6px 0 2px'>時值</div>")
                    with gr.Row(elem_classes="mod-palette"):
                        mod_eighth  = gr.Button("_ 八分", size="sm")
                        mod_sixteen = gr.Button("__ 十六", size="sm")
                        mod_dot     = gr.Button(". 附點", size="sm")
                        mod_extend  = gr.Button("- 延音", size="sm")
                        mod_bar_m   = gr.Button("| 小節", size="sm")
                    melody_input = gr.Textbox(
                        label="數字簡譜",
                        placeholder="5 6 7 5 3 - - - | 7 5 6 -",
                        lines=3,
                    )
                    melody_clear = gr.Button("🗑 清空旋律", size="sm", variant="secondary")

                # ── 和弦欄 ────────────────────────────────────────────────
                with gr.Column(scale=5):
                    gr.Markdown("**🎸 和弦**", elem_classes="section-header")
                    chord_preview = gr.Audio(label="試音", autoplay=True, visible=True)
                    with gr.Row():
                        chord_mode = gr.Radio(
                            choices=["只試音", "加入輸入框"], value="只試音",
                            show_label=False, scale=2,
                        )
                    chord_quality_state = gr.State("基本")
                    gr.Markdown("<div style='font-size:0.72em;color:#9ca3af;margin:6px 0 2px'>和弦色彩</div>")
                    with gr.Row(elem_classes="mod-palette"):
                        cq_basic = gr.Button("基本 ✓",    size="sm", variant="primary")
                        cq_m     = gr.Button("m 小調",    size="sm", variant="secondary")
                        cq_m7    = gr.Button("m7 小七",   size="sm", variant="secondary")
                        cq_7     = gr.Button("7 藍調",    size="sm", variant="secondary")
                        cq_maj7  = gr.Button("maj7 大七", size="sm", variant="secondary")
                    with gr.Row(elem_classes="mod-palette"):
                        cq_sus4  = gr.Button("sus4 掛四", size="sm", variant="secondary")
                        cq_sus2  = gr.Button("sus2 掛二", size="sm", variant="secondary")
                        cq_add9  = gr.Button("add9 加九", size="sm", variant="secondary")
                        cq_dim   = gr.Button("dim 減",    size="sm", variant="secondary")
                    gr.Markdown("<div style='font-size:0.72em;color:#9ca3af;margin:6px 0 2px'>節拍</div>")
                    with gr.Row(elem_classes="mod-palette"):
                        barline_btn = gr.Button("| 小節線", size="sm")
                    _init_chords = get_diatonic_chords("G")
                    with gr.Row(elem_classes="chord-palette"):
                        chord_btn_1 = gr.Button(_init_chords[0], size="sm")
                        chord_btn_2 = gr.Button(_init_chords[1], size="sm")
                        chord_btn_3 = gr.Button(_init_chords[2], size="sm")
                        chord_btn_4 = gr.Button(_init_chords[3], size="sm")
                        chord_btn_5 = gr.Button(_init_chords[4], size="sm")
                        chord_btn_6 = gr.Button(_init_chords[5], size="sm")
                        chord_btn_7 = gr.Button(_init_chords[6], size="sm")
                    chord_input = gr.Textbox(
                        label="和弦進行（用 | 分小節）",
                        placeholder="C Em7 | D | G/B | Em7 D",
                        lines=3,
                    )
                    chord_clear = gr.Button("🗑 清空和弦", size="sm", variant="secondary")

            # ── 步驟二：設定 + 生成 ───────────────────────────────────────
            gr.Markdown(
                "<div style='color:#6b7280;font-size:0.85em;margin:14px 0 4px'>步驟二：設定參數後生成</div>"
            )
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
                    label="音色", choices=["鋼琴", "吉他", "長笛", "管風琴", "豎琴", "小提琴"], value="鋼琴", scale=1,
                )
                time_sig_radio = gr.Radio(
                    label="拍號", choices=["4/4", "3/4"], value="4/4", scale=1,
                )
                metronome_toggle = gr.Checkbox(label="節拍器", value=False, scale=1)
                metronome_vol = gr.Slider(
                    label="節拍器音量", minimum=0.05, maximum=0.6, step=0.05, value=0.18, scale=2,
                    visible=False,
                )
                metronome_toggle.change(
                    fn=lambda on: gr.update(visible=on),
                    inputs=[metronome_toggle],
                    outputs=[metronome_vol],
                )
            melody_btn = gr.Button("🎵 生成試聽", variant="primary", size="lg")
            melody_status = gr.Textbox(label="狀態", interactive=False)
            melody_output = gr.Audio(label="試聽音頻", type="filepath")

            # ── 事件綁定 ──────────────────────────────────────────────────
            melody_btn.click(
                fn=_gen_melody,
                inputs=[melody_input, melody_key, melody_bpm, melody_octave,
                        melody_timbre, chord_input, time_sig_radio, metronome_toggle, metronome_vol],
                outputs=[melody_output, melody_status],
                api_name="gen_melody",
                show_progress="minimal",
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
                    inputs=[_btn, chord_input, chord_mode, chord_quality_state],
                    outputs=[chord_preview, chord_input],
                )

            barline_btn.click(
                fn=add_barline_to_input,
                inputs=[chord_input],
                outputs=[chord_input],
            )

            # Chord quality toggle buttons (single-select)
            _cq_btns = [cq_basic, cq_m, cq_m7, cq_7, cq_maj7, cq_sus4, cq_sus2, cq_add9, cq_dim]
            _cq_outputs = [chord_quality_state] + _cq_btns
            for _lbl, _cqb in zip(_CQ_LABELS, _cq_btns):
                _cqb.click(
                    fn=_make_cq_handler(_lbl),
                    inputs=[chord_quality_state],
                    outputs=_cq_outputs,
                )

            # Toggle modifier buttons (sharp/flat/high/low)
            mod_sharp.click(
                fn=toggle_sharp,
                inputs=[mod_state],
                outputs=[mod_state, mod_sharp, mod_flat],
            )
            mod_flat.click(
                fn=toggle_flat,
                inputs=[mod_state],
                outputs=[mod_state, mod_sharp, mod_flat],
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

            # Note buttons
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
                    outputs=[note_preview, melody_input],
                )

            # Direct-append modifiers
            mod_eighth.click(
                fn=lambda t: append_melody_modifier(t, "_"),
                inputs=[melody_input], outputs=[melody_input],
            )
            mod_sixteen.click(
                fn=lambda t: append_melody_modifier(t, "__"),
                inputs=[melody_input], outputs=[melody_input],
            )
            mod_dot.click(
                fn=lambda t: append_melody_modifier(t, "."),
                inputs=[melody_input], outputs=[melody_input],
            )
            mod_extend.click(
                fn=lambda t: append_melody_modifier(t, "-"),
                inputs=[melody_input], outputs=[melody_input],
            )
            mod_bar_m.click(
                fn=lambda t: append_melody_modifier(t, "|"),
                inputs=[melody_input], outputs=[melody_input],
            )

            # Clear buttons
            melody_clear.click(fn=lambda: "", outputs=[melody_input])
            chord_clear.click(fn=lambda: "", outputs=[chord_input])

        with gr.Tab("🔍 音頻轉譜（實驗）"):
            gr.Markdown("## 🔍 音頻轉譜\n上傳音頻，自動產生旋律簡譜與和弦進行粗稿。\n\n> ⚠️ 此功能為**實驗性**，適合單聲部人聲或簡單樂器。輸出為粗稿，請手動校正後使用。")
            with gr.Row():
                with gr.Column():
                    transcribe_audio_input = gr.Audio(
                        label="上傳音頻", type="filepath", sources=["upload"],
                    )
                    transcribe_key = gr.Dropdown(
                        label="調性（歌曲的 Key）", choices=MELODY_KEYS, value="G",
                    )
                    transcribe_btn = gr.Button("🔍 開始轉譜", variant="primary")
                    transcribe_status = gr.Textbox(label="狀態", interactive=False)
                with gr.Column():
                    transcribe_melody_out = gr.Textbox(
                        label="旋律簡譜（粗稿）", lines=6, interactive=True,
                        placeholder="轉譜後顯示於此，可直接編輯…",
                    )
                    transcribe_chord_out = gr.Textbox(
                        label="和弦進行（粗稿）", lines=6, interactive=True,
                        placeholder="轉譜後顯示於此，可直接編輯…",
                    )
            transcribe_btn.click(
                fn=transcribe_audio,
                inputs=[transcribe_audio_input, transcribe_key],
                outputs=[transcribe_melody_out, transcribe_chord_out, transcribe_status],
            )

    gr.Markdown(
        "<div style='text-align:center;color:#9ca3af;font-size:0.82em;margin:22px 0 6px;'>"
        "🌿 PitchPal 是 EMMARK 作品集中的一個專案 · "
        "<a href='https://windsjp00171-star.github.io/CLAUDE-DESIGN/' target='_blank' style='color:#f5a623;text-decoration:none;'>查看更多作品 →</a>"
        "</div>"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    # ssr_mode=False：避免 gradio 5.x 在 slim 鏡像（無完整 Node 環境）啟動時
    #   卡在 SSR 子程序、不報錯也印不出 "Running on local URL"。
    # show_api=False：跳過容易出問題的 API schema 產生步驟（本工具用不到）。
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        ssr_mode=False,
        show_api=False,
    )

