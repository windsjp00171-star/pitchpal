import gradio as gr
import librosa
import librosa.effects
import soundfile as sf
import numpy as np
import tempfile
import os
import shutil
import subprocess

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


def detect_key(audio_path: str) -> str:
    y, sr = librosa.load(audio_path, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    # Krumhansl–Schmuckler key profiles
    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    # Guard: silence or noise can produce NaN correlations; fall back to C 大調
    if np.allclose(chroma_mean, 0):
        return "C 大調"

    major_scores = [
        np.corrcoef(np.roll(major_profile, i), chroma_mean)[0, 1]
        for i in range(12)
    ]
    minor_scores = [
        np.corrcoef(np.roll(minor_profile, i), chroma_mean)[0, 1]
        for i in range(12)
    ]

    # Replace NaN (e.g. constant chroma) with -inf so argmax still works safely
    major_scores = [s if np.isfinite(s) else -np.inf for s in major_scores]
    minor_scores = [s if np.isfinite(s) else -np.inf for s in minor_scores]

    best_major = int(np.argmax(major_scores))
    best_minor = int(np.argmax(minor_scores))

    if major_scores[best_major] >= minor_scores[best_minor]:
        root = MAJOR_KEYS[best_major]
        display = KEY_DISPLAY.get(root, root)
        return f"{display} 大調"
    else:
        root = MINOR_KEYS[best_minor]
        display = KEY_DISPLAY.get(root, root)
        return f"{display} 小調"


def key_to_semitone(key_str: str) -> int:
    note = key_str.split()[0].split("/")[0]
    name_map = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
                "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
                "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    if note not in name_map:
        raise ValueError(f"未知音名：{note!r}（輸入：{key_str!r}）")
    return name_map[note]


def _write_wav(y_shifted: np.ndarray, sr: int) -> str:
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    if y_shifted.ndim == 1:
        sf.write(wav_path, y_shifted, sr)
    else:
        sf.write(wav_path, y_shifted.T, sr)
    return wav_path


def _convert_with_pydub(wav_path: str, fmt: str) -> str:
    from pydub import AudioSegment
    audio = AudioSegment.from_wav(wav_path)
    ext = fmt.lower()
    fd, out_path = tempfile.mkstemp(suffix=f".{ext}")
    os.close(fd)
    # MP4 audio uses codec aac inside mp4 container
    codec = "aac" if fmt == "MP4" else None
    try:
        audio.export(out_path, format=ext, codec=codec)
    except Exception as e:
        os.remove(wav_path)
        raise RuntimeError(f"格式轉換失敗（{fmt}）：{e}") from e
    os.remove(wav_path)
    return out_path


def transpose_audio(audio_path: str, detected_key: str, target_key: str, output_fmt: str):
    if not audio_path:
        return None, "請先上傳音頻檔案。"
    if not detected_key:
        return None, "請先偵測原曲調性。"
    if not target_key:
        return None, "請選擇目標 Key。"

    if output_fmt in ("MP3", "MP4") and not FFMPEG_AVAILABLE:
        return None, f"輸出 {output_fmt} 需要系統安裝 ffmpeg，請先安裝後再試。"

    src_semitone = key_to_semitone(detected_key)
    tgt_semitone = key_to_semitone(target_key)

    steps = tgt_semitone - src_semitone
    if steps > 6:
        steps -= 12
    elif steps < -6:
        steps += 12

    if steps == 0:
        # No transposition needed; still honour format conversion
        y, sr = librosa.load(audio_path, mono=False)
        y_shifted = y
    else:
        y, sr = librosa.load(audio_path, mono=False)
        if y.ndim == 1:
            y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=steps)
        else:
            y_shifted = np.stack([
                librosa.effects.pitch_shift(y[ch], sr=sr, n_steps=steps)
                for ch in range(y.shape[0])
            ])

    wav_path = _write_wav(y_shifted, sr)

    if output_fmt == "WAV":
        out_path = wav_path
    else:
        try:
            out_path = _convert_with_pydub(wav_path, output_fmt)
        except RuntimeError as e:
            return None, str(e)

    direction = (f"+{steps}" if steps > 0 else str(steps)) if steps != 0 else "0"
    msg = (
        f"原曲已是 {target_key}，無需移調，已轉換格式為 {output_fmt}。"
        if steps == 0
        else f"移調完成：{detected_key} → {target_key}（{direction} 個半音），格式：{output_fmt}"
    )
    return out_path, msg


