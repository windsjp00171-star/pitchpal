"""調性與 BPM 偵測（不依賴 Gradio，可單獨測試）。"""
from dataclasses import dataclass, field

import librosa
import numpy as np
from scipy.signal import find_peaks

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# 調性模型：24 個候選調（C…B 大調、C…B 小調）各自對「中頻 + 低音 + 高音色度」打分，再做 softmax。
# 權重由 GiantSteps 604 首與 GiantSteps-MTG 1410 首真實錄音（EDM，附人工標註）學得；
# 5 折交叉驗證（只看沒參與訓練的資料）：完全命中 56.6%，正確答案在前三名的比例 84.5%
# （只用中頻＋低音約 53%、舊的 Krumhansl-Schmuckler 輪廓約 43%）。高音區（C4–B6，旋律與人聲）是進步最大的一項。
# 模型輸出的最高機率可直接當把握度：≥85% 實際命中 84%、70–85% 為 74%、50–70% 為 67%、<30% 只有 30%。
# 權重形狀 (大調/小調, 36)：依序對應 中頻、低音、高音 三組色度（各自旋轉到該候選主音後）。
_W = np.array([
    [0.9269, -0.4164, 0.1124, -0.3626, 0.2671, 0.1419, -0.4654, 0.5921, -0.2461, 0.2014, -0.4789, -0.2724, 0.7369, -0.0613, -0.2225, -0.4012, 0.2810, 0.1677, -0.2918, 0.1919, -0.0088, -0.2265, 0.0004, -0.1658, 1.4121, -1.1539, 0.5007, -1.0468, 1.4272, -0.4133, -1.1606, 1.5592, -0.9125, -0.0009, -0.2835, 0.0725],
    [0.8407, 0.1135, -0.4275, 0.3162, -0.3852, 0.0379, -0.5526, 0.5206, 0.1472, -0.3036, -0.0159, -0.2913, 0.6913, -0.1368, -0.2170, 0.1053, -0.0495, -0.0703, 0.0024, -0.0082, -0.0924, -0.3344, 0.1105, -0.0009, 1.4049, -0.8962, 0.2610, 0.7155, 0.0237, -0.2787, -0.5380, 1.4798, -0.9321, -0.9263, 0.8358, -1.1496],
])
_B_TRAINED = np.array([-0.7766, 0.7766])
# 訓練資料有 73% 是小調（電子舞曲），模型因此偏愛小調：大調曲只命中 33%、小調曲 70%。
# 敬拜歌等多半是大調，所以給大調加上 ln(0.73/0.27)≈1.0 的偏移（扣掉訓練資料的大小調比例），並以交叉驗證實測確認兩者命中率持平；
# 兩種調的命中率因此拉平到各約 55–57%，代價是在電子舞曲上整體少約 3 個百分點。
# 等有敬拜歌的標註後，可依真實的大小調比例再調整。
_B = _B_TRAINED + np.array([np.log(0.73 / 0.27), 0.0])

SR = 22050
MAX_ANALYSIS_SEC = 120   # 只分析中段最多 2 分鐘，控制運算時間



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


