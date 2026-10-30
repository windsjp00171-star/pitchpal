"""調性 / BPM 偵測的測試（合成音檔，不需要 Gradio）。
Run: pytest tests/test_analysis.py -v
"""
import os
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analysis  # noqa: E402

SR = 22050
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


def _tone(freq, dur, amp=1.0):
    t = np.arange(int(SR * dur)) / SR
    wave = sum(amp / h * np.sin(2 * np.pi * freq * h * t) for h in range(1, 6))
    return wave * np.exp(-1.5 * t / dur) * np.minimum(1, t / 0.01)


def _midi(m):
    return 440 * 2 ** ((m - 69) / 12)


def _song(root, mode, bpm, bars=8):
    """和弦 + 旋律 + 鼓點的簡單合成曲：大調 I-vi-IV-V，小調 i-VI-III-VII。"""
    rng = np.random.default_rng(root)
    scale = MAJOR if mode == "大調" else MINOR
    prog = [0, 5, 3, 4] if mode == "大調" else [0, 5, 2, 6]
    beat = 60 / bpm
    bar = beat * 4
    audio = np.zeros(int(SR * bar * bars) + SR)
    for b in range(bars):
        deg = prog[b % 4]
        pos = int(SR * bar * b)
        bass = _tone(_midi(36 + root + scale[deg]), bar, 1.2)
        audio[pos:pos + len(bass)] += bass * 0.5
        for off in (0, 2, 4):
            idx = deg + off
            note = scale[idx % 7] + (12 if idx >= 7 else 0)
            chord = _tone(_midi(60 + root + note), bar, 0.6)
            audio[pos:pos + len(chord)] += chord * 0.3
        for k in range(8):
            mel = _tone(_midi(72 + root + scale[rng.integers(0, 7)]), beat / 2)
            p = pos + int(SR * beat / 2 * k)
            audio[p:p + len(mel)] += mel[:len(audio) - p] * 0.25
    for i, p in enumerate(range(0, len(audio), int(SR * beat / 2))):
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        hit = (np.sin(2 * np.pi * (60 + 80 * np.exp(-t * 40)) * t) * np.exp(-t * 30)
               if i % 4 == 0 else rng.normal(size=n) * np.exp(-t * 80) * 0.4)
        e = min(len(audio), p + n)
        audio[p:e] += hit[:e - p] * 0.3
    audio += rng.normal(size=len(audio)) * 0.01
    return (audio / np.abs(audio).max() * 0.8).astype(np.float32)


def _write(tmp_path, y, name="t.wav"):
    path = str(tmp_path / name)
    sf.write(path, y, SR)
    return path


class TestDetectBpm:
    @pytest.mark.parametrize("bpm", [68, 84, 96, 128])
    def test_bpm_within_3_percent(self, tmp_path, bpm):
        path = _write(tmp_path, _song(0, "大調", bpm))
        assert abs(analysis.detect_bpm(path).bpm - bpm) / bpm < 0.03

    def test_slow_song_not_doubled(self, tmp_path):
        # 回歸：舊版 librosa beat_track 預設偏向 120，慢歌常被誤判成倍速
        path = _write(tmp_path, _song(5, "大調", 68))
        assert analysis.detect_bpm(path).bpm < 80

    def test_no_beat_raises(self, tmp_path):
        with pytest.raises(ValueError):
            analysis.estimate_bpm(np.zeros(SR * 3, dtype=np.float32), SR)


class TestDetectKey:
    @pytest.mark.parametrize("root,mode", [(0, "大調"), (7, "大調"), (2, "大調"), (9, "大調")])
    def test_major_key_or_relative_listed(self, tmp_path, root, mode):
        key = analysis.detect_key(_write(tmp_path, _song(root, mode, 90)))
        # 相對大小調（C 大調 / A 小調）音高集合相同，本來就可能互換；至少要列在候選裡
        candidates = [(key.root, key.mode)] + key.alternatives
        assert (root, mode) in candidates

    def test_tuning_offset_does_not_shift_key(self, tmp_path):
        import librosa
        y = _song(7, "大調", 90)
        shifted = librosa.effects.pitch_shift(y, sr=SR, n_steps=0.3)  # 偏高 30 音分（半個多 bin）
        key = analysis.detect_key(_write(tmp_path, shifted))
        assert (7, "大調") in [(key.root, key.mode)] + key.alternatives

    def test_confidence_is_not_always_100(self, tmp_path):
        # 回歸：舊公式信心度永遠飽和成 100
        noise = np.random.default_rng(0).normal(size=SR * 8).astype(np.float32) * 0.1
        key = analysis.detect_key(_write(tmp_path, noise))
        assert key.confidence < 50

    def test_label_format(self):
        assert analysis.key_label(1, "大調") == "C#/Db 大調"
        assert analysis.key_label(9, "小調") == "A 小調"

    def test_silence_raises(self, tmp_path):
        with pytest.raises(ValueError):
            analysis.detect_key(_write(tmp_path, np.zeros(SR * 2, dtype=np.float32)))


class TestKeyModel:
    def test_probabilities_sum_to_one(self):
        import numpy as np
        mid = np.array([5.0, 0.5, 3.0, 0.5, 4.0, 3.0, 0.5, 4.5, 0.5, 3.0, 0.5, 2.0])
        p = analysis._key_probabilities(mid / mid.sum(), mid / mid.sum(), mid / mid.sum())
        assert p.shape == (24,) and abs(p.sum() - 1) < 1e-9

    def test_flat_chroma_is_not_confident(self):
        import numpy as np
        flat = np.full(12, 1 / 12)
        assert analysis._key_probabilities(flat, flat, flat).max() < 0.2

    def test_clear_c_major_triad_scale(self):
        import numpy as np
        c = np.zeros(12)
        c[[0, 2, 4, 5, 7, 9, 11]] = [3, 1, 2, 1.5, 2.5, 1, 0.5]       # C 大調音階，主音最重
        c = c / c.sum()
        assert analysis._key_probabilities(c, c, c).argmax() in (0, 21)   # C 大調，或其相對小調 A 小調
