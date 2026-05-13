import gradio as gr
import librosa
import librosa.effects
import soundfile as sf
import numpy as np
import subprocess
import tempfile
import os
import shutil

MAJOR_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MINOR_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

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


def detect_key(audio_path: str):
    y, sr = librosa.load(audio_path, mono=True)
    if len(y) == 0:
        raise ValueError("音頻檔案為空或無法讀取。")

    duration = len(y) / sr
    if duration > MAX_DURATION_SEC:
        raise ValueError(f"音頻長度 {duration/60:.1f} 分鐘，超過上限 {MAX_DURATION_SEC//60} 分鐘。")

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    major_scores = [np.corrcoef(np.roll(major_profile, i), chroma_mean)[0, 1] for i in range(12)]
    minor_scores = [np.corrcoef(np.roll(minor_profile, i), chroma_mean)[0, 1] for i in range(12)]

    best_major_idx = int(np.argmax(major_scores))
    best_minor_idx = int(np.argmax(minor_scores))
    best_major_score = major_scores[best_major_idx]
    best_minor_score = minor_scores[best_minor_idx]

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

    all_scores = major_scores + minor_scores
    others = [s for s in all_scores if s != best_score]
    margin = best_score - float(np.mean(others))
    confidence = int(min(100, max(0, margin / 0.35 * 100)))

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


UPLOAD_NOTE = """
> **支援格式：** MP3、WAV、M4A、FLAC（上限 50 MB）｜MP4 影片（上限 200 MB，自動擷取音軌）
> **長度上限：** 10 分鐘｜建議上傳純音頻以加快處理速度
"""

with gr.Blocks(title="PitchPal — 音樂 Key 辨別與移調工具", css=CSS) as demo:
    gr.Markdown("# 🎵 PitchPal — 音樂 Key 辨別與移調工具")
    gr.Markdown("上傳音頻，自動偵測調性，調整半音數後下載移調結果。")

    with gr.Row():
        with gr.Column(scale=1):
            audio_input = gr.File(
                label="上傳音頻 / 影片",
                file_types=[".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac"],
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

    audio_input.change(
        fn=process_upload,
        inputs=[audio_input],
        outputs=[detected_key_box, confidence_box, result_key_box, capo_box],
    )

    steps_slider.change(
        fn=on_slider_change,
        inputs=[detected_key_box, steps_slider],
        outputs=[result_key_box, capo_box],
    )

    transpose_btn.click(
        fn=transpose_audio,
        inputs=[audio_input, detected_key_box, steps_slider, output_fmt_radio],
        outputs=[audio_output, status_box],
    )

if __name__ == "__main__":
    demo.launch(inbrowser=True)
