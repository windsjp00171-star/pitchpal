import librosa
import numpy as np


SCALE_DEGREES = {
    0: '1', 1: '1#', 2: '2', 3: '2#', 4: '3', 5: '4',
    6: '4#', 7: '5', 8: '5#', 9: '6', 10: '6#', 11: '7',
}

KEY_SEMITONE = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
    'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11,
}

DIATONIC = [0, 2, 4, 5, 7, 9, 11]
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _midi_to_degree(midi: int, key_semi: int) -> str:
    pc = (midi - key_semi) % 12
    deg = SCALE_DEGREES.get(pc, '?')
    octave_offset = (midi - key_semi) // 12 - 4
    if octave_offset > 0:
        deg += "'" * octave_offset
    elif octave_offset < 0:
        deg += ',' * (-octave_offset)
    return deg


def _hz_to_midi(freq: float) -> int:
    return int(round(69 + 12 * np.log2(freq / 440.0)))


def transcribe_to_jianpu(audio_path: str, key: str = 'C', bpm: int = 80) -> dict:
    key_semi = KEY_SEMITONE.get(key.split('/')[0], 0)

    y, sr = librosa.load(audio_path, mono=True)
    hop_length = 512
    f0, voiced_flag, _ = librosa.pyin(
        y, sr=sr,
        fmin=librosa.note_to_hz('C2'),
        fmax=librosa.note_to_hz('C7'),
        hop_length=hop_length,
    )

    frame_duration = hop_length / sr
    quarter_sec = 60.0 / bpm
    sixteenth_sec = quarter_sec / 4
    frames_per_16th = max(1, int(round(sixteenth_sec / frame_duration)))

    # group consecutive same pitches
    notes_raw: list[tuple] = []
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

    tokens: list[str] = []
    beat_count = 0
    bar_beats = 4

    for midi_pitch, frames in notes_raw:
        sixteenths = max(1, int(round(frames / frames_per_16th)))
        # merge into quarter-note units
        quarters = max(1, round(sixteenths / 4))
        if midi_pitch is None:
            base = '0'
        else:
            base = _midi_to_degree(midi_pitch, key_semi)
        if quarters == 1:
            tok = base
        elif quarters == 2:
            tok = base + ' -'
        elif quarters >= 4:
            tok = base + ' - - -'
        else:
            tok = base + ' -' * (quarters - 1)

        for part in tok.split(' '):
            if beat_count > 0 and beat_count % bar_beats == 0:
                tokens.append('|')
            tokens.append(part)
            beat_count += 1

    melody_text = ' '.join(tokens)

    # simple chord estimation: chroma → diatonic chord per bar
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length * bar_beats)
    chords: list[str] = []
    for frame_idx in range(chroma.shape[1]):
        col = chroma[:, frame_idx]
        rotated = np.roll(col, -key_semi)
        scores = []
        for root in DIATONIC:
            third = (root + 4) % 12
            fifth = (root + 7) % 12
            scores.append(rotated[root] + rotated[third] * 0.8 + rotated[fifth] * 0.6)
        best = int(np.argmax(scores))
        note_name = NOTE_NAMES[(DIATONIC[best] + key_semi) % 12]
        # minor chords: degrees 2,3,6 in major scale (indices 1,2,5)
        suffix = 'm' if best in (1, 2, 5) else ''
        chords.append(note_name + suffix)

    chord_text = ' | '.join(chords) if chords else ''

    return {
        'melody': melody_text,
        'chords': chord_text,
        'key': key,
        'bpm': bpm,
    }
