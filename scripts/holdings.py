#!/usr/bin/env python3
"""伯克希尔 13F 逐季持仓：查询、环比变动、单只标的的时间线。

合并规则（重要）：
  同一季度可能有多份申报，其中 13F-HR/A 有时只列「新增持仓」（3 行），
  直接取最新申报会把整季持仓算成 3 行。所以按期取「行数最多」的那份，
  行数相同再取最新申报日。

用法：
  python scripts/holdings.py periods
  python scripts/holdings.py top --period 2026-06-30
  python scripts/holdings.py changes --period 2026-06-30
  python scripts/holdings.py timeline --issuer APPLE
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def load(path: Path) -> dict[str, list[dict]]:
    """按季度合并申报：原报打底，补报新增的修正版并入，重述版替换。"""
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by_period: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_period[r["period"]].append(r)

    series: dict[str, list[dict]] = {}
    for period, rs in sorted(by_period.items()):
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in rs:
            groups[r["accession"]].append(r)

        def total(acc: str) -> int:
            return sum(int(x["value"] or 0) for x in groups[acc])

        def kind(acc: str) -> str:
            return (groups[acc][0].get("amend") or "original")

        def filed(acc: str) -> str:
            return groups[acc][0]["filed"]

        restatements = [a for a in groups if kind(a) == "restatement"]
        if restatements:
            base = max(restatements, key=filed)
        else:
            pool = [a for a in groups if kind(a) != "adds"] or list(groups)
            base = max(pool, key=total)

        merged: list[dict] = list(groups[base])
        seen = {(r["cusip"], r["shares"], r["value"]) for r in merged}
        for acc in groups:
            if acc == base or kind(acc) != "adds":
                continue
            for r in groups[acc]:
                key = (r["cusip"], r["shares"], r["value"])
                if key not in seen:
                    seen.add(key)
                    merged.append(r)
        series[period] = merged
    return series


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """按 CUSIP 聚合（同一标的可能拆成多行不同类别/权限）。"""
    out: dict[str, dict] = {}
    for r in rows:
        cusip = r["cusip"]
        cur = out.setdefault(cusip, {
            "cusip": cusip, "issuer": r["issuer"], "title": r["title"],
            "shares": 0, "value": 0, "puts": 0, "calls": 0,
        })
        shares = int(r["shares"] or 0)
        value = int(r["value"] or 0)
        pc = (r["put_call"] or "").lower()
        if pc == "put":
            cur["puts"] += shares
        elif pc == "call":
            cur["calls"] += shares
        else:
            cur["shares"] += shares
        cur["value"] += value
        if len(r["issuer"]) > len(cur["issuer"]):
            cur["issuer"] = r["issuer"]
    return out


def short(name: str, n: int = 22) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    return name if len(name) <= n else name[: n - 1] + "…"


def cmd_periods(series) -> int:
    print(f"{'季度':<12}{'持仓数':>7}{'总市值($B)':>12}{'申报日':>13}")
    rows = list(csv.DictReader((DATA / "holdings.csv").open(encoding="utf-8")))
    filed = {r["period"]: r["filed"] for r in rows}
    for period, rs in series.items():
        agg = aggregate(rs)
        total = sum(v["value"] for v in agg.values()) / 1e9
        print(f"{period:<12}{len(agg):>7}{total:>12.1f}{filed.get(period, ''):>13}")
    return 0


def cmd_top(series, period: str, n: int) -> int:
    rs = series.get(period)
    if not rs:
        print(f"✗ 没有 {period} 这一期"); return 1
    agg = aggregate(rs)
    total = sum(v["value"] for v in agg.values())
    ranked = sorted(agg.values(), key=lambda v: -v["value"])
    print(f"{period}  合计 ${total/1e9:.1f}B  持仓 {len(agg)} 只")
    print(f"{'#':>3} {'发行人':<24}{'市值($M)':>10}{'权重':>7}{'股数':>14}")
    for i, v in enumerate(ranked[:n], 1):
        print(f"{i:>3} {short(v['issuer']):<24}{v['value']/1e6:>10.0f}"
              f"{v['value']/total*100:>6.1f}%{v['shares']:>14,}")
    top10 = sum(v["value"] for v in ranked[:10]) / total * 100
    print(f"    前十大占比 {top10:.1f}%")
    return 0


def cmd_changes(series, period: str, n: int) -> int:
    periods = list(series)
    if period not in periods:
        print(f"✗ 没有 {period}"); return 1
    i = periods.index(period)
    if i == 0:
        print("✗ 这是第一期，没有上一期可比"); return 1
    prev, cur = aggregate(series[periods[i - 1]]), aggregate(series[period])
    total = sum(v["value"] for v in cur.values())

    events = []
    for cusip, c in cur.items():
        p = prev.get(cusip)
        if not p or p["shares"] == 0:
            events.append(("新建", c, c["shares"], c["value"]))
        elif c["shares"] > p["shares"]:
            events.append(("加仓", c, c["shares"] - p["shares"], c["value"] - p["value"]))
        elif c["shares"] < p["shares"]:
            events.append(("减仓", c, c["shares"] - p["shares"], c["value"] - p["value"]))
    for cusip, p in prev.items():
        if cusip not in cur:
            events.append(("清仓", p, -p["shares"], -p["value"]))

    order = {"清仓": 0, "新建": 1, "加仓": 2, "减仓": 3}
    events.sort(key=lambda e: (order[e[0]], -abs(e[3])))
    print(f"{periods[i-1]} → {period}   变动 {len(events)} 项")
    print(f"{'动作':<5}{'发行人':<24}{'股数变化':>14}{'市值变化($M)':>14}{'现权重':>8}")
    for act, c, ds, dv in events[:n]:
        w = c["value"] / total * 100 if act != "清仓" else 0.0
        print(f"{act:<5}{short(c['issuer']):<24}{ds:>+14,}{dv/1e6:>+14.0f}{w:>7.1f}%")
    if len(events) > n:
        print(f"    …还有 {len(events)-n} 项")
    return 0


def cmd_timeline(series, keyword: str) -> int:
    kw = keyword.lower()
    print(f"{'季度':<12}{'股数':>14}{'市值($M)':>12}{'权重':>8}")
    last = None
    for period, rs in series.items():
        agg = aggregate(rs)
        total = sum(v["value"] for v in agg.values())
        hit = next((v for v in agg.values() if kw in v["issuer"].lower()), None)
        if hit:
            print(f"{period:<12}{hit['shares']:>14,}{hit['value']/1e6:>12.0f}"
                  f"{hit['value']/total*100:>7.1f}%")
            last = hit
        elif last is not None:
            print(f"{period:<12}{'— 已清仓 —':>14}")
            last = None
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="伯克希尔 13F 查询")
    ap.add_argument("--data", default=str(DATA / "holdings.csv"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("periods").set_defaults(func=lambda a, s: cmd_periods(s))
    t = sub.add_parser("top"); t.add_argument("--period", required=True); t.add_argument("--n", type=int, default=15)
    t.set_defaults(func=lambda a, s: cmd_top(s, a.period, a.n))
    c = sub.add_parser("changes"); c.add_argument("--period", required=True); c.add_argument("--n", type=int, default=15)
    c.set_defaults(func=lambda a, s: cmd_changes(s, a.period, a.n))
    l = sub.add_parser("timeline"); l.add_argument("--issuer", required=True)
    l.set_defaults(func=lambda a, s: cmd_timeline(s, a.issuer))
    args = ap.parse_args()
    series = load(Path(args.data))
    return args.func(args, series)


if __name__ == "__main__":
    raise SystemExit(main())
