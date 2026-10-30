"""調性與 BPM 偵測（不依賴 Gradio，可單獨測試）。"""
from dataclasses import dataclass, field

import librosa
import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# 調性模型：24 個候選調（C…B 大調、C…B 小調）各自對「中頻色度 + 低音色度」打分，再做 softmax。
# 權重由 GiantSteps 604 首真實錄音（EDM，附人工標註）學得；5 折交叉驗證（只看沒參與訓練的資料）：
#   完全命中 57.8%（舊的 Krumhansl-Schmuckler 輪廓：42.9%），正確答案在前三名的比例 78%。
# 模型輸出的最高機率可直接當把握度：說 85% 以上的實際命中 85%，不到 30% 的只有 24%。
# 權重形狀 (大調/小調, 24)：前 12 個對應中頻色度（旋轉到該候選主音後），後 12 個對應低音色度。
_W = np.array([
    [2.0644, -1.4964, 0.1570, -0.6184, 1.3329, -0.0664, -1.6552, 2.0172, -1.0932, 0.3014, -0.5392, -0.4041, 0.9143, -0.4898, 0.4643, -0.5924, -0.1130, 0.7116, -0.3212, 0.0503, 0.3597, -0.0401, -0.4601, -0.4835],
    [1.6271, -0.7464, -0.2288, 1.0703, -0.7525, -0.0971, -1.0338, 1.5485, -0.2613, -1.0569, 0.9319, -1.0010, 0.9869, -0.1455, -0.4611, -0.1531, 0.2124, -0.0302, 0.0920, -0.3546, 0.2386, -0.0776, -0.5021, 0.1943],
])
_B = np.array([-1.1405, 1.1405])

SR = 22050
MAX_ANALYSIS_SEC = 120   # 只分析中段最多 2 分鐘，控制運算時間

BPM_MIN, BPM_MAX = 50, 200
BPM_PRIOR_CENTER = 95    # 敬拜曲常見速度中心；只用來在倍速/半速之間取捨
BPM_PRIOR_SIGMA = 0.55   # 以 octave（2 倍）為單位


@dataclass
class KeyResult:
    root: int                 # 0=C … 11=B
    mode: str                 # "大調" / "小調"
    confidence: int           # 0-100
    alternatives: list = field(default_factory=list)  # [(root, mode), ...] 次佳候選

    @property
    def name(self) -> str:
        return key_label(self.root, self.mode)


@dataclass
class BpmResult:
    bpm: int
    alternatives: list = field(default_factory=list)  # 可能的半速/倍速


def key_label(root: int, mode: str) -> str:
    name = NOTE_NAMES[root]
    display = {"C#": "C#/Db", "D#": "D#/Eb", "F#": "F#/Gb",
               "G#": "G#/Ab", "A#": "A#/Bb"}.get(name, name)
    return f"{display} {mode}"


def load_audio(path: str, max_sec: int = MAX_ANALYSIS_SEC):
    """讀檔、轉單聲道、去掉首尾靜音；太長就取中段。"""
    y, sr = librosa.load(path, sr=SR, mono=True)
    if len(y) == 0:
        raise ValueError("音頻檔案為空或無法讀取。")
    if np.max(np.abs(y)) < 1e-4:
        raise ValueError("音頻檔案幾乎是靜音。")
    y, _ = librosa.effects.trim(y, top_db=30)
    if len(y) == 0:
        raise ValueError("音頻檔案幾乎是靜音。")
    cap = max_sec * sr
    if len(y) > cap:
        start = (len(y) - cap) // 2
        y = y[start:start + cap]
    return y, sr


# ── 調性 ──────────────────────────────────────────────────────────────────────

def _fold_chroma(chroma: np.ndarray) -> np.ndarray:
    """每個 frame 先正規化再依響度加權平均，避免靜音雜訊與少數爆音主導。"""
    energy = chroma.sum(axis=0)
    if energy.sum() <= 0:
        return np.zeros(12)
    weights = np.sqrt(energy)
    frames = chroma / (energy + 1e-9)
    return (frames * weights).sum(axis=1) / (weights.sum() + 1e-9)


