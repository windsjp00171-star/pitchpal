"""
Self-test for PitchPal core logic.
Run with: python test_app.py
Requires: pip install -r requirements.txt
"""
import os
import sys
import tempfile
import traceback
import numpy as np

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def check(name, got, expected):
    ok = got == expected
    status = PASS if ok else FAIL
    print(f"  [{status}] {name}")
    if not ok:
        print(f"         got:      {got!r}")
        print(f"         expected: {expected!r}")
    results.append(ok)


def check_contains(name, got, substring):
    ok = substring in str(got)
    status = PASS if ok else FAIL
    print(f"  [{status}] {name}")
    if not ok:
        print(f"         got: {got!r}")
        print(f"         expected to contain: {substring!r}")
    results.append(ok)


def check_no_raise(name, fn):
    try:
        val = fn()
        print(f"  [{PASS}] {name} → {val!r}")
        results.append(True)
        return val
    except Exception as e:
        print(f"  [{FAIL}] {name}")
        print(f"         raised: {e}")
        results.append(False)
        return None


def check_raises(name, fn, exc_type=Exception):
    try:
        fn()
        print(f"  [{FAIL}] {name} (expected exception, got none)")
        results.append(False)
    except exc_type as e:
        print(f"  [{PASS}] {name} → raised {type(e).__name__}: {e}")
        results.append(True)
    except Exception as e:
        print(f"  [{FAIL}] {name} → wrong exception: {e}")
        results.append(False)


# ── Import ────────────────────────────────────────────────────────────────────
print("\n=== Import ===")
try:
    from app import (
        _key_semitone, result_key, capo_suggestions,
        _resolve_path, _prepare_audio, detect_key, _write_wav,
        MAX_AUDIO_MB, MAX_DURATION_SEC,
    )
    print(f"  [{PASS}] import app")
    results.append(True)
except Exception as e:
    print(f"  [{FAIL}] import app: {e}")
    results.append(False)
    sys.exit(1)


# ── _key_semitone ─────────────────────────────────────────────────────────────
print("\n=== _key_semitone ===")
check("C 大調 → 0",   _key_semitone("C 大調"),        0)
check("G 大調 → 7",   _key_semitone("G 大調"),        7)
check("C#/Db 大調 → 1", _key_semitone("C#/Db 大調"),  1)
check("A#/Bb 小調 → 10", _key_semitone("A#/Bb 小調"), 10)
check_raises("empty string raises", lambda: _key_semitone(""), ValueError)
check_raises("bad note raises",     lambda: _key_semitone("X 大調"), ValueError)


# ── result_key ────────────────────────────────────────────────────────────────
print("\n=== result_key ===")
check("C 大調 +2 → D 大調",      result_key("C 大調", 2),   "D 大調")
check("C 大調 -1 → B 大調",      result_key("C 大調", -1),  "B 大調")
check("A 大調 +3 → C 大調",      result_key("A 大調", 3),   "C 大調")
check("G 小調 +5 → C 小調",      result_key("G 小調", 5),   "C 小調")
check("C 大調 +12 → C 大調",     result_key("C 大調", 12),  "C 大調")
check("empty detected → ''",     result_key("", 3),          "")


# ── capo_suggestions ──────────────────────────────────────────────────────────
print("\n=== capo_suggestions ===")
check_contains("C 大調 contains 不夾 Capo", capo_suggestions("C 大調"), "不夾 Capo")
check_contains("G 大調 contains 不夾 Capo", capo_suggestions("G 大調"), "不夾 Capo")
check_contains("D 大調 contains 不夾 Capo", capo_suggestions("D 大調"), "不夾 Capo")
check_contains("F 大調 contains Capo",      capo_suggestions("F 大調"), "Capo")
check("empty key → ''", capo_suggestions(""), "")


# ── _resolve_path ─────────────────────────────────────────────────────────────
print("\n=== _resolve_path ===")
check("str passthrough",    _resolve_path("/tmp/foo.mp3"), "/tmp/foo.mp3")
check("dict with path",     _resolve_path({"path": "/a"}), "/a")
check("dict with name",     _resolve_path({"name": "/b"}), "/b")
check("None → None",        _resolve_path(None), None)

class _FakePath:
    path = "/fake/path.wav"

check("obj with .path",     _resolve_path(_FakePath()), "/fake/path.wav")


# ── _prepare_audio (size guard) ───────────────────────────────────────────────
print("\n=== _prepare_audio size guard ===")

def _make_tmp(size_bytes, ext=".mp3"):
    fd, path = tempfile.mkstemp(suffix=ext)
    os.write(fd, b"\x00" * size_bytes)
    os.close(fd)
    return path

small_mp3 = _make_tmp(1024, ".mp3")
big_mp3   = _make_tmp(int(MAX_AUDIO_MB * 1024 * 1024) + 1, ".mp3")
big_mp4   = _make_tmp(201 * 1024 * 1024, ".mp4")

try:
    check_no_raise("small audio passes size check",
                   lambda: _prepare_audio(small_mp3))
    check_raises("oversized audio raises",
                 lambda: _prepare_audio(big_mp3), ValueError)
    check_raises("oversized video raises",
                 lambda: _prepare_audio(big_mp4), ValueError)
finally:
    for p in (small_mp3, big_mp3, big_mp4):
        if os.path.exists(p):
            os.remove(p)


# ── detect_key + duration guard (needs librosa) ───────────────────────────────
print("\n=== detect_key (synthetic audio) ===")

def _make_sine_wav(freq=440.0, duration=3.0, sr=22050) -> str:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    y = (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)
    return _write_wav(y, sr)

sine_path = check_no_raise("generate 3s sine WAV", _make_sine_wav)
if sine_path:
    try:
        result = check_no_raise("detect_key on sine (any result ok)",
                                lambda: detect_key(sine_path))
        if result:
            key, conf = result
            check_contains("key string contains 調", key, "調")
            ok = 0 <= conf <= 100
            print(f"  [{'PASS' if ok else 'FAIL'}] confidence in 0–100 (got {conf})")
            results.append(ok)
    finally:
        if os.path.exists(sine_path):
            os.remove(sine_path)

# Duration guard
print("\n=== detect_key duration guard ===")

def _make_long_wav():
    sr = 22050
    samples = int((MAX_DURATION_SEC + 60) * sr)
    y = np.zeros(samples, dtype=np.float32)
    return _write_wav(y, sr)

long_path = check_no_raise("generate oversized WAV", _make_long_wav)
if long_path:
    try:
        check_raises("oversized audio raises ValueError",
                     lambda: detect_key(long_path), ValueError)
    finally:
        if os.path.exists(long_path):
            os.remove(long_path)


# ── Summary ───────────────────────────────────────────────────────────────────
total = len(results)
passed = sum(results)
print(f"\n{'='*40}")
print(f"結果：{passed}/{total} 通過", "✓" if passed == total else "✗ 有測試失敗")
print('='*40)
sys.exit(0 if passed == total else 1)
