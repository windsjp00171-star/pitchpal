"""音頻轉譜（粗稿）：旋律簡譜與和弦。"""
import librosa
import numpy as np

from synth import MELODY_KEY_ROOTS

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


