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
