"""琴鍵音階圖：調號與主音。Run: pytest tests/test_keyboard.py -v"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from keyboard import keyboard_html  # noqa: E402


def _caption(key):
    return re.search(r'pp-kb-cap">(.*?)<', keyboard_html(key, "#000", "音階")).group(1)


@pytest.mark.parametrize("key,sig", [
    ("C 大調", "沒有升降記號"), ("G 大調", "1 個升記號"), ("F 大調", "1 個降記號"),
    ("A#/Bb 大調", "2 個降記號"), ("A 小調", "沒有升降記號"), ("E 小調", "1 個升記號"),
    ("C#/Db 小調", "4 個升記號"),
])
def test_key_signature(key, sig):
    assert _caption(key).endswith(sig)


def test_empty_key_renders_without_signature():
    html = keyboard_html("", "#000", "音階")
    assert "<svg" in html and "記號" not in html


def test_unknown_key_does_not_crash():
    assert "<svg" in keyboard_html("—", "#000", "音階")


# ── 五線譜、指板、短音檔 ────────────────────────────────────────────────────────
from fretboard import capo_html, parse_capo_text  # noqa: E402
from notation import signature, staff_svg  # noqa: E402


@pytest.mark.parametrize("root,mode,expected", [
    (0, "大調", ("", 0)), (7, "大調", ("sharp", 1)), (10, "大調", ("flat", 2)),
    (9, "小調", ("", 0)), (4, "小調", ("sharp", 1)), (1, "小調", ("sharp", 4)),
])
def test_signature(root, mode, expected):
    assert signature(root, mode) == expected


def test_staff_has_clef_and_one_path_per_accidental():
    assert staff_svg(10, "大調", "#000").count("<path") == 1 + 2      # 譜號 + 兩個降記號
    assert staff_svg(0, "大調", "#000").count("<path") == 1           # 只有譜號


def test_parse_capo_text():
    text = "Capo 1  →  用 A 指型彈奏\nCapo 3  →  用 G 指型彈奏\n不夾 Capo  →  用 C 指型彈奏"
    assert parse_capo_text(text) == [(1, "A"), (3, "G"), (0, "C")]
    assert parse_capo_text("") == []
    assert capo_html("") == ""


def test_audio_helpers():
    import soundfile as sf
    from synth import click_audio, scale_audio
    y, sr = sf.read(click_audio(100))
    assert abs(len(y) / sr - 4.8) < 0.1          # 8 拍 @100 BPM
    assert scale_audio("C 大調") and scale_audio("—") is None and click_audio(0) is None
