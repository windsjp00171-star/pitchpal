import gradio as gr
import librosa
import librosa.effects
import soundfile as sf
import numpy as np
import subprocess
import tempfile
import os
import shutil

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
.gradio-container { max-width: 900px !important; margin: auto; }
#capo-box textarea { font-family: monospace; font-size: 0.95em; }
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
    if not file:
        return "", "—", "", ""
    file_path = _resolve_path(file)
    if not file_path:
        return "無法取得檔案路徑", "—", "", ""

    extracted = None
    try:
        audio_path, needs_cleanup = _prepare_audio(file_path)
        if needs_cleanup:
            extracted = audio_path
        key, conf = detect_key(audio_path)
    except Exception as e:
        return str(e), "—", "", ""
    finally:
        if extracted and os.path.exists(extracted):
            os.remove(extracted)

    rkey = result_key(key, 0)
    capo = capo_suggestions(rkey)
    return key, f"{conf}%", rkey, capo


def on_slider_change(detected_key: str, steps: int):
    rkey = result_key(detected_key, steps)
    capo = capo_suggestions(rkey)
    return rkey, capo


def _write_wav(y: np.ndarray, sr: int) -> str:
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(wav_path, y.T if y.ndim > 1 else y, sr)
    return wav_path


def _convert_to_mp3(wav_path: str) -> str:
    fd, out_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    subprocess.run(
        ["ffmpeg", "-i", wav_path, "-q:a", "2", out_path, "-y"],
        capture_output=True, check=True,
    )
    return out_path


def transpose_audio(file, detected_key, steps, output_fmt, progress=gr.Progress()):
    if not file:
        return None, "請先上傳音頻檔案。"

    file_path = _resolve_path(file)
    if not file_path:
        return None, "無法取得檔案路徑。"
    if output_fmt == "MP3" and not FFMPEG_AVAILABLE:
        return None, "輸出 MP3 需要 ffmpeg，目前環境不支援。"

    steps = int(steps)
    extracted = wav_path = None
    try:
        progress(0.1, desc="準備音頻…")
        audio_path, needs_cleanup = _prepare_audio(file_path)
        if needs_cleanup:
            extracted = audio_path

        progress(0.2, desc="載入音頻…")
        y, sr = librosa.load(audio_path, mono=False)

        duration = len(y) / sr if y.ndim == 1 else y.shape[1] / sr
        if duration > MAX_DURATION_SEC:
            return None, f"音頻長度 {duration/60:.1f} 分鐘，超過上限 {MAX_DURATION_SEC//60} 分鐘。"

        progress(0.35, desc="移調處理中…")
        if steps == 0:
            y_shifted = y
        else:
            if y.ndim == 1:
                y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=steps)
            else:
                y_shifted = np.stack([
                    librosa.effects.pitch_shift(y[ch], sr=sr, n_steps=steps)
                    for ch in range(y.shape[0])
                ])

        progress(0.85, desc="輸出檔案…")
        wav_path = _write_wav(y_shifted, sr)

        if output_fmt == "WAV":
            out_path = wav_path
            wav_path = None
        else:
            out_path = _convert_to_mp3(wav_path)

        progress(1.0, desc="完成！")
        direction = f"+{steps}" if steps > 0 else str(steps)
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


def _tone(freq: float, duration: float, sr: int = 22050) -> np.ndarray:
    n = int(sr * duration)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0, duration, n, endpoint=False)
    wave = (np.sin(2 * np.pi * freq * t) * 0.6
            + np.sin(2 * np.pi * freq * 2 * t) * 0.25
            + np.sin(2 * np.pi * freq * 3 * t) * 0.1)
    # ADSR envelope
    atk = min(int(0.01 * sr), n)
    rel = min(int(0.08 * sr), n)
    env = np.ones(n, dtype=np.float32)
    env[:atk] = np.linspace(0, 1, atk)
    env[n - rel:] *= np.linspace(1, 0, rel)
    return (wave * env * 0.5).astype(np.float32)


def _rest(duration: float, sr: int = 22050) -> np.ndarray:
    return np.zeros(int(sr * duration), dtype=np.float32)


def parse_and_synth(text: str, key: str, bpm: int, octave: int) -> str:
    sr = 22050
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
            segments.append(_tone(last_freq, beat * extra, sr))
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
        segments.append(_tone(freq, beat * (1 + extra_beats), sr))

    if not segments:
        raise ValueError("沒有解析到任何音符，請確認輸入格式。")

    audio = np.concatenate(segments)
    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(out_path, audio, sr)
    return out_path


