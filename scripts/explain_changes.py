#!/usr/bin/env python3
"""逐季解释调仓：谁走了、谁进来、为什么。

读取 screen-all-<date>.json（全量评分），对比相邻两期的 Top N，
给出每一笔买卖的直接原因：
  · 分数排名掉出 Top N
  · 估值变化（PE 上升/下降）
  · 景气变化（净利同比转负/转正）
  · 行业（如果被行业上限挤出）

用法：
  python scripts/explain_changes.py --tag all --top 10
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "screen"


def load(date: str, tag: str) -> list[dict]:
    p = CACHE / f"screen-{tag}-{date}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def fmt(x: dict) -> str:
    g = x.get("growth")
    gs = f"增速{g:+.0f}%" if g is not None else "增速—"
    return f"ROE {x['roe_mean']:.0f}%/{x['roe_min']:.0f}%｜PE {x['pe']:.1f}｜{gs}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="all")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    dates = sorted(p.stem.split(f"screen-{args.tag}-")[-1] for p in CACHE.glob(f"screen-{args.tag}-*.json"))
    prev: list[dict] = []
    for i, d in enumerate(dates):
        rows = load(d, args.tag)
        rank = {r["code"]: j + 1 for j, r in enumerate(rows)}
        cur = rows[: args.top]
        cutoff = cur[-1]["score"] if cur else 0
        print(f"\n=== {d}｜Top{args.top} 门槛 {cutoff:.0f} 分｜可评分 {len(rows)}")

        if prev:
            prev_codes = {r["code"] for r in prev}
            cur_codes = {r["code"] for r in cur}
            out = [r for r in prev if r["code"] not in cur_codes]
            inn = [r for r in cur if r["code"] not in prev_codes]
            if not out and not inn:
                print("  无调仓（前十不变）")
            for r in out:
                now = next((x for x in rows if x["code"] == r["code"]), None)
                if now is None:
                    reason = "已不满足入选条件（ROE 历史不足或估值缺失）"
                else:
                    bits = [f"排名 {rank[now['code']]}（{now['score']:.0f} 分，门槛 {cutoff:.0f}）"]
                    if now["pe"] > r["pe"] * 1.2:
                        bits.append(f"PE {r['pe']:.1f}→{now['pe']:.1f}")
                    if r.get("growth") is not None and now.get("growth") is not None and now["growth"] < -10 <= r["growth"]:
                        bits.append(f"增速 {r['growth']:+.0f}%→{now['growth']:+.0f}%")
                    reason = "；".join(bits)
                print(f"  卖出 {r['code']} {r['name'][:6]:<7}{fmt(r)}  ← {reason}")
            for r in inn:
                print(f"  买入 {r['code']} {r['name'][:6]:<7}{fmt(r)}  ← 新进前十")
            print(f"  换手 {len(out)}/{len(cur)}")
        prev = cur

    print("\n注：这是机械规则的调仓，不是人工判断；理由只解释「分数为什么变」，不代表对错。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
