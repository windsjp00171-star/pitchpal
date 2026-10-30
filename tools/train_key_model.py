"""重新訓練調性模型（analysis.py 的 _W / _B）。

資料：GiantSteps key dataset（音檔 *.mp3 與標註 *.LOFI.key，標註內容如 "C minor"）。
用法：
    python tools/train_key_model.py AUDIO_DIR ANNOTATION_DIR [--limit N]
輸出 5 折交叉驗證的完全命中率，以及可直接貼回 analysis.py 的權重。
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import librosa
import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import analysis  # noqa: E402

NAMES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
         "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def label(path):
    tonic, mode = open(path).read().split()[:2]
    return NAMES[tonic] + (0 if mode.lower().startswith("maj") else 12)


def features(audio):
    y, sr = analysis.load_audio(audio)
    return analysis._chroma_profile(librosa.effects.harmonic(y, margin=1.0), sr)


def candidates(mid, bass):
    """24 個候選調各自的特徵：色度旋轉到該候選主音後的 [中頻, 低音]。與 analysis._key_probabilities 一致。"""
    norm = lambda c: c / (c.sum() + 1e-9) * 12 - 1  # noqa: E731
    mid, bass = norm(mid), norm(bass)
    return np.stack([np.concatenate([np.roll(mid, -(k % 12)), np.roll(bass, -(k % 12))]) for k in range(24)])


def fit(R, y, l2=1e-3):
    N, _, D = R.shape
    mode = np.arange(24) // 12

    def f(p):
        W, b = p[:2 * D].reshape(2, D), p[2 * D:]
        S = np.einsum("nkd,kd->nk", R, W[mode]) + b[mode]
        S -= S.max(1, keepdims=True)
        P = np.exp(S)
        P /= P.sum(1, keepdims=True)
        loss = -np.log(P[np.arange(N), y] + 1e-12).mean() + l2 * (W ** 2).sum()
        G = P.copy()
        G[np.arange(N), y] -= 1
        G /= N
        gW = np.stack([np.einsum("nk,nkd->d", G[:, mode == m], R[:, mode == m]) for m in (0, 1)]) + 2 * l2 * W
        gb = np.array([G[:, mode == m].sum() for m in (0, 1)])
        return loss, np.concatenate([gW.ravel(), gb])

    r = minimize(f, np.zeros(2 * D + 2), jac=True, method="L-BFGS-B", options={"maxiter": 300})
    return r.x[:2 * D].reshape(2, D), r.x[2 * D:]


def predict(R, W, b):
    mode = np.arange(24) // 12
    return (np.einsum("nkd,kd->nk", R, W[mode]) + b[mode]).argmax(1)


def _one(args):
    audio, ann = args
    try:
        return candidates(*features(audio)), label(ann)
    except Exception:
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("audio_dir")
    ap.add_argument("annotation_dir")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    ids = sorted(f[:-4] for f in os.listdir(a.audio_dir) if f.endswith(".mp3"))
    ids = [i for i in ids if os.path.exists(f"{a.annotation_dir}/{i}.LOFI.key")]
    if a.limit:
        ids = ids[:a.limit]
    jobs = [(f"{a.audio_dir}/{i}.mp3", f"{a.annotation_dir}/{i}.LOFI.key") for i in ids]
    with ProcessPoolExecutor(4) as ex:
        rows = [r for r in ex.map(_one, jobs, chunksize=4) if r]
    R, y = np.stack([r[0] for r in rows]), np.array([r[1] for r in rows])
    folds = np.array_split(np.random.default_rng(0).permutation(len(y)), 5)
    pred = np.zeros(len(y), int)
    for k in range(5):
        tr = np.concatenate([folds[j] for j in range(5) if j != k])
        W, b = fit(R[tr], y[tr])
        pred[folds[k]] = predict(R[folds[k]], W, b)
    print(f"{len(y)} 首，5 折交叉驗證完全命中率：{(pred == y).mean():.3f}")
    W, b = fit(R, y)
    print("_W = np.array([")
    for row in W:
        print("    [" + ", ".join(f"{v:.4f}" for v in row) + "],")
    print("])")
    print(f"_B = np.array({[round(float(v), 4) for v in b]})")
