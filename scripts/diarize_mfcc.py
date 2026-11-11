#!/usr/bin/env python3
"""纯 numpy 的说话人聚类：MFCC + 基频 + 能量，KMeans 分 2–3 类。

为什么不用 resemblyzer/pyannote：它们依赖 torch，而这台机器下载 torch 被限速到
0.3 MB/s，装不上。MFCC + F0 对「两个老年男声 + 一个主持人」这种粗分已经够用——
基频是区分巴菲特和芒格最有效的单一特征。

标签规则（与 diarize_meeting.py 一致）：
  其他   = 提问占比最高
  巴菲特 = 剩余里累计发言最长
  芒格   = 再剩下的

用法：
  python scripts/diarize_mfcc.py --audio work/2023.wav \
      --segments data/video/2023-meeting.jsonl --k 3 --out out/2023-who.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16000


def mel_filterbank(n_mels: int = 26, n_fft: int = 512) -> np.ndarray:
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel2hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    mels = np.linspace(hz2mel(80), hz2mel(7600), n_mels + 2)
    bins = np.floor((n_fft + 1) * mel2hz(mels) / SR).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for i in range(n_mels):
        l, c, r = bins[i], bins[i + 1], bins[i + 2]
        for k in range(l, c):
            fb[i, k] = (k - l) / max(1, c - l)
        for k in range(c, r):
            fb[i, k] = (r - k) / max(1, r - c)
    return fb


DCT = np.cos(np.pi / 26 * (np.arange(13)[:, None] * (2 * np.arange(26)[None, :] + 1) / 2))


def features(x: np.ndarray) -> np.ndarray | None:
    if len(x) < SR * 0.8:
        return None
    frame, hop = int(0.025 * SR), int(0.010 * SR)
    n = 1 + (len(x) - frame) // hop
    if n < 5:
        return None
    idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx] * np.hamming(frame)[None, :]
    spec = np.abs(np.fft.rfft(frames, 512)) ** 2
    fb = mel_filterbank()
    melspec = np.log(spec @ fb.T + 1e-9)
    mfcc = melspec @ DCT.T
    f0 = _pitch(x)
    energy = np.sqrt((frames ** 2).mean(axis=1))
    return np.concatenate([mfcc.mean(axis=0), mfcc.std(axis=0),
                           [f0, energy.mean(), energy.std()]])


def _pitch(x: np.ndarray) -> float:
    """自相关估基频：对老年男声，巴菲特 ~110Hz，芒格 ~130–150Hz。"""
    frame, hop = int(0.040 * SR), int(0.020 * SR)
    n = 1 + (len(x) - frame) // hop
    if n < 3:
        return 0.0
    lo, hi = int(SR / 300), int(SR / 70)
    vals = []
    for i in range(0, n, max(1, n // 40)):
        f = x[i * hop: i * hop + frame]
        if np.sqrt((f ** 2).mean()) < 0.01:
            continue
        ac = np.correlate(f, f, "full")[frame - 1:]
        if hi >= len(ac):
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.3 * ac[0]:
            vals.append(SR / lag)
    return float(np.median(vals)) if vals else 0.0


def kmeans(X: np.ndarray, k: int, iters: int = 50, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    best, best_inertia = None, np.inf
    for _ in range(5):
        cent = X[rng.choice(len(X), k, replace=False)]
        for _ in range(iters):
            d = ((X[:, None, :] - cent[None, :, :]) ** 2).sum(axis=2)
            lab = d.argmin(axis=1)
            new = np.array([X[lab == j].mean(axis=0) if (lab == j).any() else cent[j]
                            for j in range(k)])
            if np.allclose(new, cent):
                break
            cent = new
        inertia = ((X - cent[lab]) ** 2).sum()
        if inertia < best_inertia:
            best, best_inertia = lab.copy(), inertia
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--segments", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--offset", type=float, default=0.0,
                    help="音频起点在整场中的秒数（用窗口片段测试时填）")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.segments).open(encoding="utf-8") if l.strip()]
    wav, sr = sf.read(args.audio, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    assert sr == SR, f"需要 16k 单声道，当前 {sr}"

    X, keep = [], []
    for i, r in enumerate(rows):
        a = int((r["start"] - args.offset) * SR)
        b = int((r["end"] - args.offset) * SR)
        if a < 0 or b > len(wav):
            continue
        f = features(wav[a:b])
        if f is not None:
            X.append(f)
            keep.append(i)
    X = np.vstack(X)
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
    lab = kmeans(X, args.k)

    stats = {}
    for c in range(args.k):
        idx = [j for j, l in enumerate(lab) if l == c]
        segs = [rows[keep[j]] for j in idx]
        dur = sum(max(0.0, s["end"] - s["start"]) for s in segs)
        q = sum(1 for s in segs if s.get("speaker") == "Q") / max(1, len(segs))
        f0 = float(np.mean([X[j, -3] for j in idx])) if idx else 0.0
        stats[c] = {"n": len(segs), "dur": dur, "q": q, "f0": f0}

    others = max(stats, key=lambda c: stats[c]["q"])
    rest = [c for c in stats if c != others]
    buffett = max(rest, key=lambda c: stats[c]["dur"]) if rest else others
    munger = [c for c in rest if c != buffett]
    name = {others: "other", buffett: "buffett"}
    if munger:
        name[munger[0]] = "munger"

    for c, s in sorted(stats.items(), key=lambda kv: -kv[1]["dur"]):
        print(f"簇{c} → {name[c]:<8} 段 {s['n']:>4}｜时长 {s['dur']/60:6.1f} 分钟｜"
              f"提问占比 {s['q']*100:4.1f}%")

    with Path(args.out).open("w", encoding="utf-8") as fh:
        kept = set(keep)
        for j, i in enumerate(keep):
            rows[i]["who"] = name[lab[j]]
        for i, r in enumerate(rows):
            if i not in kept:
                r["who"] = "other"
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"输出 {args.out}｜{len(rows)} 段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
