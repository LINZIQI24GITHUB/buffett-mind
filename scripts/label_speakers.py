#!/usr/bin/env python3
"""给转写稿标「提问 / 回答」，把提问者的话和巴菲特的回答分开。

为什么要做：CNBC 的整场录像里，主持人念观众提问、巴菲特和芒格回答，
全部混在一段文字里。检索「他怎么说」时，经常命中提问者的话。

能做到什么：文本启发式区分 **Q（提问）/ A（回答）**。
做不到什么：**分不出巴菲特和芒格**——那需要声纹，本地 CPU 跑不动，
而且 pyannote 的预训练模型需要 HF token。所以这里只标 Q/A，不标具体人。

用法：
  python scripts/label_speakers.py --segments data/video/2024-meeting.jsonl --inplace
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

Q_PATTERNS = [
    r"this question comes from",
    r"our (first|next|last) question",
    r"question (is )?from",
    r"i'?d like to ask",
    r"i want to ask",
    r"can you (tell|explain|comment)",
    r"what do you (think|make)",
    r"how do you (think|see|view)",
    r"why did you",
    r"would you (say|agree)",
    r"becky|andrew",
]
Q_RE = re.compile("|".join(Q_PATTERNS), re.I)


def classify(text: str) -> str:
    t = text.strip()
    if not t:
        return "A"
    if Q_RE.search(t):
        return "Q"
    words = t.split()
    if t.endswith("?") and len(words) <= 60:
        return "Q"
    if len(words) <= 12 and t.endswith("?"):
        return "Q"
    return "A"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", required=True)
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    src = Path(args.segments)
    rows = [json.loads(l) for l in src.open(encoding="utf-8") if l.strip()]
    for r in rows:
        r["speaker"] = classify(r.get("text", ""))

    dst = src if args.inplace else Path(args.out or src.with_suffix(".labeled.jsonl"))
    with dst.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    q = sum(1 for r in rows if r["speaker"] == "Q")
    words_q = sum(len(r["text"].split()) for r in rows if r["speaker"] == "Q")
    words_all = sum(len(r["text"].split()) for r in rows)
    print(f"{src.name}: {len(rows)} 段｜Q {q} 段（{words_q/words_all*100:.1f}% 词数）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
