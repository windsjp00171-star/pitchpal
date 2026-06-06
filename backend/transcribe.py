import librosa
import numpy as np
import tempfile
import os
import subprocess
import shutil

LILYPOND_AVAILABLE = shutil.which("lilypond") is not None


def _hz_to_midi(freq: float) -> int:
    return int(round(69 + 12 * np.log2(freq / 440.0)))


def transcribe_to_pdf(audio_path: str, title: str = "", composer: str = "") -> tuple:
    if not LILYPOND_AVAILABLE:
        return None, "未偵測到 lilypond，請先安裝：sudo apt install lilypond"

    try:
        from music21 import stream, note, metadata as m21meta, tempo, meter
    except ImportError:
        return None, "請先安裝 music21：pip install music21"

    y, sr = librosa.load(audio_path, mono=True)
    hop_length = 512
    f0, voiced_flag, _ = librosa.pyin(
        y, sr=sr,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        hop_length=hop_length,
    )

    frame_duration = hop_length / sr
    notes_raw = []
    prev_midi = None
    run = 0
    for freq, voiced in zip(f0, voiced_flag):
        midi = _hz_to_midi(float(freq)) if (voiced and freq and freq > 0) else None
        if midi == prev_midi:
            run += 1
        else:
            if run > 0:
                notes_raw.append((prev_midi, run))
            prev_midi = midi
            run = 1
    if run > 0:
        notes_raw.append((prev_midi, run))

    bpm = 80
    quarter_sec = 60.0 / bpm
    sixteenth_sec = quarter_sec / 4
    frames_per_16th = max(1, int(round(sixteenth_sec / frame_duration)))

    part = stream.Part()
    part.insert(0, tempo.MetronomeMark(number=bpm))
    part.insert(0, meter.TimeSignature("4/4"))

    for midi_pitch, frames in notes_raw:
        sixteenths = max(1, int(round(frames / frames_per_16th)))
        ql = sixteenths * 0.25
        n = note.Rest(quarterLength=ql) if midi_pitch is None else note.Note(midi_pitch, quarterLength=ql)
        part.append(n)

    score = stream.Score()
    md = m21meta.Metadata()
    if title.strip():
        md.title = title.strip()
    if composer.strip():
        md.composer = composer.strip()
    score.insert(0, md)
    score.append(part)

    try:
        ly_path = score.write("lilypond")
        pdf_base = str(ly_path).replace(".ly", "")
        result = subprocess.run(
            ["lilypond", "--pdf", f"-o{pdf_base}", str(ly_path)],
            capture_output=True, text=True, timeout=120,
        )
        pdf_path = pdf_base + ".pdf"
        if result.returncode != 0 or not os.path.exists(pdf_path):
            return None, f"LilyPond 渲染失敗：{result.stderr[-300:]}"
    except subprocess.TimeoutExpired:
        return None, "LilyPond 渲染逾時（超過 120 秒）。"
    except Exception as e:
        return None, f"PDF 輸出失敗：{e}"
    finally:
        if "ly_path" in dir() and os.path.exists(str(ly_path)):
            os.remove(str(ly_path))

    return pdf_path, "轉譜完成"
