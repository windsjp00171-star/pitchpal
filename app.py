import gradio as gr
import librosa
import librosa.effects
import soundfile as sf
import numpy as np
import tempfile
import os

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


def detect_key(audio_path: str) -> str:
    y, sr = librosa.load(audio_path, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    # Krumhansl–Schmuckler key profiles
    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    major_scores = [
        np.corrcoef(np.roll(major_profile, i), chroma_mean)[0, 1]
        for i in range(12)
    ]
    minor_scores = [
        np.corrcoef(np.roll(minor_profile, i), chroma_mean)[0, 1]
        for i in range(12)
    ]

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
    """Return the pitch class (0–11) for a key string like 'G 大調'."""
    note = key_str.split()[0]
    # Normalise slash notation e.g. C#/Db → C#
    note = note.split("/")[0]
    name_map = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
                "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
                "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    return name_map[note]


def transpose_audio(audio_path: str, detected_key: str, target_key: str):
    if not audio_path:
        return None, "請先上傳音頻檔案。"
    if not detected_key:
        return None, "請先偵測原曲調性。"
    if not target_key:
        return None, "請選擇目標 Key。"

    src_semitone = key_to_semitone(detected_key)
    tgt_semitone = key_to_semitone(target_key)

    # Determine mode match (both major or both minor) to pick shortest path
    src_minor = "小調" in detected_key
    tgt_minor = "小調" in target_key

    steps = tgt_semitone - src_semitone
    # Always take the shortest chromatic interval (−6 to +6)
    if steps > 6:
        steps -= 12
    elif steps < -6:
        steps += 12

    if steps == 0:
        return audio_path, f"原曲已是 {target_key}，無需移調。"

    y, sr = librosa.load(audio_path, mono=False)
    if y.ndim == 1:
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=steps)
    else:
        # Stereo: process each channel
        y_shifted = np.stack([
            librosa.effects.pitch_shift(y[ch], sr=sr, n_steps=steps)
            for ch in range(y.shape[0])
        ])

    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)

    if y_shifted.ndim == 1:
        sf.write(out_path, y_shifted, sr)
    else:
        sf.write(out_path, y_shifted.T, sr)

    direction = f"+{steps}" if steps > 0 else str(steps)
    msg = f"移調完成：{detected_key} → {target_key}（{direction} 個半音）"
    return out_path, msg


def process_upload(audio_path: str):
    if not audio_path:
        return "", gr.update(choices=ALL_KEYS, value=None)
    key = detect_key(audio_path)
    return key, gr.update(choices=ALL_KEYS, value=key)


with gr.Blocks(title="音樂 Key 辨別與移調工具") as demo:
    gr.Markdown("# 🎵 音樂 Key 辨別與移調工具")
    gr.Markdown("上傳音頻，自動偵測調性，選擇目標 Key 後下載移調結果。")

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
            transpose_btn = gr.Button("開始移調", variant="primary")

        with gr.Column():
            status_box = gr.Textbox(label="狀態訊息", interactive=False)
            audio_output = gr.Audio(label="移調後音頻（點擊下載）", type="filepath")

    # Auto-detect key on upload
    audio_input.change(
        fn=process_upload,
        inputs=[audio_input],
        outputs=[detected_key_box, target_key_drop],
    )

    transpose_btn.click(
        fn=transpose_audio,
        inputs=[audio_input, detected_key_box, target_key_drop],
        outputs=[audio_output, status_box],
    )

if __name__ == "__main__":
    demo.launch(inbrowser=True)
