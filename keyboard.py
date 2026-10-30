"""把「某個調」畫成一個八度的琴鍵：音階內的音塗色，主音實心。"""
from keys import NOTE_MAP

_MAJOR = (0, 2, 4, 5, 7, 9, 11)
_MINOR = (0, 2, 3, 5, 7, 8, 10)          # 自然小調
_WHITE_PCS = (0, 2, 4, 5, 7, 9, 11)      # C D E F G A B
_WHITE_NAMES = ("C", "D", "E", "F", "G", "A", "B")
_BLACK = ((1, 0.68), (3, 1.68), (6, 3.68), (8, 4.68), (10, 5.68))  # (音高類別, 以白鍵寬為單位的中心位置)

W, H = 56, 150          # 單一白鍵寬、琴鍵高（SVG 單位）
BW, BH = 36, 92         # 黑鍵


def _parse(key_str: str):
    parts = (key_str or "").split()
    if len(parts) < 2:
        return None
    note = parts[0].split("/")[0]
    if note not in NOTE_MAP:
        return None
    return NOTE_MAP[note], parts[1]


def _signature(root: int, mode: str) -> str:
    """調號：升降記號的數量（以五度圈位置推算）。"""
    major_root = root if mode == "大調" else (root + 3) % 12
    fifths = (major_root * 7) % 12          # 0..11，沿五度圈往升號方向走的步數
    if fifths == 0:
        return "沒有升降記號"
    if fifths <= 6:
        return f"{fifths} 個升記號"
    return f"{12 - fifths} 個降記號"


def keyboard_html(key_str: str, color: str, caption: str) -> str:
    """回傳 gr.HTML 用的字串。color 為音階與主音的顏色。"""
    parsed = _parse(key_str)
    scale = set()
    root = None
    if parsed:
        root, mode = parsed
        scale = {(root + i) % 12 for i in (_MAJOR if mode == "大調" else _MINOR)}

    keys, labels, blacks = [], [], []
    for i, pc in enumerate(_WHITE_PCS):
        x = i * W
        in_scale = bool(parsed) and pc in scale
        is_root = bool(parsed) and pc == root
        fill, opacity = ("#ffffff", 1)
        if is_root:
            fill = color
        elif in_scale:
            fill, opacity = color, 0.22
        keys.append(
            f'<rect x="{x}" y="0" width="{W}" height="{H}" rx="4" fill="#ffffff" stroke="#16130f" stroke-width="2.5"/>'
            f'<rect x="{x}" y="0" width="{W}" height="{H}" rx="4" fill="{fill}" fill-opacity="{opacity if (is_root or in_scale) else 0}"/>'
        )
        txt = "#fff" if is_root else ("#16130f" if in_scale else "#6b645c")
        labels.append(
            f'<text x="{x + W / 2}" y="{H - 14}" text-anchor="middle" font-size="19" '
            f'font-weight="{800 if in_scale else 500}" fill="{txt}">{_WHITE_NAMES[i]}</text>'
        )
    for pc, pos in _BLACK:
        cx = pos * W + W / 2
        in_scale = bool(parsed) and pc in scale
        is_root = bool(parsed) and pc == root
        blacks.append(
            f'<rect x="{cx - BW / 2}" y="0" width="{BW}" height="{BH}" rx="3" fill="#16130f" stroke="#16130f" stroke-width="2.5"/>'
        )
        if is_root:
            blacks.append(f'<circle cx="{cx}" cy="{BH - 18}" r="12" fill="#ffffff"/><circle cx="{cx}" cy="{BH - 18}" r="7" fill="{color}"/>')
        elif in_scale:
            blacks.append(f'<circle cx="{cx}" cy="{BH - 18}" r="6" fill="#ffffff"/>')
    svg = (
        f'<svg class="pp-kb-svg" viewBox="-3 -3 {7 * W + 6} {H + 6}" role="img" '
        f'aria-label="{caption}">' + "".join(keys) + "".join(labels) + "".join(blacks) + "</svg>"
    )
    cap = f"{caption}" + (f"：{_signature(root, mode)}" if parsed else "")
    return f'<div class="pp-kb"><div class="pp-kb-cap">{cap}</div>{svg}</div>'
