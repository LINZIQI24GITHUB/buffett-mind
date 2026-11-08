#!/usr/bin/env python3
"""逐条核对「清仓后再买回」的断档，判断是真实卖出还是解析缺失。

判定逻辑：
  1. 断档中间的每个季度，申报是否成功解析？（持仓数、总额是否合理）
  2. 断档前后的持股数变化是否连续？（例如 100 万股 → 0 → 120 万股，更像真实清仓后买回）
  3. 如果中间季度的持仓数明显异常（例如 <10 只），标记为「疑似解析缺失」

输出：一张核对表 + 汇总。
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import holdings as H  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> int:
    series = H.load(DATA / "holdings.csv")
    ps = list(series)
    pos = {p: i for i, p in enumerate(ps)}

    totals = {p: sum(int(r["value"]) for r in series[p]) / 1e9 for p in ps}
    counts = {p: len({r["cusip"] for r in series[p]}) for p in ps}

    # 按 CUSIP 收集出现的季度
    seen: dict[str, list[int]] = defaultdict(list)
    names: dict[str, str] = {}
    shares: dict[tuple[str, str], int] = {}
    for p in ps:
        agg = H.aggregate(series[p])
        for c, v in agg.items():
            seen[c].append(pos[p])
            names[c] = v["issuer"]
            shares[(c, p)] = v["shares"]

    gaps = []
    for c, idx in seen.items():
        idx = sorted(set(idx))
        for a, b in zip(idx, idx[1:]):
            if b - a > 1:
                gaps.append((c, names[c], ps[a], ps[b], b - a - 1))

    print(f"总额曲线：{ps[0]} ~ {ps[-1]}，{len(ps)} 个季度")
    print(f"  最低 ${min(totals.values()):.1f}B（{min(totals, key=totals.get)}）"
          f"  最高 ${max(totals.values()):.1f}B（{max(totals, key=totals.get)}）")
    print("\n断档核对：")
    print(f"{'发行人':<24}{'前':<12}{'后':<12}{'缺':>3}{'前股数':>12}{'后股数':>12}  判定")
    suspicious = []
    for c, name, before, after, miss in sorted(gaps, key=lambda g: -g[4]):
        mid = ps[pos[before] + 1: pos[after]]
        low = [q for q in mid if counts[q] < 12]
        verdict = "疑似解析缺失" if low else "真实清仓后买回"
        if low:
            suspicious.append((name, low))
        print(f"{name[:22]:<24}{before:<12}{after:<12}{miss:>3}"
              f"{shares[(c, before)]:>12,}{shares[(c, after)]:>12,}  {verdict}")

    print(f"\n合计 {len(gaps)} 处｜疑似解析缺失 {len(suspicious)} 处")
    for name, lows in suspicious:
        print(f"  {name[:24]:<24} 可疑季度：{lows[:4]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