def process_upload(audio_path: str):
    if not audio_path:
        return "", gr.update(choices=ALL_KEYS, value=None)
    key = detect_key(audio_path)
    return key, gr.update(choices=ALL_KEYS, value=key)


LILYPOND_AVAILABLE = shutil.which("lilypond") is not None


def _hz_to_midi(freq: float) -> int:
    return int(round(69 + 12 * np.log2(freq / 440.0)))


def transcribe_to_pdf(audio_path: str, title: str, composer: str) -> tuple:
    """音檔 → librosa pYIN 旋律追蹤 → music21 → LilyPond → PDF"""
    if not audio_path:
        return None, "請先上傳音頻檔案。"
    if not LILYPOND_AVAILABLE:
        return None, "未偵測到 lilypond，請先安裝：sudo apt install lilypond"

    try:
        from music21 import stream, note, metadata as m21meta, tempo, meter
    except ImportError:
        return None, "請先安裝 music21：pip install music21"

    # 1. 載入音頻，pYIN 追蹤基本頻率
    y, sr = librosa.load(audio_path, mono=True)
    hop_length = 512
    f0, voiced_flag, _ = librosa.pyin(
        y, sr=sr,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        hop_length=hop_length,
    )

    # 2. 將 frame-level f0 合併成音符（相鄰同音合併）
    frame_duration = hop_length / sr  # 秒/frame
    notes_raw = []  # [(midi_pitch, duration_in_frames)]
    prev_midi = None
    run = 0
    for freq, voiced in zip(f0, voiced_flag):
        if voiced and freq > 0:
            midi = _hz_to_midi(float(freq))
        else:
            midi = None  # 休止

        if midi == prev_midi:
            run += 1
        else:
            if prev_midi is not None or run > 0:
                notes_raw.append((prev_midi, run))
            prev_midi = midi
            run = 1
    if run > 0:
        notes_raw.append((prev_midi, run))

    # 3. 量化為最小音符單位（以 16 分音符為基準）
    # 預設 BPM=80，計算每 frame 的音符時值
    bpm = 80
    quarter_sec = 60.0 / bpm
    sixteenth_sec = quarter_sec / 4
    frames_per_16th = max(1, int(round(sixteenth_sec / frame_duration)))

    part = stream.Part()
    part.insert(0, tempo.MetronomeMark(number=bpm))
    part.insert(0, meter.TimeSignature("4/4"))

    for midi_pitch, frames in notes_raw:
        sixteenths = max(1, int(round(frames / frames_per_16th)))
        # music21 quarterLength: 1.0 = 四分音符, 0.25 = 十六分音符
        ql = sixteenths * 0.25
        if midi_pitch is None:
            n = note.Rest(quarterLength=ql)
        else:
            n = note.Note(midi_pitch, quarterLength=ql)
        part.append(n)

    score = stream.Score()
    md = m21meta.Metadata()
    if title.strip():
        md.title = title.strip()
    if composer.strip():
        md.composer = composer.strip()
    score.insert(0, md)
    score.append(part)

    # 4. music21 → LilyPond → PDF
    try:
        ly_path = score.write("lilypond")
        pdf_base = str(ly_path).replace(".ly", "")

        result = subprocess.run(
            ["lilypond", "--pdf", f"-o{pdf_base}", str(ly_path)],
            capture_output=True, text=True, timeout=120,
        )
        pdf_path = pdf_base + ".pdf"
        if result.returncode != 0 or not os.path.exists(pdf_path):
            return None, f"LilyPond 渲染失敗：{result.stderr[-500:]}"
    except subprocess.TimeoutExpired:
        return None, "LilyPond 渲染逾時（超過 120 秒）。"
    except Exception as e:
        return None, f"PDF 輸出失敗：{e}"
    finally:
        if "ly_path" in dir() and os.path.exists(str(ly_path)):
            os.remove(str(ly_path))

    return pdf_path, "轉譜完成，PDF 已產生。"


