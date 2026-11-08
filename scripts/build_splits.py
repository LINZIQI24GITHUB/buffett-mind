#!/usr/bin/env python3
"""抓每只标的的拆股事件，用来把 13F 的股数换算到同一口径。

为什么必须做：13F 报的是季度末「实际持股数」，4:1 拆股会让股数直接乘 4；
而 Yahoo 的收盘价已经是拆股调整后的。两边口径不统一，就会把拆股当成
「加仓 700%」，成本被算到拆股后的高价上（苹果 2020-09 就是典型）。

产出 data/splits.csv：ticker, date, numerator, denominator
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 FinanSI buffett-mind"}
DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> int:
    ap = argparse.ArgumentParser(description="抓拆股事件")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    mapping = json.loads((DATA / "cusip-map.json").read_text(encoding="utf-8"))
    tickers = sorted({v["ticker"] for v in mapping.values() if v.get("ticker")})
    if args.limit:
        tickers = tickers[: args.limit]
    print(f"标的数：{len(tickers)}")

    rows: list[dict] = []
    for i, ticker in enumerate(tickers, 1):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        try:
            r = requests.get(url, headers=UA, timeout=30,
                             params={"range": "max", "interval": "1d", "events": "split"})
            if r.status_code != 200:
                print(f"  [{i:>3}/{len(tickers)}] {ticker:<8} HTTP {r.status_code}")
                continue
            res = r.json()["chart"]["result"][0]
            splits = (res.get("events") or {}).get("splits") or {}
            n = 0
            for s in splits.values():
                rows.append({"ticker": ticker, "date": s["date"][:10] if isinstance(s.get("date"), str)
                             else __import__("datetime").datetime.utcfromtimestamp(int(s["date"])) .strftime("%Y-%m-%d"),
                             "numerator": s["numerator"], "denominator": s["denominator"]})
                n += 1
            print(f"  [{i:>3}/{len(tickers)}] {ticker:<8} 拆股 {n} 次")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:>3}/{len(tickers)}] {ticker:<8} 失败 {type(e).__name__}")
        time.sleep(0.25)

    out = DATA / "splits.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "date", "numerator", "denominator"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n拆股事件 {len(rows)} 条｜输出 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
