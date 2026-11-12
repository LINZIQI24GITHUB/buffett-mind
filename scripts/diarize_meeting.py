#!/usr/bin/env python3
"""用声纹把年会转写区分成「巴菲特 / 芒格 / 其他（主持人、提问者）」。

思路：不依赖 gated 模型（pyannote 需要 HF token）。用开源的 resemblyzer 给每段
转写算一个说话人向量，再聚类成 2–3 类，最后按行为特征贴标签：

  其他   = 问题占比最高的那一类（主持人念观众提问）
  巴菲特 = 剩下里累计发言时长最长的一类
  芒格   = 再剩下的那一类（发言短、插话多）

局限：两人声音都老、都低沉时聚类会混；芒格只在场 2011–2023，
2020 年他缺席，程序会自动只分 2 类。

用法：
  python scripts/diarize_meeting.py --audio work/2023.wav \
      --segments data/video/2023-meeting.jsonl --k 3 --out data/video/2023-diarized.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from resemblyzer import VoiceEncoder, preprocess_wav
from sklearn.cluster import KMeans


def load_audio(path: Path) -> np.ndarray:
    wav, sr = sf.read(str(path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return preprocess_wav(wav, source_sr=sr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--segments", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--min-sec", type=float, default=0.8)
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.segments).open(encoding="utf-8") if l.strip()]
    wav = load_audio(Path(args.audio))
    sr = 16000
    encoder = VoiceEncoder("cpu")

    vecs, keep = [], []
    for i, r in enumerate(rows):
        a, b = int(r["start"] * sr), int(min(r["end"], len(wav) / sr) * sr)
        if b - a < args.min_sec * sr:
            continue
        emb = encoder.embed_utterance(wav[a:b])
        vecs.append(emb)
        keep.append(i)

    X = np.vstack(vecs)
    km = KMeans(n_clusters=args.k, n_init=10, random_state=0).fit(X)
    labels = km.labels_

    # 每个簇的行为特征
    stats = {}
    for c in range(args.k):
        idx = [j for j, l in enumerate(labels) if l == c]
        segs = [rows[keep[j]] for j in idx]
        dur = sum(max(0.0, s["end"] - s["start"]) for s in segs)
        q = sum(1 for s in segs if s.get("speaker") == "Q") / max(1, len(segs))
        avg = dur / max(1, len(segs))
        stats[c] = {"n": len(segs), "dur": dur, "q": q, "avg": avg}

    # 贴标签：其他人 = Q 比例最高；巴菲特 = 剩余里时长最长；芒格 = 剩下的
    others = max(stats, key=lambda c: stats[c]["q"])
    rest = [c for c in stats if c != others]
    buffett = max(rest, key=lambda c: stats[c]["dur"]) if rest else others
    munger = [c for c in rest if c != buffett]
    name = {others: "other", buffett: "buffett"}
    if munger:
        name[munger[0]] = "munger"

    for c, s in stats.items():
        print(f"簇{c} → {name[c]:<8} 段 {s['n']:>4}｜时长 {s['dur']/60:6.1f} 分钟｜"
              f"提问占比 {s['q']*100:4.1f}%｜平均 {s['avg']:.1f}s")

    with Path(args.out).open("w", encoding="utf-8") as fh:
        for j, i in enumerate(keep):
            r = rows[i]
            r["who"] = name[labels[j]]
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        # 太短的段没有向量，默认归到其他
        kept = set(keep)
        for i, r in enumerate(rows):
            if i not in kept:
                r["who"] = "other"
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"输出 {args.out}｜{len(rows)} 段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
