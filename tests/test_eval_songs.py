"""tools/eval_songs.py 的解析與對照。Run: pytest tests/test_eval_songs.py -v"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import eval_songs as E  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("G 大調", (7, "大調")), ("E minor", (4, "小調")), ("F#m", (6, "小調")), ("Bb", (10, "大調")),
    ("Ebm", (3, "小調")), ("e 小調", (4, "小調")), ("C Major", (0, "大調")), ("C major", (0, "大調")),
])
def test_parse_key(text, expected):
    assert E.parse_key(text) == expected


def test_parse_key_rejects_garbage():
    assert E.parse_key("亂寫") is None and E.parse_key("") is None


def test_key_relation():
    c = (0, "大調")
    assert E.key_relation(c, c) == "完全正確"
    assert E.key_relation((9, "小調"), c) == "相對大小調"
    assert E.key_relation((7, "大調"), c) == "差一個五度"
    assert E.key_relation((0, "小調"), c) == "同主音但大小調相反"


def test_bpm_relation():
    assert E.bpm_relation(100, 102, []) == "正確"
    assert E.bpm_relation(100, 200, [200]) == "在「也可能是」裡"
    assert "一半" in E.bpm_relation(70, 140, [])
    assert "兩倍" in E.bpm_relation(140, 70, [])
