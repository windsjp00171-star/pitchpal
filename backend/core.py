import librosa
import librosa.effects
import numpy as np
import soundfile as sf
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
    "C#": "C#/Db", "D#": "D#/Eb", "F#": "F#/Gb",
    "G#": "G#/Ab", "A#": "A#/Bb",
}

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def detect_key(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)

    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                               2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                               2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    if np.allclose(chroma_mean, 0):
        return {"key": "C 大調", "confidence": 0.0}

    major_scores = [
        np.corrcoef(np.roll(major_profile, i), chroma_mean)[0, 1]
        for i in range(12)
    ]
    minor_scores = [
        np.corrcoef(np.roll(minor_profile, i), chroma_mean)[0, 1]
        for i in range(12)
    ]

    major_scores = [s if np.isfinite(s) else -np.inf for s in major_scores]
    minor_scores = [s if np.isfinite(s) else -np.inf for s in minor_scores]

    best_major = int(np.argmax(major_scores))
    best_minor = int(np.argmax(minor_scores))

    all_scores = major_scores + minor_scores
    best_score = max(all_scores)
    # 正規化信心度：把相關係數 (-1~1) 轉成 0~100%
    confidence = round(float((best_score + 1) / 2 * 100), 1)

    if major_scores[best_major] >= minor_scores[best_minor]:
        root = MAJOR_KEYS[best_major]
        display = KEY_DISPLAY.get(root, root)
        return {"key": f"{display} 大調", "confidence": confidence}
    else:
        root = MINOR_KEYS[best_minor]
        display = KEY_DISPLAY.get(root, root)
        return {"key": f"{display} 小調", "confidence": confidence}


def key_to_semitone(key_str: str) -> int:
    note = key_str.split()[0].split("/")[0]
    name_map = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
                "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
                "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    if note not in name_map:
        raise ValueError(f"未知音名：{note!r}（輸入：{key_str!r}）")
    return name_map[note]


def transpose_audio(audio_path: str, detected_key: str, target_key: str) -> str:
    src = key_to_semitone(detected_key)
    tgt = key_to_semitone(target_key)
    steps = tgt - src
    if steps > 6:
        steps -= 12
    elif steps < -6:
        steps += 12

    y, sr = librosa.load(audio_path, mono=False)

    if steps == 0:
        y_shifted = y
    elif y.ndim == 1:
        y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=steps)
    else:
        y_shifted = np.stack([
            librosa.effects.pitch_shift(y[ch], sr=sr, n_steps=steps)
            for ch in range(y.shape[0])
        ])

    fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    if y_shifted.ndim == 1:
        sf.write(out_path, y_shifted, sr)
    else:
        sf.write(out_path, y_shifted.T, sr)

    return out_path