JIANPU_HELP = """
**輸入格式說明**
| 輸入 | 意思 |
|---|---|
| `1` – `7` | 基本音（Do–Ti） |
| `4#` | 升半音（F# 等） |
| `1'` | 高八度 |
| `1,` | 低八度 |
| `1--` | 延音（共 3 拍） |
| `0` | 休止符 |
| `\|` | 小節線（忽略） |

**範例（遠超過諸天 Intro，A調）**
```
6 6 6 7 7 7 7 6 | 4# 4# 4# 2 2 2 1# 1#
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


def _gen_melody(text, key, bpm, octave):
    if not text or not text.strip():
        return None, "請先輸入旋律。"
    try:
        path = parse_and_synth(text, key, int(bpm), int(octave))
        return path, f"生成完成｜調性：{key}，BPM：{bpm}"
    except Exception as e:
        return None, f"生成失敗：{e}"


UPLOAD_NOTE = """
> **支援格式：** MP3、WAV、M4A、FLAC（上限 50 MB）｜MP4 影片（上限 200 MB，自動擷取音軌）
> **長度上限：** 10 分鐘｜建議上傳純音頻以加快處理速度
"""

with gr.Blocks(title="PitchPal — 音樂 Key 辨別與移調工具", css=CSS) as demo:
    gr.Markdown("# 🎵 PitchPal — 音樂 Key 辨別與移調工具")

    with gr.Tabs():

        # ── Tab 1：移調工具 ───────────────────────────────────────────────────
        with gr.Tab("🎚️ 移調工具"):
            gr.Markdown("上傳音頻，自動偵測調性，調整半音數後下載移調結果。")
            with gr.Row():
                with gr.Column(scale=1):
                    audio_input = gr.Audio(
                        label="上傳音頻（mp3 / wav / m4a / flac）",
                        type="filepath",
                        sources=["upload"],
                    )
                    gr.Markdown(UPLOAD_NOTE)
                    with gr.Row():
                        detected_key_box = gr.Textbox(
                            label="原曲調性",
                            interactive=False,
                            placeholder="上傳後自動顯示…",
                            scale=3,
                        )
                        confidence_box = gr.Textbox(
                            label="信心度",
                            interactive=False,
                            value="—",
                            scale=1,
                        )
                    steps_slider = gr.Slider(
                        label="移調半音數（負數 = 降Key，正數 = 升Key）",
                        minimum=-12,
                        maximum=12,
                        step=1,
                        value=0,
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
                    output_fmt_radio = gr.Radio(
                        label="輸出格式",
                        choices=OUTPUT_FORMATS,
                        value="WAV",
                    )
                    transpose_btn = gr.Button("開始移調", variant="primary", size="lg")

                with gr.Column(scale=1):
                    status_box = gr.Textbox(label="狀態訊息", interactive=False)
                    audio_output = gr.Audio(label="移調後音頻", type="filepath")

                    gr.Markdown("---")
                    gr.Markdown("""**偵測結果不正確？幫我們改善準確率 🙏**

每一筆回報都會被記錄下來，累積足夠數據後用來優化辨識演算法，讓工具對大家越來越準確。

_填入正確調性後按「回報修正」即可，不需要登入。_""")
                    feedback_key = gr.Dropdown(
                        label="正確調性",
                        choices=ALL_KEYS,
                        value=None,
                    )
                    feedback_notes = gr.Textbox(
                        label="備註（選填）",
                        placeholder="例如：這首歌有轉調…",
                        lines=1,
                    )
                    feedback_btn = gr.Button("回報修正", variant="secondary")
                    feedback_status = gr.Textbox(label="回報狀態", interactive=False)

            audio_input.change(
                fn=process_upload,
                inputs=[audio_input],
                outputs=[detected_key_box, confidence_box, result_key_box, capo_box],
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

        # ── Tab 2：旋律試聽 ───────────────────────────────────────────────────
        with gr.Tab("🎼 旋律試聽"):
            gr.Markdown("輸入簡譜數字，選調性與速度，生成旋律音頻確認音調。")
            with gr.Row():
                with gr.Column(scale=1):
                    melody_input = gr.Textbox(
                        label="輸入旋律（簡譜）",
                        placeholder="6 6 6 7 7 7 7 6 | 4# 4# 4# 2 2 2 1# 1#",
                        lines=4,
                    )
                    with gr.Row():
                        melody_key = gr.Dropdown(
                            label="調性（1 = ?）",
                            choices=MELODY_KEYS,
                            value="A",
                            scale=1,
                        )
                        melody_bpm = gr.Slider(
                            label="BPM",
                            minimum=40,
                            maximum=200,
                            step=1,
                            value=80,
                            scale=2,
                        )
                        melody_octave = gr.Slider(
                            label="八度（4 = 中央）",
                            minimum=2,
                            maximum=6,
                            step=1,
                            value=4,
                            scale=1,
                        )
                    melody_btn = gr.Button("生成旋律", variant="primary", size="lg")

                with gr.Column(scale=1):
                    gr.Markdown(JIANPU_HELP)
                    melody_status = gr.Textbox(label="狀態", interactive=False)
                    melody_output = gr.Audio(label="旋律音頻", type="filepath")

            melody_btn.click(
                fn=_gen_melody,
                inputs=[melody_input, melody_key, melody_bpm, melody_octave],
                outputs=[melody_output, melody_status],
                api_name="gen_melody",
            )

if __name__ == "__main__":
    demo.launch(ssr=False, inbrowser=True)
