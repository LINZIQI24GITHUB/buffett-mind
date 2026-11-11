#!/usr/bin/env python3
"""把他的决策片段抽成「判例库」，供类比判断使用。

不是打分，也不是阈值：每条判例是「他在某年对某个生意做了什么、理由是什么、结果如何」。

抽取规则（全部基于文本，不做语义猜测）：
  动作词：bought / purchased / sold / passed / didn't buy / avoid / never buy
  对象：entities.py 里的公司名 + 若干行业词（airlines, banks, insurance, retail…）

用法：
  python scripts/build_cases.py --out data/cases.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import entities  # noqa: E402

DB = ROOT / "corpus" / "index.sqlite"

ACTION = re.compile(
    r"\b(we|i)\s+(bought|purchased|sold|passed|avoid|never buy|didn't buy|did not buy|"
    r"have bought|have sold)\b", re.I)
INDUSTRY = ["airline", "bank", "insurance", "retail", "technology", "tech",
            "utility", "oil", "railroad", "newspaper", "textile", "shoe",
            "candy", "soda", "jewelry", "furniture"]


def known_names() -> list[str]:
    names = set()
    for key in dir(entities):
        obj = getattr(entities, key)
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, dict) and v.get("name"):
                    names.add(v["name"])
                elif isinstance(v, str) and len(v) > 3:
                    names.add(v)
    return sorted(names, key=len, reverse=True)[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "cases.jsonl"))
    args = ap.parse_args()

    names = known_names()
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT id, kind, year, source, text FROM docs").fetchall()

    cases = []
    for doc_id, kind, year, source, text in rows:
        flat = re.sub(r"\s+", " ", text)
        sents = re.split(r"(?<=[.!?])\s+", flat)
        for i, s in enumerate(sents):
            m = ACTION.search(s)
            if not m:
                continue
            comp = [n for n in names if n.lower() in s.lower()]
            inds = [w for w in INDUSTRY if w in s.lower()]
            if not comp and not inds:
                continue
            cases.append({
                "doc": doc_id, "year": year, "kind": kind,
                "source": source[:60],
                "action": m.group(2).lower(),
                "companies": comp,
                "industries": inds,
                "text": s.strip()[:400],
            })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    from collections import Counter
    print(f"抽取判例 {len(cases)} 条 → {out}")
    print("动作分布:", dict(Counter(c["action"] for c in cases).most_common(8)))
    print("涉及行业:", dict(Counter(i for c in cases for i in c["industries"]).most_common(10)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