def _chroma_profile(y_h: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """回傳 (中頻色度, 低音色度)。y_h 為和聲成分（已去掉鼓與打擊樂對音高的干擾）。"""
    # estimate_tuning 的單位是「一個 bin 的比例」；用 12 bins 估才涵蓋 ±半音，
    # 再換算成 36 bins/octave 的單位（1 半音 = 3 bins）餵給 chroma_cqt
    tuning_semitones = float(librosa.estimate_tuning(y=y_h, sr=sr, bins_per_octave=12))
    # 偏差不到半個 bin（約 1/6 半音）時音高仍落在同一格，估計值只會帶來雜訊，不校正
    if abs(tuning_semitones) < 0.17:
        tuning_semitones = 0.0
    kw = dict(y=y_h, sr=sr, tuning=tuning_semitones * 3, bins_per_octave=36, norm=None)
    mid = librosa.feature.chroma_cqt(**kw, fmin=librosa.note_to_hz("C2"), n_octaves=6)   # 略過會蓋掉音高的超低頻
    bass = librosa.feature.chroma_cqt(**kw, fmin=librosa.note_to_hz("C1"), n_octaves=2)  # 低音多半是和弦根音
    return _fold_chroma(mid), _fold_chroma(bass)


def _key_probabilities(mid: np.ndarray, bass: np.ndarray) -> np.ndarray:
    """24 個候選調的機率（前 12 個大調、後 12 個小調）。"""
    def norm(c):
        return c / (c.sum() + 1e-9) * 12 - 1
    mid, bass = norm(mid), norm(bass)
    scores = np.empty(24)
    for k in range(24):
        feat = np.concatenate([np.roll(mid, -(k % 12)), np.roll(bass, -(k % 12))])
        scores[k] = feat @ _W[k // 12] + _B[k // 12]
    scores -= scores.max()
    p = np.exp(scores)
    return p / p.sum()


def estimate_key(y: np.ndarray, sr: int, y_h: np.ndarray | None = None) -> KeyResult:
    if y_h is None:
        y_h = librosa.effects.harmonic(y, margin=1.0)
    mid, bass = _chroma_profile(y_h, sr)
    if mid.sum() <= 0:
        raise ValueError("音頻檔案幾乎是靜音。")
    p = _key_probabilities(mid, bass)
    order = np.argsort(p)[::-1]
    best = int(order[0])
    alternatives = [(int(i) % 12, "大調" if i < 12 else "小調") for i in order[1:3]]
    return KeyResult(best % 12, "大調" if best < 12 else "小調", int(round(100 * p[best])), alternatives)


def detect_key(audio_path: str) -> KeyResult:
    y, sr = load_audio(audio_path)
    return estimate_key(y, sr)


# ── BPM ───────────────────────────────────────────────────────────────────────

def _tempo_curve(y_p: np.ndarray, sr: int, hop: int = 512):
    """以打擊成分的 onset 強度做自相關，回傳 (bpm 陣列, 強度陣列)。"""
    onset = librosa.onset.onset_strength(y=y_p, sr=sr, hop_length=hop, aggregate=np.median)
    if onset.std() < 1e-9:
        return None, None
    onset = onset - onset.mean()
    ac = librosa.autocorrelate(onset, max_size=len(onset) // 2)
    ac = np.maximum(ac, 0)
    ac = ac / (ac[0] + 1e-9)

    lags = np.arange(len(ac))
    lags[0] = 1
    bpms = 60.0 * sr / (hop * lags)
    mask = (bpms >= BPM_MIN) & (bpms <= BPM_MAX)
    return bpms[mask][::-1], ac[mask][::-1]


def estimate_bpm(y: np.ndarray, sr: int, y_p: np.ndarray | None = None) -> BpmResult:
    if y_p is None:
        y_p = librosa.effects.percussive(y, margin=2.0)
    bpms, strength = _tempo_curve(y_p, sr)
    if bpms is None:
        raise ValueError("找不到明顯的節拍。")

    # 同一個節拍的倍數（半速/倍速）自相關也會高，用先驗分佈決定取哪個
    prior = np.exp(-0.5 * (np.log2(bpms / BPM_PRIOR_CENTER) / BPM_PRIOR_SIGMA) ** 2)
    # 把 1/2、1、2 倍位置的自相關合併，讓真正的拍子比單一尖峰更穩
    def at(scale):
        return np.interp(bpms * scale, bpms, strength, left=0, right=0)
    combined = strength + 0.5 * at(2.0) + 0.5 * at(0.5)
    best = int(np.argmax(combined * prior))
    bpm = float(bpms[best])

    # 倍速/半速候選：自相關夠強才列出，讓使用者自己判斷
    alts = []
    for scale in (0.5, 2.0):
        cand = bpm * scale
        if BPM_MIN <= cand <= BPM_MAX:
            i = int(np.argmin(np.abs(bpms - cand)))
            lo, hi = max(0, i - 2), i + 3
            if strength[lo:hi].max() >= 0.6 * strength[max(0, best - 2):best + 3].max():
                alts.append(int(round(cand)))
    return BpmResult(int(round(bpm)), alts)


def detect_bpm(audio_path: str) -> BpmResult:
    y, sr = load_audio(audio_path)
    return estimate_bpm(y, sr)


def analyze(audio_path: str) -> tuple[KeyResult, "BpmResult | None"]:
    """調性與 BPM 一起算：只讀檔一次、只做一次和聲/打擊分離。找不到節拍時 BPM 為 None。"""
    y, sr = load_audio(audio_path)
    H, P = librosa.decompose.hpss(librosa.stft(y), margin=(1.0, 2.0))
    n = len(y)
    key = estimate_key(y, sr, y_h=librosa.istft(H, length=n))
    try:
        bpm = estimate_bpm(y, sr, y_p=librosa.istft(P, length=n))
    except ValueError:
        bpm = None
    return key, bpm