ffmpeg_note = "" if FFMPEG_AVAILABLE else "\n> ⚠️ 未偵測到 ffmpeg，MP3 / MP4 輸出暫不可用（請安裝 ffmpeg）。"
lilypond_note = "" if LILYPOND_AVAILABLE else "\n> ⚠️ 未偵測到 lilypond，轉譜功能暫不可用（請安裝 lilypond）。"

with gr.Blocks(title="音樂 Key 辨別與移調工具") as demo:
    gr.Markdown("# 🎵 音樂 Key 辨別與移調工具")

    with gr.Tabs():
        with gr.Tab("調性偵測 / 移調"):
            gr.Markdown(f"上傳音頻，自動偵測調性，選擇目標 Key 後下載移調結果。{ffmpeg_note}")

            with gr.Row():
                with gr.Column():
                    audio_input = gr.Audio(
                        label="上傳音頻（mp3 / wav / m4a）",
                        type="filepath",
                        sources=["upload"],
                    )
                    detected_key_box = gr.Textbox(
                        label="偵測到的原曲調性",
                        interactive=False,
                        placeholder="上傳後自動顯示…",
                    )
                    target_key_drop = gr.Dropdown(
                        label="目標 Key",
                        choices=ALL_KEYS,
                        value=None,
                    )
                    output_fmt_radio = gr.Radio(
                        label="輸出格式",
                        choices=OUTPUT_FORMATS,
                        value="WAV",
                    )
                    transpose_btn = gr.Button("開始移調", variant="primary")

                with gr.Column():
                    status_box = gr.Textbox(label="狀態訊息", interactive=False)
                    audio_output = gr.Audio(label="移調後音頻（點擊下載）", type="filepath")

            audio_input.change(
                fn=process_upload,
                inputs=[audio_input],
                outputs=[detected_key_box, target_key_drop],
            )
            transpose_btn.click(
                fn=transpose_audio,
                inputs=[audio_input, detected_key_box, target_key_drop, output_fmt_radio],
                outputs=[audio_output, status_box],
            )

        with gr.Tab("音檔轉譜（PDF）"):
            gr.Markdown(f"上傳音頻，自動辨識音符，輸出 PDF 樂譜。{lilypond_note}")
            gr.Markdown("> 適合旋律為主的詩歌錄音，複雜混音準確率較低。")

            with gr.Row():
                with gr.Column():
                    transcribe_audio = gr.Audio(
                        label="上傳音頻（mp3 / wav / m4a）",
                        type="filepath",
                        sources=["upload"],
                    )
                    score_title = gr.Textbox(label="樂譜標題（選填）", placeholder="例：Amazing Grace")
                    score_composer = gr.Textbox(label="作曲者（選填）", placeholder="例：John Newton")
                    transcribe_btn = gr.Button("開始轉譜", variant="primary")

                with gr.Column():
                    transcribe_status = gr.Textbox(label="狀態訊息", interactive=False)
                    pdf_output = gr.File(label="PDF 樂譜（點擊下載）")

            transcribe_btn.click(
                fn=transcribe_to_pdf,
                inputs=[transcribe_audio, score_title, score_composer],
                outputs=[pdf_output, transcribe_status],
            )

if __name__ == "__main__":
    demo.launch(inbrowser=True)
