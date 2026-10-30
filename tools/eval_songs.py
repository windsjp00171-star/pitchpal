"""用自己的歌檢查調性與 BPM 的偵測結果。

用法：
    python tools/eval_songs.py 歌曲資料夾 答案.csv

答案.csv 每首一列（第一列是標題）：
    檔名,調性,BPM,備註
    song01.mp3,G 大調,72,
    song02.mp3,E minor,128,有轉調

調性可寫「G 大調」「E 小調」「G major」「E minor」「Em」「F#m」；BPM 可留空。
輸出逐首對照，不算準確率（首數少時百分比沒有意義）。
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import analysis  # noqa: E402

FLAT = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}


def parse_key(text):
    """回傳 (主音 0-11, '大調'|'小調')，看不懂就回傳 None。"""
    m = re.match(r"\s*([A-Ga-g])([#b♯♭]?)\s*(.*)", text or "")
    if not m:
        return None
    note = m.group(1).upper() + m.group(2).replace("♯", "#").replace("♭", "b")
    note = FLAT.get(note, note)
    if note not in analysis.NOTE_NAMES:
        return None
    rest = m.group(3).lower()
    minor = rest.startswith(("小", "m", "minor")) and not rest.startswith(("maj", "major", "大"))
    return analysis.NOTE_NAMES.index(note), "小調" if minor else "大調"


def key_relation(est, truth):
    (er, em), (tr, tm) = est, truth
    if (er, em) == (tr, tm):
        return "完全正確"
    if em == tm and (er - tr) % 12 in (5, 7):
        return "差一個五度"
    rel = ((tr + 9) % 12, "小調") if tm == "大調" else ((tr + 3) % 12, "大調")
    if (er, em) == rel:
        return "相對大小調"
    if er == tr:
        return "同主音但大小調相反"
    return "其他"


def bpm_relation(est, truth, alts):
    if abs(est - truth) <= 0.04 * truth:
        return "正確"
    for c in alts:
        if abs(c - truth) <= 0.04 * truth:
            return "在「也可能是」裡"
    for k, name in ((2, "報成一半（真實是它的兩倍）"), (0.5, "報成兩倍（真實是它的一半）")):
        if abs(est * k - truth) <= 0.04 * truth:
            return name
    return "其他"


def main(folder, csv_path):
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"{'檔名':24s} {'答案':10s} {'偵測':12s} {'把握':>4s}  調性判斷 / BPM（答案→偵測）")
    for r in rows:
        name = (r.get("檔名") or "").strip()
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            print(f"{name:24s} 找不到檔案")
            continue
        truth = parse_key(r.get("調性"))
        key, bpm = analysis.analyze(path)
        k_rel = key_relation((key.root, key.mode), truth) if truth else "（答案看不懂）"
        want = float(r["BPM"]) if (r.get("BPM") or "").strip() else None
        b_txt = "—"
        if want and bpm:
            b_txt = f"{bpm_relation(bpm.bpm, want, bpm.alternatives)}（{want:g}→{bpm.bpm}，也可能 {bpm.alternatives or '無'}）"
        t_txt = analysis.key_label(*truth) if truth else r.get("調性", "")
        print(f"{name:24s} {t_txt:10s} {key.name:12s} {key.confidence:3d}%  {k_rel} / {b_txt}  {r.get('備註') or ''}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
