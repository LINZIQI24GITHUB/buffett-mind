#!/usr/bin/env python3
"""转写稿数字抽检：把带数字的句子捞出来，供人工/脚本核对。

为什么必须做：ASR 的错误集中在数字和专名，而框架结论全靠数字。
错一个持股数，比没有这段语料更糟。

用法：
  python scripts/validate_transcript.py --segments data/video/2024-meeting.jsonl
  python scripts/validate_transcript.py --segments ... --tsv out/numbers.tsv
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NUM = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:billion|million|thousand|percent|%|shares?|dollars?)?\b",
                 re.I)
CONTEXT = 90


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", required=True)
    ap.add_argument("--tsv", default=None)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    path = Path(args.segments)
    rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
    text = " ".join(r["text"] for r in rows)

    hits: list[tuple[str, str]] = []
    for r in rows:
        for m in NUM.finditer(r["text"]):
            s = max(0, m.start() - CONTEXT)
            ctx = r["text"][s:m.end() + CONTEXT].replace("\n", " ")
            hits.append((f"{int(r['start'])//60:02d}:{int(r['start'])%60:02d}", ctx.strip()))

    print(f"段落 {len(rows)}｜词数 {len(text.split())}｜命中数字 {len(hits)}")
    uniq = {}
    for t, c in hits:
        key = re.sub(r"\s+", " ", c)[:60]
        uniq.setdefault(key, (t, c))
    print(f"去重后 {len(uniq)} 条\n")
    for i, (t, c) in enumerate(list(uniq.values())[: args.limit], 1):
        print(f"[{i:02d}] {t}  …{c}…")

    if args.tsv:
        out = Path(args.tsv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            fh.write("time\tcontext\n")
            for t, c in uniq.values():
                fh.write(f"{t}\t{c}\n")
        print(f"\n已写 {out}（{len(uniq)} 行，供逐条核对）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
