"""Capo 建議畫成吉他指板圖：夾在第幾格、用哪個指型、手指按哪裡。"""
import re

# 開放和弦指型：六弦（低 E → 高 e）每條弦按第幾格；-1 = 不彈，0 = 空弦
SHAPES = {
    "C": (-1, 3, 2, 0, 1, 0),
    "D": (-1, -1, 0, 2, 3, 2),
    "E": (0, 2, 2, 1, 0, 0),
    "G": (3, 2, 0, 0, 0, 3),
    "A": (-1, 0, 2, 2, 2, 0),
}
_LINE = re.compile(r"(?:Capo\s*(\d+)|不夾\s*Capo)\s*[→\->]+\s*用\s*([A-G])\s*指型")

SX, SY = 18, 22        # 弦距、格距
LEFT, TOP = 22, 34     # 指板左上角


def parse_capo_text(text: str) -> list[tuple[int, str]]:
    """把 capo_box 的文字解析成 [(capo 格數, 指型)]，最多取三個。"""
    out = []
    for line in (text or "").splitlines():
        m = _LINE.search(line)
        if m and m.group(2) in SHAPES:
            out.append((int(m.group(1) or 0), m.group(2)))
    return out[:3]


def _one(capo: int, shape: str) -> str:
    w = LEFT + SX * 5 + 22
    h = TOP + SY * 4 + 30
    frets = SHAPES[shape]
    parts = []
    # 琴格線與弦
    for r in range(5):
        parts.append(f'<line x1="{LEFT}" y1="{TOP + r * SY}" x2="{LEFT + SX * 5}" y2="{TOP + r * SY}" stroke="#16130f" stroke-width="{3.5 if r == 0 and capo == 0 else 1.5}"/>')
    for s in range(6):
        parts.append(f'<line x1="{LEFT + s * SX}" y1="{TOP}" x2="{LEFT + s * SX}" y2="{TOP + SY * 4}" stroke="#16130f" stroke-width="1.6"/>')
    # Capo 橫桿
    if capo:
        parts.append(f'<rect x="{LEFT - 7}" y="{TOP - 9}" width="{SX * 5 + 14}" height="14" rx="7" fill="#C8321A"/>')
    # 手指
    for s, f in enumerate(frets):
        x = LEFT + s * SX
        if f == -1:
            parts.append(f'<path d="M{x - 4} {TOP - 24} l8 8 m0 -8 l-8 8" stroke="#16130f" stroke-width="2" fill="none"/>')
        elif f == 0:
            parts.append(f'<circle cx="{x}" cy="{TOP - 20}" r="4.5" fill="none" stroke="#16130f" stroke-width="2"/>')
        else:
            parts.append(f'<circle cx="{x}" cy="{TOP + (f - 0.5) * SY}" r="7.5" fill="#16130f"/>')
    title = "不夾 Capo" if capo == 0 else f"夾第 {capo} 格"
    return (
        f'<figure class="pp-fret"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{title}，彈 {shape} 指型">'
        + "".join(parts) + "</svg>"
        f'<figcaption><strong>{title}</strong><br>彈 {shape} 指型</figcaption></figure>'
    )


def capo_html(text: str) -> str:
    items = parse_capo_text(text)
    if not items:
        return ""
    return '<div class="pp-frets">' + "".join(_one(c, s) for c, s in items) + "</div>"