def _chroma_profile(y_h: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """回傳 (中頻色度, 低音色度, 高音色度)。y_h 為和聲成分（已去掉鼓與打擊樂對音高的干擾）。"""
    # estimate_tuning 的單位是「一個 bin 的比例」；用 12 bins 估才涵蓋 ±半音，
    # 再換算成 36 bins/octave 的單位（1 半音 = 3 bins）餵給 chroma_cqt
    tuning_semitones = float(librosa.estimate_tuning(y=y_h, sr=sr, bins_per_octave=12))
    # 偏差不到半個 bin（約 1/6 半音）時音高仍落在同一格，估計值只會帶來雜訊，不校正
    if abs(tuning_semitones) < 0.17:
        tuning_semitones = 0.0
    kw = dict(y=y_h, sr=sr, tuning=tuning_semitones * 3, bins_per_octave=36, norm=None)
    mid = librosa.feature.chroma_cqt(**kw, fmin=librosa.note_to_hz("C2"), n_octaves=6)     # 略過會蓋掉音高的超低頻
    bass = librosa.feature.chroma_cqt(**kw, fmin=librosa.note_to_hz("C1"), n_octaves=2)    # 低音多半是和弦根音
    treble = librosa.feature.chroma_cqt(**kw, fmin=librosa.note_to_hz("C4"), n_octaves=3)  # 旋律與人聲
    return _fold_chroma(mid), _fold_chroma(bass), _fold_chroma(treble)


def _key_probabilities(*chromas: np.ndarray) -> np.ndarray:
    """24 個候選調的機率（前 12 個大調、後 12 個小調）。輸入依序為 中頻、低音、高音色度。"""
    def norm(c):
        return c / (c.sum() + 1e-9) * 12 - 1
    normed = [norm(c) for c in chromas]
    scores = np.empty(24)
    for k in range(24):
        feat = np.concatenate([np.roll(c, -(k % 12)) for c in normed])
        scores[k] = feat @ _W[k // 12] + _B[k // 12]
    scores -= scores.max()
    p = np.exp(scores)
    return p / p.sum()


def estimate_key(y: np.ndarray, sr: int, y_h: np.ndarray | None = None) -> KeyResult:
    if y_h is None:
        y_h = librosa.effects.harmonic(y, margin=1.0)
    chromas = _chroma_profile(y_h, sr)
    if chromas[0].sum() <= 0:
        raise ValueError("音頻檔案幾乎是靜音。")
    p = _key_probabilities(*chromas)
    order = np.argsort(p)[::-1]
    best = int(order[0])
    alternatives = [(int(i) % 12, "大調" if i < 12 else "小調") for i in order[1:3]]
    return KeyResult(best % 12, "大調" if best < 12 else "小調", int(round(100 * p[best])), alternatives)


def detect_key(audio_path: str) -> KeyResult:
    y, sr = load_audio(audio_path)
    return estimate_key(y, sr)


# ── BPM ───────────────────────────────────────────────────────────────────────
# 做法：從節奏訊號（打擊成分、全頻、低頻鼓點、高頻打擊各一條）算自相關曲線，找出幾個候選速度，
# 再由訓練好的樹模型替每個候選打分，挑最像「人會打拍子的速度」的那個。
# 特徵只用「候選和它的半速、倍速等在節奏上誰更強」的相對值，不含絕對速度，所以不偏愛快歌或慢歌。
# 訓練資料：GiantSteps tempo 664 首真實錄音（EDM）＋ 36 首合成慢歌（58–140 BPM，權重 5）。
# 664 首 5 折交叉驗證（只看沒參與訓練的資料）：嚴格命中（±4%）85.5%（舊做法 21.4%），
# 答案在「第一名＋也可能是」裡的比例 93.2%；第一名機率 ≥95% 的 100% 命中。

HOP = 512
_RATIOS = (1, 2, 0.5, 1.5, 2 / 3, 3, 1 / 3, 4, 0.25)
_KINDS = ("perc", "full", "low", "high")
ALT_MIN_PROB = 0.08      # 其他候選的機率至少這麼高才列為「也可能是」
ALT_MAX = 2


def _autocorr_curve(onset: np.ndarray, sr: int):
    """onset 強度的自相關，回傳 (bpm 由小到大, 強度)。"""
    onset = onset - onset.mean()
    ac = librosa.autocorrelate(onset, max_size=len(onset) // 2)
    ac = np.maximum(ac, 0)
    ac = ac / (ac[0] + 1e-9)
    lags = np.arange(len(ac))
    lags[0] = 1
    bpms = 60.0 * sr / (HOP * lags)
    mask = (bpms >= 40) & (bpms <= 260)
    return bpms[mask][::-1], ac[mask][::-1]


def tempo_curves(y: np.ndarray, y_p: np.ndarray, sr: int) -> dict:
    """四條節奏曲線：{kind: (bpms, strength) 或 None}。y 為原音、y_p 為其打擊成分。"""
    S = np.abs(librosa.stft(y_p, hop_length=HOP))
    f = librosa.fft_frequencies(sr=sr)
    onsets = {
        "perc": librosa.onset.onset_strength(y=y_p, sr=sr, hop_length=HOP, aggregate=np.median),
        "full": librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP),
        "low": np.maximum(np.diff(np.log1p(S[f < 200]).sum(0), prepend=0), 0),    # 鼓點
        "high": np.maximum(np.diff(np.log1p(S[f > 4000]).sum(0), prepend=0), 0),  # 鈸與高頻打擊
    }
    return {k: (None if o.std() < 1e-9 else _autocorr_curve(o, sr)) for k, o in onsets.items()}


def tempo_candidates(curves: dict, k: int = 8, lo: float = 50, hi: float = 220) -> list[float]:
    """打擊曲線上最強的幾個峰（bpm）。"""
    if curves["perc"] is None:
        return []
    b, s = curves["perc"]
    m = (b >= lo) & (b <= hi)
    bb, ss = b[m], s[m]
    pk, _ = find_peaks(ss, prominence=0.02)
    pk = pk[np.argsort(-ss[pk])][:k]
    return [float(bb[i]) for i in pk]


def tempo_features(curves: dict, c: float) -> list[float]:
    f = []
    for kind in _KINDS:
        if curves[kind] is None:
            f += [0.0] * len(_RATIOS)
            continue
        b, s = curves[kind]
        mx = s.max() + 1e-9
        f += [float(np.interp(c * r, b, s, left=0, right=0)) / mx for r in _RATIOS]
    pb, ps = curves["perc"]
    f.append(float(np.interp(c, pb, ps)))
    return f


def _tree_score(x: list[float]) -> float:
    """訓練好的梯度提升樹（bpm_model_data）：回傳該候選是「正確速度」的機率。"""
    import bpm_model_data      # 延後載入：訓練腳本第一次執行時這個檔案還不存在
    raw = bpm_model_data.BASELINE
    for feat, thr, left, right, val in bpm_model_data.TREES:
        n = 0
        while left[n] >= 0:
            n = left[n] if x[feat[n]] <= thr[n] else right[n]
        raw += val[n]
    return 1.0 / (1.0 + np.exp(-raw))


def estimate_bpm(y: np.ndarray, sr: int, y_p: np.ndarray | None = None) -> BpmResult:
    if y_p is None:
        y_p = librosa.effects.percussive(y, margin=2.0)
    curves = tempo_curves(y, y_p, sr)
    cands = tempo_candidates(curves)
    if not cands:
        raise ValueError("找不到明顯的節拍。")
    probs = [_tree_score(tempo_features(curves, c)) for c in cands]
    order = np.argsort(probs)[::-1]
    best = cands[order[0]]
    alts = []
    for j in order[1:]:
        c = cands[j]
        if probs[j] >= ALT_MIN_PROB and all(abs(c - x) > 0.04 * x for x in [best] + alts) and len(alts) < ALT_MAX:
            alts.append(c)
    return BpmResult(int(round(best)), [int(round(a)) for a in alts])


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
