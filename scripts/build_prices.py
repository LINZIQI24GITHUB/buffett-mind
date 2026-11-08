#!/usr/bin/env python3
"""13F 只有 CUSIP 和股数，没有价格。这里补两步：

  1. CUSIP → 代码：OpenFIGI 免费映射（每批 10 个，无需 key）
  2. 日线 → 季度 VWAP：Yahoo chart API（含成交量）

为什么用 VWAP 而不是季末收盘：13F 只告诉你季末持股数，不知道具体哪天买。
若买入在季内均匀分布，成交量加权均价就是成本的无偏估计；季末收盘会系统性
高估成本（实测 KO 1988 高估 12.7%，AAPL 2016Q1 高估 10.6%）。

用法：
  python scripts/build_prices.py            # 全量（映射 + 行情 + VWAP）
  python scripts/build_prices.py --limit 5  # 只处理 5 个 CUSIP，验证用
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 FinanSI buffett-mind"}
DATA = Path(__file__).resolve().parent.parent / "data"
START = "1995-01-01"


def load_cusips(csv_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in csv.DictReader(csv_path.open(encoding="utf-8")):
        c = r["cusip"].strip()
        if c and c not in out:
            out[c] = r["issuer"]
    return out


def map_cusips(cusips: list[str], cache_path: Path) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    todo = [c for c in cusips if c not in cache]
    print(f"CUSIP 映射：已有 {len(cache)} 个，待查 {len(todo)} 个")
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        body = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            r = requests.post("https://api.openfigi.com/v3/mapping", headers=UA, json=body, timeout=30)
            if r.status_code == 200:
                for c, res in zip(batch, r.json()):
                    hit = None
                    if isinstance(res, dict) and res.get("data"):
                        # 只认美国交易所，否则会拿到法兰克福等地代码（如 LEE1EUR），价格对不上
                        us = [d for d in res["data"]
                              if d.get("exchCode") in ("US", "UN", "UW", "UQ")]
                        if us:
                            hit = {"ticker": us[0].get("ticker", ""), "name": us[0].get("name", ""),
                                   "exch": us[0].get("exchCode", "")}
                    cache[c] = hit or {}
        except Exception as e:  # noqa: BLE001
            print(f"  批次 {i//10} 失败：{type(e).__name__}")
        time.sleep(1.2)
        print(f"  {min(i+10, len(todo))}/{len(todo)}")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def yahoo_daily(ticker: str, start: str) -> list[tuple[str, float, float, float]]:
    import datetime as _dt

    p1 = int(_dt.datetime.strptime(start, "%Y-%m-%d").timestamp())
    p2 = int(_dt.datetime.now().timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    try:
        r = requests.get(url, headers=UA, timeout=30,
                         params={"period1": p1, "period2": p2, "interval": "1d"})
        if r.status_code != 200:
            return []
        j = r.json()["chart"]["result"][0]
    except Exception:  # noqa: BLE001
        return []
    ts = j.get("timestamp") or []
    q = j["indicators"]["quote"][0]
    adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(ts)
    out = []
    for t, c, v, a in zip(ts, q["close"], q["volume"], adj):
        if c is None or v in (None, 0):
            continue
        d = dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")
        out.append((d, float(c), float(v), float(a) if a is not None else float(c)))
    return out


def quarter_of(date: str) -> str:
    y, m = int(date[:4]), int(date[5:7])
    q = (m - 1) // 3 + 1
    return f"{y}-Q{q}"


def main() -> int:
    ap = argparse.ArgumentParser(description="CUSIP→代码 + 季度 VWAP")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    (DATA / "prices").mkdir(parents=True, exist_ok=True)
    cusips = load_cusips(DATA / "holdings.csv")
    items = list(cusips.items())
    if args.limit:
        items = items[: args.limit]
    print(f"标的数：{len(items)}（全库 {len(cusips)}）")

    mapping = map_cusips([c for c, _ in items], DATA / "cusip-map.json")

    vwap_rows = []
    for i, (cusip, issuer) in enumerate(items, 1):
        info = mapping.get(cusip) or {}
        ticker = info.get("ticker", "")
        if not ticker:
            print(f"  [{i:>3}/{len(items)}] {cusip} 无映射  {issuer[:30]}")
            continue
        safe = re.sub(r'[<>:"/\\|?*]', "_", ticker)
        cache_file = DATA / "prices" / f"{safe}.csv"
        if cache_file.exists():
            rows = [tuple(r) for r in csv.reader(cache_file.open(encoding="utf-8"))][1:]
            rows = [(d, float(c), float(v), float(a)) for d, c, v, a in rows]
        else:
            rows = yahoo_daily(ticker, START)
            with cache_file.open("w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["date", "close", "volume", "adjclose"])
                w.writerows(rows)
            time.sleep(0.3)

        buckets: dict[str, list] = {}
        for d, c, v, a in rows:
            buckets.setdefault(quarter_of(d), []).append((c, v, a))
        for q, vals in buckets.items():
            vol = sum(v for _, v, _ in vals)
            if vol <= 0:
                continue
            vwap = sum(c * v for c, v, _ in vals) / vol
            avwap = sum(a * v for _, v, a in vals) / vol
            vwap_rows.append({"cusip": cusip, "ticker": ticker, "quarter": q,
                              "vwap": round(vwap, 4), "adj_vwap": round(avwap, 4),
                              "days": len(vals), "volume": int(vol)})
        print(f"  [{i:>3}/{len(items)}] {ticker:<8} {len(rows):>5} 根  {len(buckets)} 季  {issuer[:26]}")

    out = DATA / "vwap.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["cusip", "ticker", "quarter", "vwap", "adj_vwap", "days", "volume"])
        w.writeheader()
        w.writerows(vwap_rows)
    print(f"\nVWAP 行数：{len(vwap_rows)}｜输出 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
