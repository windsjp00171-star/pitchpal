"""調性與 BPM 偵測（不依賴 Gradio，可單獨測試）。"""
from dataclasses import dataclass, field

import librosa
import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler 調性輪廓。GiantSteps 160 首真實錄音實測：
# 完全命中率 KS 約 45%、Temperley 約 31%；色度圖從 C2 起算（略過超低頻）再升到 46%。
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

SR = 22050
MAX_ANALYSIS_SEC = 180   # 只分析中段最多 3 分鐘，控制運算時間

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


def _chroma_profile(y: np.ndarray, sr: int) -> np.ndarray:
    # 取和聲成分，去掉鼓與打擊樂對音高的干擾；並校正整首歌的調音偏差
    y_h = librosa.effects.harmonic(y, margin=1.0)
    # estimate_tuning 的單位是「一個 bin 的比例」；用 12 bins 估才涵蓋 ±半音，
    # 再換算成 36 bins/octave 的單位（1 半音 = 3 bins）餵給 chroma_cqt
    tuning_semitones = float(librosa.estimate_tuning(y=y_h, sr=sr, bins_per_octave=12))
    # 偏差不到半個 bin（約 1/6 半音）時音高仍落在同一格，估計值只會帶來雜訊，不校正
    if abs(tuning_semitones) < 0.17:
        tuning_semitones = 0.0
    chroma = librosa.feature.chroma_cqt(
        y=y_h, sr=sr, tuning=tuning_semitones * 3, bins_per_octave=36, norm=None,
        fmin=librosa.note_to_hz("C2"), n_octaves=6)  # 從 C2 起，略過會蓋掉音高的超低頻
    return _fold_chroma(chroma)


def _corr_all_keys(chroma: np.ndarray) -> np.ndarray:
    """回傳 (24,) 相關係數：前 12 個為大調 C…B，後 12 個為小調 C…B。"""
    if np.allclose(chroma, 0) or np.std(chroma) < 1e-9:
        return np.full(24, -1.0)
    scores = np.empty(24)
    for i in range(12):
        scores[i] = np.corrcoef(np.roll(_MAJOR_PROFILE, i), chroma)[0, 1]
        scores[12 + i] = np.corrcoef(np.roll(_MINOR_PROFILE, i), chroma)[0, 1]
    return scores


def estimate_key(y: np.ndarray, sr: int) -> KeyResult:
    scores = _corr_all_keys(_chroma_profile(y, sr))

    order = np.argsort(scores)[::-1]
    best = int(order[0])
    root, mode = best % 12, ("大調" if best < 12 else "小調")

    # 信心度：第一名與「第二名」的差距。相對大小調（如 C 大調 vs A 小調）本來就
    # 容易混淆，所以另外列為候選，不算進差距，避免永遠顯示低信心。
    relative = (root + 9) % 12 + 12 if best < 12 else (root + 3) % 12
    rivals = [int(i) for i in order[1:] if int(i) != relative]
    gap = float(scores[best] - scores[rivals[0]])
    # 合成與真實音檔實測：差距約 0.01（難分）～0.17（明確）
    confidence = int(round(min(1.0, max(0.0, gap / 0.10)) * 100))

    alternatives = [(relative % 12, "小調" if best < 12 else "大調")]
    runner = rivals[0]
    alternatives.append((runner % 12, "大調" if runner < 12 else "小調"))
    return KeyResult(root, mode, confidence, alternatives)


def detect_key(audio_path: str) -> KeyResult:
    y, sr = load_audio(audio_path)
    return estimate_key(y, sr)


# ── BPM ───────────────────────────────────────────────────────────────────────

def _tempo_curve(y: np.ndarray, sr: int, hop: int = 512):
    """以打擊成分的 onset 強度做自相關，回傳 (bpm 陣列, 強度陣列)。"""
    y_p = librosa.effects.percussive(y, margin=2.0)
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


def estimate_bpm(y: np.ndarray, sr: int) -> BpmResult:
    bpms, strength = _tempo_curve(y, sr)
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
