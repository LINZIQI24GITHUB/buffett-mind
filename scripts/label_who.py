#!/usr/bin/env python3
"""给年会段落标注「巴菲特 / 芒格 / 其他」——高精度优先的混合规则版。

背景：纯声纹聚类在这批素材上不可靠。原因是两人都是老年男声，而且问答节奏快、
单段只有 2–4 秒，聚类会把主持人的开场和巴菲特的回答混到一起（实测过三轮）。

所以第一版改成「高精度、低召回」的规则：
  1. 主持人念题（含 question comes from / 以问号结尾且很短）→ other
  2. 巴菲特点名芒格（"Charlie, ...?" / "Charlie, I'm sure you have something to add"）
     → 本人 buffett，紧跟着 25 秒内的短回答 → munger
  3. 芒格口头禅（I have nothing to add / I agree / That's right）→ munger
  4. 其余 → buffett（他占发言时长的绝大多数）

没标到的芒格发言会留在 buffett 里，这是有意为之：宁可漏，不可错。
置信度写在 confidence 字段（high / medium / default）。

用法：
  python scripts/label_who.py --segments data/video/2023-meeting.jsonl --inplace
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MODERATOR = re.compile(
    r"this question comes from|our (first|next|last) question|question (is )?from|"
    r"i'?d like to ask|we have a question", re.I)
MUNGER_TIC = re.compile(
    r"nothing to add|i have nothing|i'?ve got nothing|i agree|that'?s right|"
    r"you can argue that", re.I)
ADDRESS_CHARLIE = re.compile(r"charlie[^.]{0,60}(\?|add|any|thoughts|comment|say)", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", required=True)
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-munger", action="store_true",
                    help="该场没有芒格（2020 缺席、2024 起已去世），把 munger 并回 buffett")
    args = ap.parse_args()

    src = Path(args.segments)
    rows = [json.loads(l) for l in src.open(encoding="utf-8") if l.strip()]

    for r in rows:
        r["who"] = "buffett"
        r["confidence"] = "default"

    # 规则 1：主持人念题
    for r in rows:
        t = r["text"].strip()
        if MODERATOR.search(t):
            r["who"], r["confidence"] = "other", "high"
        elif r.get("speaker") == "Q" and len(t.split()) <= 25:
            r["who"], r["confidence"] = "other", "medium"

    # 规则 2：巴菲特点名芒格 → 后续短回答归芒格
    for i, r in enumerate(rows):
        if not ADDRESS_CHARLIE.search(r["text"]):
            continue
        r["who"], r["confidence"] = "buffett", "medium"
        for j in range(i + 1, min(i + 4, len(rows))):
            nxt = rows[j]
            if nxt["start"] - r["end"] > 25:
                break
            if nxt["who"] == "other":
                continue
            if len(nxt["text"].split()) <= 30:
                nxt["who"], nxt["confidence"] = "munger", "medium"
            break

    # 规则 3：芒格口头禅
    for r in rows:
        if MUNGER_TIC.search(r["text"]) and r["who"] != "other":
            r["who"], r["confidence"] = "munger", "high"

    if args.no_munger:
        for r in rows:
            if r["who"] == "munger":
                r["who"], r["confidence"] = "buffett", "default"

    dst = src if args.inplace else Path(args.out or src.with_suffix(".who.jsonl"))
    with dst.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    c = Counter((r["who"], r["confidence"]) for r in rows)
    total = len(rows)
    men = c[("munger", "high")] + c[("munger", "medium")]
    print(f"{src.name}: {total} 段｜芒格 {men}（{men/total*100:.1f}%）｜"
          f"其他 {c[('other','high')] + c[('other','medium')]}｜巴菲特 {c[('buffett','default')]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
