import gradio as gr
import librosa
import librosa.effects
import soundfile as sf
import numpy as np
import tempfile
import os
import shutil

MAJOR_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MINOR_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

ALL_KEYS = (
    [f"{k} 大調" for k in MAJOR_KEYS]
    + [f"{k} 小調" for k in MINOR_KEYS]
)

KEY_DISPLAY = {
    "C#": "C#/Db",
    "D#": "D#/Eb",
    "F#": "F#/Gb",
    "G#": "G#/Ab",
    "A#": "A#/Bb",
}

OUTPUT_FORMATS = ["WAV", "MP3", "MP4"]
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

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


def detect_key(audio_path: str):
    y, sr = librosa.load(audio_path, mono=True)
    if len(y) == 0:
        raise ValueError("音頻檔案為空或無法讀取。")

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

    # Confidence = how far the winner stands above the average of all other 23 keys
    all_scores = major_scores + minor_scores
    others = [s for s in all_scores if s != best_score]
    margin = best_score - float(np.mean(others))
    # A margin of 0.35+ is very distinct; below 0.1 is ambiguous
    confidence = int(min(100, max(0, margin / 0.35 * 100)))

    return key_str, confidence


def capo_suggestions(target_key_str: str) -> str:
    if not target_key_str:
        return ""
    try:
        target = _key_semitone(target_key_str)
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
        return "此 Key 無常用 Capo 組合（建議移調到較近的 Key）"
    return "\n".join(r[1] for r in results)


def _write_wav(y: np.ndarray, sr: int) -> str:
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(wav_path, y.T if y.ndim > 1 else y, sr)
    return wav_path


def _convert_with_pydub(wav_path: str, fmt: str) -> str:
    from pydub import AudioSegment
    audio = AudioSegment.from_wav(wav_path)
    fd, out_path = tempfile.mkstemp(suffix=f".{fmt.lower()}")
    os.close(fd)
    codec = "aac" if fmt == "MP4" else None
    audio.export(out_path, format=fmt.lower(), codec=codec)
    return out_path


def process_upload(audio_path: str):
    if not audio_path:
        return "", "—", gr.update(choices=ALL_KEYS, value=None), ""
    try:
        key, conf = detect_key(audio_path)
    except Exception as e:
        return f"偵測失敗：{e}", "—", gr.update(choices=ALL_KEYS, value=None), ""
    capo = capo_suggestions(key)
    return key, f"{conf}%", gr.update(choices=ALL_KEYS, value=key), capo


def on_target_change(target_key: str):
    return capo_suggestions(target_key)


def transpose_audio(audio_path, detected_key, target_key, output_fmt, progress=gr.Progress()):
    if not audio_path:
        return None, "請先上傳音頻檔案。"
    if not detected_key:
        return None, "請先偵測原曲調性。"
    if not target_key:
        return None, "請選擇目標 Key。"
    if output_fmt in ("MP3", "MP4") and not FFMPEG_AVAILABLE:
        return None, f"輸出 {output_fmt} 需要 ffmpeg，目前環境不支援。"

    wav_path = None
    try:
        progress(0.1, desc="載入音頻…")
        src = _key_semitone(detected_key)
        tgt = _key_semitone(target_key)
        steps = tgt - src
        if steps > 6:
            steps -= 12
        elif steps < -6:
            steps += 12

        y, sr = librosa.load(audio_path, mono=False)

        progress(0.3, desc="移調處理中…")
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
            wav_path = None  # ownership transferred, don't delete
        else:
            out_path = _convert_with_pydub(wav_path, output_fmt)

        progress(1.0, desc="完成！")
        direction = (f"+{steps}" if steps > 0 else str(steps)) if steps != 0 else "0"
        msg = (
            f"原曲已是 {target_key}，無需移調，已輸出為 {output_fmt}。"
            if steps == 0
            else f"移調完成：{detected_key} → {target_key}（{direction} 個半音）｜格式：{output_fmt}"
        )
        return out_path, msg

    except Exception as e:
        return None, f"處理失敗：{e}"
    finally:
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


with gr.Blocks(title="PitchPal — 音樂 Key 辨別與移調工具", css=CSS) as demo:
    gr.Markdown("# 🎵 PitchPal — 音樂 Key 辨別與移調工具")
    gr.Markdown("上傳音頻，自動偵測調性，選目標 Key 後下載移調結果。")

    with gr.Row():
        with gr.Column(scale=1):
            audio_input = gr.Audio(
                label="上傳音頻（mp3 / wav / m4a）",
                type="filepath",
                sources=["upload"],
            )
            with gr.Row():
                detected_key_box = gr.Textbox(
                    label="偵測到的原曲調性",
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
            target_key_drop = gr.Dropdown(
                label="目標 Key",
                choices=ALL_KEYS,
                value=None,
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
            audio_output = gr.Audio(label="移調後音頻（點擊下載）", type="filepath")

    audio_input.change(
        fn=process_upload,
        inputs=[audio_input],
        outputs=[detected_key_box, confidence_box, target_key_drop, capo_box],
    )

    target_key_drop.change(
        fn=on_target_change,
        inputs=[target_key_drop],
        outputs=[capo_box],
    )

    transpose_btn.click(
        fn=transpose_audio,
        inputs=[audio_input, detected_key_box, target_key_drop, output_fmt_radio],
        outputs=[audio_output, status_box],
    )

if __name__ == "__main__":
    demo.launch(inbrowser=True)
