"""
BDD-style specs for pitchpal core logic.
Run: pytest tests/test_bdd.py -v
"""
import numpy as np
import pytest
from app import detect_key, key_to_semitone, transpose_audio


# ---------------------------------------------------------------------------
# Feature: key_to_semitone — 將調性字串轉換為 MIDI 半音數
# ---------------------------------------------------------------------------

class TestKeyToSemitone:
    """Given a key string (as produced by detect_key or the UI dropdown),
    When key_to_semitone() is called,
    Then it returns the correct semitone index (0=C … 11=B)."""

    @pytest.mark.parametrize("key_str, expected", [
        # 自然音
        ("C 大調",   0),
        ("D 大調",   2),
        ("E 大調",   4),
        ("F 大調",   5),
        ("G 大調",   7),
        ("A 大調",   9),
        ("B 大調",  11),
        # 升降記號（enharmonic 等值）
        ("C#/Db 大調", 1),
        ("D#/Eb 大調", 3),
        ("F#/Gb 大調", 6),
        ("G#/Ab 大調", 8),
        ("A#/Bb 大調", 10),
        # 小調應與同根音大調回傳相同半音數
        ("C 小調",   0),
        ("A 小調",   9),
        ("F#/Gb 小調", 6),
    ])
    def test_semitone_mapping(self, key_str, expected):
        assert key_to_semitone(key_str) == expected


# ---------------------------------------------------------------------------
# Feature: detect_key — 從音頻偵測調性
# ---------------------------------------------------------------------------

def _make_sine(freq_hz: float, sr: int = 22050, duration: float = 2.0) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq_hz * t).astype(np.float32)


def _write_wav(y: np.ndarray, sr: int, tmp_path) -> str:
    import soundfile as sf
    path = str(tmp_path / "test.wav")
    sf.write(path, y, sr)
    return path


class TestDetectKey:
    """Given an audio file,
    When detect_key() is called,
    Then it returns a string matching '<Note> 大調' or '<Note> 小調'."""

    def test_returns_string_format(self, tmp_path):
        # Given: a simple sine wave (C4 = 261.63 Hz)
        y = _make_sine(261.63)
        path = _write_wav(y, 22050, tmp_path)
        # When
        result = detect_key(path)
        # Then: format is '<something> 大調' or '<something> 小調'
        assert result.endswith("大調") or result.endswith("小調")

    def test_silent_audio_does_not_crash(self, tmp_path):
        # Given: silence (all zeros)
        y = np.zeros(22050 * 2, dtype=np.float32)
        path = _write_wav(y, 22050, tmp_path)
        # When / Then: should not raise; returns some valid key string
        result = detect_key(path)
        assert result.endswith("大調") or result.endswith("小調")

    def test_noise_audio_does_not_crash(self, tmp_path):
        # Given: white noise
        rng = np.random.default_rng(42)
        y = rng.uniform(-1, 1, 22050 * 2).astype(np.float32)
        path = _write_wav(y, 22050, tmp_path)
        # When / Then: should not raise
        result = detect_key(path)
        assert result.endswith("大調") or result.endswith("小調")


# ---------------------------------------------------------------------------
# Feature: transpose_audio — 移調邏輯
# ---------------------------------------------------------------------------

class TestTransposeAudio:
    """Given a valid audio file, a detected key, and a target key,
    When transpose_audio() is called,
    Then it returns (output_path, status_message) with correct behaviour."""

    def _make_wav(self, tmp_path) -> str:
        y = _make_sine(440.0)  # A4
        return _write_wav(y, 22050, tmp_path)

    # --- Guard clauses ---

    def test_missing_audio_returns_error(self, tmp_path):
        # Given: no audio path
        out, msg = transpose_audio("", "A 大調", "C 大調", "WAV")
        assert out is None
        assert "上傳" in msg

    def test_missing_detected_key_returns_error(self, tmp_path):
        path = self._make_wav(tmp_path)
        out, msg = transpose_audio(path, "", "C 大調", "WAV")
        assert out is None
        assert "偵測" in msg

    def test_missing_target_key_returns_error(self, tmp_path):
        path = self._make_wav(tmp_path)
        out, msg = transpose_audio(path, "A 大調", "", "WAV")
        assert out is None
        assert "選擇" in msg

    # --- Same key → no transposition ---

    def test_same_key_outputs_file_and_zero_step_message(self, tmp_path):
        # Given: detected == target
        path = self._make_wav(tmp_path)
        out, msg = transpose_audio(path, "A 大調", "A 大調", "WAV")
        # Then: file is produced, message mentions no transposition
        assert out is not None
        assert "無需移調" in msg or "0" in msg

    # --- Semitone wrap logic ---

    @pytest.mark.parametrize("src, tgt, expected_steps", [
        # C→G raw=+7, wrap to -5 (shorter path downward)
        ("C 大調",  "G 大調",  -5),
        # Downward wrap: C → G# is +8 raw → should wrap to -4
        ("C 大調",  "G#/Ab 大調", -4),
        # Boundary: tritone (6 semitones) — no wrap, stays +6
        ("C 大調",  "F#/Gb 大調",  6),
        # Downward within -6
        ("G 大調",  "D 大調",  -5),
    ])
    def test_semitone_step_calculation(self, src, tgt, expected_steps, tmp_path):
        # Given: known src/tgt keys; When: transpose_audio runs
        path = self._make_wav(tmp_path)
        out, msg = transpose_audio(path, src, tgt, "WAV")
        # Then: message contains the expected step count
        assert out is not None
        if expected_steps == 0:
            assert "無需移調" in msg
        else:
            sign = "+" if expected_steps > 0 else ""
            assert f"{sign}{expected_steps}" in msg

    # --- Output file is valid WAV ---

    def test_wav_output_is_readable(self, tmp_path):
        import soundfile as sf
        path = self._make_wav(tmp_path)
        out, _ = transpose_audio(path, "A 大調", "C 大調", "WAV")
        assert out is not None
        data, sr = sf.read(out)
        assert sr == 22050
        assert len(data) > 0
