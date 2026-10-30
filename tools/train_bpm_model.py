"""重新訓練 BPM 模型，並匯出成 bpm_model_data.py（純數字的樹，網站不需要 scikit-learn）。

資料：GiantSteps tempo dataset（音檔 <id>.mp3，標註 <id>.LOFI.bpm，內容如 "127.0"）。
另外加入 36 首合成慢歌（58–140 BPM，取自 tests/test_analysis.py 的合成器），避免模型只學到電子舞曲的速度。
用法：
    python tools/train_bpm_model.py 音檔資料夾 標註資料夾 [--limit N] [--syn-weight 5]
需要 scikit-learn（只有訓練用，網站不需要）。
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import librosa
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
import analysis  # noqa: E402

TOL = 0.04


def curves_from_audio(y, sr):
    H, P = librosa.decompose.hpss(librosa.stft(y), margin=(1.0, 2.0))
    return analysis.tempo_curves(y, librosa.istft(P, length=len(y)), sr)


def _edm(job):
    audio, truth = job
    try:
        y, sr = analysis.load_audio(audio)
        return curves_from_audio(y, sr), truth
    except Exception:
        return None


def _syn(job):
    import test_analysis as TA
    root, mode, bpm = job
    return curves_from_audio(TA._song(root, mode, bpm, bars=10), TA.SR), float(bpm)


def rows(items):
    X, y, g = [], [], []
    for n, (curves, truth) in enumerate(items):
        for c in analysis.tempo_candidates(curves):
            X.append(analysis.tempo_features(curves, c))
            y.append(abs(c - truth) <= TOL * truth)
            g.append(n)
    return np.array(X), np.array(y), np.array(g)


def new_model():
    return HistGradientBoostingClassifier(max_iter=150, learning_rate=0.06, max_leaf_nodes=8, l2_regularization=1.0)


def export(model, path):
    trees = []
    for it in model._predictors:
        nodes = it[0].nodes
        leaf = nodes["is_leaf"].astype(bool)
        trees.append((
            [int(v) for v in np.where(leaf, 0, nodes["feature_idx"])],
            [float(v) for v in np.where(leaf, 0, nodes["num_threshold"])],       # 門檻不可四捨五入：有些特徵極小（~1e-7）
            [-1 if l else int(v) for l, v in zip(leaf, nodes["left"])],
            [-1 if l else int(v) for l, v in zip(leaf, nodes["right"])],
            [round(float(v), 8) for v in nodes["value"]],
        ))
    with open(path, "w", encoding="utf-8") as f:
        f.write('"""BPM 模型（梯度提升樹，純數字）。由 tools/train_bpm_model.py 產生，請勿手改。"""\n')
        f.write(f"BASELINE = {float(model._baseline_prediction.ravel()[0])!r}\n")
        f.write("# (feature_idx, threshold, left, right, value)；left < 0 表示葉節點\nTREES = [\n")
        for t in trees:
            f.write("    (" + ", ".join(repr(x) for x in t) + "),\n")
        f.write("]\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("audio_dir")
    ap.add_argument("annotation_dir")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--syn-weight", type=float, default=5.0)
    a = ap.parse_args()
    ids = sorted(f[:-len(".LOFI.bpm")] for f in os.listdir(a.annotation_dir) if f.endswith(".LOFI.bpm"))
    ids = [i for i in ids if os.path.exists(f"{a.audio_dir}/{i}.mp3")]
    if a.limit:
        ids = ids[:a.limit]
    jobs = [(f"{a.audio_dir}/{i}.mp3", float(open(f"{a.annotation_dir}/{i}.LOFI.bpm").read().split()[0])) for i in ids]
    rng = np.random.default_rng(3)
    syn_jobs = [(int(rng.integers(0, 12)), str(rng.choice(["大調", "小調"])), b)
                for b in (58, 62, 66, 70, 74, 78, 82, 86, 90, 94, 98, 104, 110, 116, 122, 128, 134, 140) for _ in range(2)]
    with ProcessPoolExecutor(4) as ex:
        edm = [r for r in ex.map(_edm, jobs, chunksize=2) if r]
        syn = list(ex.map(_syn, syn_jobs))
    Xs, ys, _ = rows(syn)
    folds = np.array_split(np.random.default_rng(0).permutation(len(edm)), 5)
    hit = []
    for k in range(5):
        te = set(folds[k].tolist())
        Xtr, ytr, _ = rows([edm[i] for i in range(len(edm)) if i not in te])
        m = new_model().fit(np.vstack([Xtr, Xs]), np.concatenate([ytr, ys]),
                            sample_weight=np.concatenate([np.ones(len(ytr)), np.full(len(ys), a.syn_weight)]))
        Xte, yte, gte = rows([edm[i] for i in sorted(te)])
        p = m.predict_proba(Xte)[:, 1]
        for g in range(len(te)):
            sel = gte == g
            if sel.any():
                hit.append(bool(yte[sel][np.argmax(p[sel])]))
    print(f"{len(edm)} 首 EDM + {len(syn)} 首合成慢歌；5 折交叉驗證嚴格命中（±4%）：{np.mean(hit):.3f}")
    Xe, ye, _ = rows(edm)
    model = new_model().fit(np.vstack([Xe, Xs]), np.concatenate([ye, ys]),
                            sample_weight=np.concatenate([np.ones(len(ye)), np.full(len(ys), a.syn_weight)]))
    out = os.path.join(ROOT, "bpm_model_data.py")
    export(model, out)
    # 驗證匯出的純數字模型與 scikit-learn 的結果一致
    import importlib
    sys.modules.pop("bpm_model_data", None)
    importlib.invalidate_caches()
    X = np.vstack([Xe, Xs])[:300]
    sk = model.predict_proba(X)[:, 1]
    mine = np.array([analysis._tree_score(list(x)) for x in X])
    print(f"已寫入 {out}；與 scikit-learn 的最大差異 {np.abs(sk - mine).max():.2e}")
