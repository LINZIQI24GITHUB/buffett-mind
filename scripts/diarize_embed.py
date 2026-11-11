#!/usr/bin/env python3
"""用 sherpa-onnx 的 3D-Speaker 声纹模型区分巴菲特 / 芒格 / 其他。

模型：3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx（约 38 MB）
运行时只依赖 onnxruntime（已随 sherpa-onnx 装好），不需要 torch。

流程：每段转写切出音频 → 声纹向量 → KMeans 聚类 → 按行为特征贴标签
  其他   = 提问/短插话占比高
  巴菲特 = 剩余里累计发言最长
  芒格   = 再剩下的那一类

用法：
  python scripts/diarize_embed.py --audio work/2023.wav \
      --segments data/video/2023-meeting.jsonl --k 3 --out out/2023-who.jsonl
  --offset 用于只截取某段窗口（音频起点在整场中的秒数）
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf

SR = 16000
MODEL = Path("D:/dsh-data/models/speaker/eres2net.onnx")


def kmeans(X: np.ndarray, k: int, iters: int = 60, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    best, best_inertia = None, np.inf
    for _ in range(8):
        cent = X[rng.choice(len(X), k, replace=False)]
        lab = np.zeros(len(X), dtype=int)
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
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--model", default=str(MODEL))
    args = ap.parse_args()

    cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=args.model, num_threads=4)
    ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)

    rows = [json.loads(l) for l in Path(args.segments).open(encoding="utf-8") if l.strip()]
    wav, sr = sf.read(args.audio, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != SR:
        raise SystemExit(f"需要 16k 音频，当前 {sr}")

    vecs, keep = [], []
    for i, r in enumerate(rows):
        a = int((r["start"] - args.offset) * SR)
        b = int((r["end"] - args.offset) * SR)
        if a < 0 or b > len(wav) or b - a < SR * 0.6:
            continue
        stream = ext.create_stream()
        stream.accept_waveform(SR, wav[a:b])
        stream.input_finished()
        if not ext.is_ready(stream):
            continue
        v = np.array(ext.compute(stream), dtype=np.float32)
        vecs.append(v / (np.linalg.norm(v) + 1e-9))
        keep.append(i)

    X = np.vstack(vecs)
    lab = kmeans(X, min(args.k, len(X)))

    stats = {}
    for c in range(lab.max() + 1):
        idx = [j for j, l in enumerate(lab) if l == c]
        segs = [rows[keep[j]] for j in idx]
        dur = sum(max(0.0, s["end"] - s["start"]) for s in segs)
        q = sum(1 for s in segs if s.get("speaker") == "Q") / max(1, len(segs))
        stats[c] = {"n": len(segs), "dur": dur, "q": q}

    others = max(stats, key=lambda c: stats[c]["q"])
    rest = [c for c in stats if c != others]
    buffett = max(rest, key=lambda c: stats[c]["dur"]) if rest else others
    munger = [c for c in rest if c != buffett]
    name = {others: "other", buffett: "buffett"}
    if munger:
        name[munger[0]] = "munger"

    for c, s in sorted(stats.items(), key=lambda kv: -kv[1]["dur"]):
        print(f"簇{c} → {name[c]:<8} 段 {s['n']:>4}｜时长 {s['dur']/60:6.1f} 分钟｜提问占比 {s['q']*100:4.1f}%")

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
