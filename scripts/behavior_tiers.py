#!/usr/bin/env python3
"""把 13F 持仓按「仓位大小」分层，比较持有期与收益。

问题：13F 的持有中位数 9 季混合了两类完全不同的仓位——
试错型小仓位（1–4 季就清）和核心重仓（20–100 季）。
用中位数当规则是统计误用。这里把两类分开看。

分层标准用的是**仓位权重分位**（数据切分，不是投资判断）：
  取每笔持仓在其存续期内的最大权重，按五分位分组。

用法：
  python scripts/behavior_tiers.py
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import holdings as H  # noqa: E402

DATA = ROOT / "data"
PRICES = DATA / "prices"


def price_return(ticker: str, start: str, end: str) -> float | None:
    f = PRICES / f"{ticker.replace('/', '-')}.csv"
    if not f.exists():
        return None
    rows = [r for r in csv.DictReader(f.open(encoding="utf-8")) if start <= r["date"] <= end]
    if len(rows) < 2:
        return None
    try:
        return float(rows[-1]["adjclose"]) / float(rows[0]["adjclose"]) - 1
    except Exception:
        return None


def main() -> int:
    series = H.load(DATA / "holdings.csv")
    periods = sorted(series)
    cmap = json.loads((DATA / "cusip-map.json").read_text(encoding="utf-8"))

    # 每个 CUSIP 的序列：权重、股数
    weights: dict[str, dict[str, float]] = defaultdict(dict)
    for p in periods:
        agg = H.aggregate(series[p])
        total = sum(v["value"] for v in agg.values()) or 1
        for cusip, v in agg.items():
            weights[cusip][p] = v["value"] / total

    rows = []
    for cusip, w in weights.items():
        ps = sorted(w)
        first, last = ps[0], ps[-1]
        left_censored = first == periods[0]
        max_w = max(w.values())
        hold = periods.index(last) - periods.index(first) + 1
        ticker = (cmap.get(cusip) or {}).get("ticker", "")
        ret = price_return(ticker, first, last) if ticker else None
        rows.append({"cusip": cusip, "first": first, "last": last,
                     "max_w": max_w, "hold": hold, "ret": ret,
                     "censored": left_censored, "ticker": ticker})

    print(f"持仓总数 {len(rows)}｜窗口前已持有（左删失）{sum(1 for r in rows if r['censored'])}")

    # 按最大权重五分位
    rows_sorted = sorted(rows, key=lambda r: r["max_w"])
    n = len(rows_sorted)
    quints = [rows_sorted[i * n // 5:(i + 1) * n // 5] for i in range(5)]

    print(f"\n{'分位':<8}{'样本':>5}{'权重区间':>14}{'中位持有':>9}{'中位收益':>9}{'胜率':>7}{'持有>20季':>10}")
    for i, q in enumerate(quints, 1):
        holds = [x["hold"] for x in q]
        rets = [x["ret"] for x in q if x["ret"] is not None]
        wmin, wmax = min(x["max_w"] for x in q), max(x["max_w"] for x in q)
        win = sum(1 for r in rets if r > 0) / len(rets) * 100 if rets else 0
        long_share = sum(1 for h in holds if h > 20) / len(holds) * 100
        med_ret = statistics.median(rets) * 100 if rets else 0
        print(f"Q{i:<7}{len(q):>5}{f'{wmin*100:.1f}%–{wmax*100:.1f}%':>14}"
              f"{statistics.median(holds):>9.0f}{med_ret:>8.0f}%{win:>6.0f}%{long_share:>9.0f}%")

    # 只看窗口内建仓的（排除左删失）
    fresh = [r for r in rows if not r["censored"]]
    fresh.sort(key=lambda r: r["max_w"])
    n2 = len(fresh)
    quints2 = [fresh[i * n2 // 5:(i + 1) * n2 // 5] for i in range(5)]
    print("\n排除左删失后：")
    for i, q in enumerate(quints2, 1):
        holds = [x["hold"] for x in q]
        rets = [x["ret"] for x in q if x["ret"] is not None]
        wmin, wmax = min(x["max_w"] for x in q), max(x["max_w"] for x in q)
        med_ret = statistics.median(rets) * 100 if rets else 0
        print(f"  Q{i}: 权重 {wmin*100:.1f}%–{wmax*100:.1f}%｜中位持有 {statistics.median(holds):.0f} 季"
              f"｜中位收益 {med_ret:+.0f}%｜样本 {len(q)}")

    # 权重前 20 的持仓明细
    print("\n权重最大的 12 笔：")
    for r in sorted(rows, key=lambda x: -x["max_w"])[:12]:
        ret = f"{r['ret']*100:+.0f}%" if r["ret"] is not None else "—"
        print(f"  {r['ticker'] or r['cusip']:<8}{r['max_w']*100:>6.1f}%"
              f"  {r['first']}→{r['last']}  {r['hold']:>3} 季  {ret}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
