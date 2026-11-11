#!/usr/bin/env python3
"""滑窗声纹分人：先按 3 秒窗口做声纹聚类，再把标签投票给转写段落。

为什么滑窗：单段往往只有 2–4 秒，声纹向量不稳定；改成在整段音频上按
6 秒窗、3 秒步长滑动，窗内通常只有一个说话人，向量稳定得多。
最后每段按重叠时长对窗口标签投票。

用法：
  python scripts/diarize_slide.py --audio work/2023.wav \
      --segments data/video/2023-meeting.jsonl --k 3 --out out/2023-who.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import sherpa_onnx
import soundfile as sf

SR = 16000
MODEL = "D:/dsh-data/models/speaker/eres2net.onnx"


def kmeans(X: np.ndarray, k: int, iters: int = 60, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    best, best_inertia = None, np.inf
    for _ in range(6):
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
    ap.add_argument("--win", type=float, default=6.0)
    ap.add_argument("--hop", type=float, default=3.0)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    ext = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=args.model, num_threads=4))

    wav, sr = sf.read(args.audio, dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != SR:
        raise SystemExit(f"需要 16k 音频，当前 {sr}")

    # 1) 滑窗声纹
    starts, vecs = [], []
    t = 0.0
    while t + args.win <= len(wav) / SR:
        a, b = int(t * SR), int((t + args.win) * SR)
        stream = ext.create_stream()
        stream.accept_waveform(SR, wav[a:b])
        stream.input_finished()
        if ext.is_ready(stream):
            v = np.array(ext.compute(stream), dtype=np.float32)
            vecs.append(v / (np.linalg.norm(v) + 1e-9))
            starts.append(t)
        t += args.hop
    X = np.vstack(vecs)
    print(f"窗口 {len(X)} 个｜{X.shape[1]} 维")
    lab = kmeans(X, min(args.k, len(X)))

    # 2) 段落投票
    rows = [json.loads(l) for l in Path(args.segments).open(encoding="utf-8") if l.strip()]
    win_spans = [(s + args.offset, s + args.offset + args.win) for s in starts]
    for r in rows:
        a, b = r["start"], r["end"]
        votes = np.zeros(lab.max() + 1)
        for (ws, we), l in zip(win_spans, lab):
            ov = max(0.0, min(b, we) - max(a, ws))
            if ov > 0:
                votes[l] += ov
        r["who"] = "v" + str(int(votes.argmax())) if votes.sum() > 0 else "unknown"

    # 3) 按行为特征给聚类命名
    stats = {}
    for c in range(lab.max() + 1):
        segs = [r for r in rows if r["who"] == f"v{c}"]
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

    for r in rows:
        if r["who"].startswith("v"):
            r["who"] = name.get(int(r["who"][1:]), "other")

    with Path(args.out).open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"输出 {args.out}｜{len(rows)} 段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
