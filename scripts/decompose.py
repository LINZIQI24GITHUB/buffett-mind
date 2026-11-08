#!/usr/bin/env python3
"""把 13F 季度市值变化拆成「价格效应」和「数量效应」。

为什么必须拆：13F 报的是季末市值，市值下跌可能只是股价跌了，仓位一动没动。
直接拿总额变化说「他减仓了」，会把市场下跌误读成主动卖出——这正是我第一版
框架里犯的错（2020Q1 说成「砍仓 27%」，其实全是股价）。

口径：
  价格效应 = Σ(上季股数 × 本季收盘价) − Σ(上季股数 × 上季收盘价)
  数量效应 = Σ(本季股数 × 本季收盘价) − Σ(上季股数 × 本季收盘价)
  股数统一折算到当前拆股口径，否则拆股会被当成加仓。

用法：
  python scripts/decompose.py --from 2020-03-31 --to 2020-06-30
  python scripts/decompose.py --scan          # 扫全历史，列出数量效应最大的季度
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import holdings as H  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def load_ctx():
    cmap = json.loads((DATA / "cusip-map.json").read_text(encoding="utf-8"))
    splits: dict[str, list] = {}
    for row in csv.DictReader((DATA / "splits.csv").open(encoding="utf-8")):
        den = float(row["denominator"] or 1)
        if den:
            splits.setdefault(row["ticker"], []).append(
                (row["date"], float(row["numerator"]) / den))
    return cmap, splits


class Prices:
    def __init__(self) -> None:
        self.cmap, self.splits = load_ctx()
        self.cache: dict[tuple[str, str], float | None] = {}

    def ticker(self, cusip: str) -> str:
        return (self.cmap.get(cusip) or {}).get("ticker", "").replace("/", "-")

    def adj(self, cusip: str, period: str) -> float:
        f = 1.0
        for d, r in self.splits.get(self.ticker(cusip), []):
            if d > period:
                f *= r
        return f

    def close(self, cusip: str, date: str) -> float | None:
        key = (cusip, date)
        if key in self.cache:
            return self.cache[key]
        t = self.ticker(cusip)
        val = None
        f = DATA / "prices" / f"{t}.csv"
        if t and f.exists():
            for row in csv.DictReader(f.open(encoding="utf-8")):
                if row["date"] <= date:
                    val = float(row["close"])
                else:
                    break
        self.cache[key] = val
        return val

    def value(self, period: str, shares: dict[str, int], price_period: str) -> tuple[float, int]:
        total, miss = 0.0, 0
        for c, sh in shares.items():
            px = self.close(c, price_period)
            if not px:
                miss += 1
                continue
            total += sh * self.adj(c, period) * px
        return total / 1e9, miss


def decompose(series: dict, px: Prices, p0: str, p1: str) -> dict:
    a0 = H.aggregate(series[p0])
    a1 = H.aggregate(series[p1])
    s0 = {c: v["shares"] for c, v in a0.items()}
    s1 = {c: v["shares"] for c, v in a1.items()}

    v0, miss = px.value(p0, s0, p0)
    pv, _ = px.value(p0, s0, p1)
    v1, _ = px.value(p1, s1, p1)
    rep0 = sum(v["value"] for v in a0.values()) / 1e9
    rep1 = sum(v["value"] for v in a1.values()) / 1e9
    return {"from": p0, "to": p1, "reported_from": rep0, "reported_to": rep1,
            "recalc_from": v0, "recalc_to": v1,
            "price": pv - v0, "quantity": v1 - pv, "missing": miss}


def show(r: dict) -> None:
    print(f"{r['from']} → {r['to']}")
    print(f"  报告市值 {r['reported_from']:.1f} → {r['reported_to']:.1f}B "
          f"({(r['reported_to']/r['reported_from']-1)*100:+.1f}%)")
    print(f"  价格效应 {r['price']:+.1f}B｜数量效应 {r['quantity']:+.1f}B"
          f"｜缺价 {r['missing']} 只")
    verdict = "几乎全是股价" if abs(r["quantity"]) < abs(r["price"]) * 0.2 else "仓位确有变化"
    print(f"  判断：{verdict}")


def main() -> int:
    ap = argparse.ArgumentParser(description="13F 市值变化分解")
    ap.add_argument("--from", dest="p0")
    ap.add_argument("--to", dest="p1")
    ap.add_argument("--scan", action="store_true")
    args = ap.parse_args()

    series = H.load(DATA / "holdings.csv")
    px = Prices()
    periods = list(series)

    if args.scan:
        rows = []
        for a, b in zip(periods, periods[1:]):
            r = decompose(series, px, a, b)
            rows.append(r)
        rows.sort(key=lambda r: r["quantity"])
        print("数量效应最大的 8 个季度（真正在买卖）：")
        for r in rows[:8]:
            print(f"  {r['to']}  数量 {r['quantity']:+7.1f}B｜价格 {r['price']:+7.1f}B")
        return 0

    if not args.p0 or not args.p1:
        print("✗ 需要 --from/--to，或使用 --scan")
        return 2
    show(decompose(series, px, args.p0, args.p1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
