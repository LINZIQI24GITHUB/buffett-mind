#!/usr/bin/env python3
"""从 13F 提取他的「持有行为模式」，用来校验任何自动化策略。

看四件事：
  1. 拿了多久：建仓到清仓（或到最新）的季度数分布
  2. 怎么加：建仓后加了几次、第一次加仓隔多久
  3. 怎么卖：一次性清仓 vs 分几季减完
  4. 什么时候动：组合市值下跌的季度，加仓的比例是否更高

用法：
  python scripts/behavior.py
"""
from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import holdings as H  # noqa: E402

DATA = ROOT / "data"


def main() -> int:
    series = H.load(DATA / "holdings.csv")
    periods = sorted(series)

    # 每个发行人（按 CUSIP 汇总）的股数序列
    track: dict[str, dict[str, float]] = defaultdict(dict)
    for p in periods:
        for cusip, v in H.aggregate(series[p]).items():
            track[cusip][p] = v["shares"]

    spans, adds_after_entry, exit_styles = [], [], []
    first_add_gap = []
    detail = []

    for cusip, s in track.items():
        ps = [p for p in periods if p in s]
        # 只统计「在数据窗口内建仓」的，避免左删失
        first = min(ps)
        if first == periods[0]:
            continue
        last = max(ps)
        alive = s.get(periods[-1], 0) > 0
        span = periods.index(last) - periods.index(first) + 1
        spans.append(span)

        vals = [s[p] for p in ps]
        adds = sum(1 for a, b in zip(vals, vals[1:]) if b > a * 1.001)
        adds_after_entry.append(adds)
        if adds and len(vals) > 1:
            idx = next(i for i in range(1, len(vals)) if vals[i] > vals[i - 1] * 1.001)
            first_add_gap.append(ps[idx] - ps[0] if False else idx)

        # 退出方式：数据末尾仍在 = 持有中；否则视为已退出
        exited = last != periods[-1]
        if exited:
            tail = vals[-4:]
            drops = sum(1 for a, b in zip(tail, tail[1:]) if b < a * 0.8)
            exit_styles.append("一次性清仓" if drops <= 1 else "分季减完")
        else:
            exit_styles.append("仍持有")
        detail.append((cusip, span, adds, len(vals)))

    print(f"样本：窗口内建仓的持仓 {len(spans)} 个")
    if spans:
        print(f"持有季度数：中位 {statistics.median(spans):.0f}｜均值 {statistics.mean(spans):.1f}"
              f"｜最短 {min(spans)}｜最长 {max(spans)}")
        buckets = {"<4 季": 0, "4–8 季": 0, "9–20 季": 0, "21–40 季": 0, ">40 季": 0}
        for s in spans:
            if s < 4:
                buckets["<4 季"] += 1
            elif s <= 8:
                buckets["4–8 季"] += 1
            elif s <= 20:
                buckets["9–20 季"] += 1
            elif s <= 40:
                buckets["21–40 季"] += 1
            else:
                buckets[">40 季"] += 1
        total = len(spans)
        print("分布：" + "｜".join(f"{k} {v}（{v/total*100:.0f}%）" for k, v in buckets.items()))

    if adds_after_entry:
        print(f"\n建仓后加仓次数：中位 {statistics.median(adds_after_entry):.0f}"
              f"｜平均 {statistics.mean(adds_after_entry):.1f}"
              f"｜从未加仓 {sum(1 for a in adds_after_entry if a == 0)} 个")

    if first_add_gap:
        print(f"建仓到第一次加仓：中位 {statistics.median(first_add_gap):.0f} 个季度")

    if exit_styles:
        cnt = defaultdict(int)
        for e in exit_styles:
            cnt[e] += 1
        print("清仓方式：" + "｜".join(f"{k} {v}" for k, v in cnt.items()))

    # 组合市值下跌的季度里，加仓的多不多
    totals = []
    for p in periods:
        totals.append(sum(v["value"] for v in H.aggregate(series[p]).values()))
    down_quarters = [i for i in range(1, len(periods)) if totals[i] < totals[i - 1] * 0.95]
    up_quarters = [i for i in range(1, len(periods)) if totals[i] > totals[i - 1] * 1.05]

    def add_rate(indices: list[int]) -> float:
        if not indices:
            return 0.0
        hit = 0
        for i in indices:
            prev, cur = periods[i - 1], periods[i]
            for cusip in track:
                a, b = track[cusip].get(prev), track[cusip].get(cur)
                if a and b and b > a * 1.001:
                    hit += 1
                    break
        return hit / len(indices)

    print(f"\n组合市值大幅下跌（-5% 以上）的季度 {len(down_quarters)} 个，其中至少有一只加仓的比例：{add_rate(down_quarters)*100:.0f}%")
    print(f"组合市值大幅上涨（+5% 以上）的季度 {len(up_quarters)} 个，其中至少有一只加仓的比例：{add_rate(up_quarters)*100:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
