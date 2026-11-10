#!/usr/bin/env python3
"""季度推演：把「某一天他会买什么」变成一个**逐季变化的过程**。

为什么需要它：他不会买完就不动。每个季度财报出来、股价变了，他都会重新算一遍
「这门生意还值不值这个价」。只看某一天的切片，会把一个持续决策误读成一次性选择。

做法：对每个季度末，用「当时已公布的财报 + 当天收盘估值」重算一次，
按框架给出动作（加仓/持有/减仓/清仓），于是能看到一条决策路径。

数据：东方财富 datacenter（财报 + 历史估值），--asof 控制时点，避免后视镜。

用法：
  python scripts/replay.py --codes 000858,000651,000333,600036 --start 2024-09-30 --end 2026-09-30
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 FinanSI", "Referer": "https://data.eastmoney.com/"}
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def quarters(start: str, end: str) -> list[str]:
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    out = []
    y, m = s.year, s.month
    while True:
        q_end = {3: 3, 6: 6, 9: 9, 12: 12}
        month = min([x for x in q_end if x >= m], default=12)
        d = dt.date(y, month, 1)
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        if d > e:
            break
        if d >= s:
            out.append(d.isoformat())
        # 下一季
        if month == 12:
            y, m = y + 1, 1
        else:
            m = month + 1
    return out


def get(params: dict) -> list[dict]:
    try:
        r = requests.get(DC, headers=UA, params=params, timeout=20)
        return (r.json().get("result") or {}).get("data", []) or []
    except Exception:  # noqa: BLE001
        return []


def snapshot(code: str, asof: str) -> dict | None:
    fin = get({"reportName": "RPT_LICO_FN_CPD",
               "columns": "SECURITY_NAME_ABBR,REPORTDATE,WEIGHTAVG_ROE,XSMLL,ZXGXL",
               "filter": f'(SECURITY_CODE="{code}")(REPORTDATE<=\'{asof}\')',
               "pageSize": 40, "sortColumns": "REPORTDATE", "sortTypes": -1})
    if not fin:
        return None
    # 只用年报：季报的 ROE 是累计值，混用会把 Q1 的 3% 当成年度 ROE
    annuals = [x for x in fin if str(x.get("REPORTDATE", ""))[5:10] == "12-31"]
    roes = [x["WEIGHTAVG_ROE"] for x in annuals if x.get("WEIGHTAVG_ROE") is not None]
    gms = [x["XSMLL"] for x in annuals if x.get("XSMLL") is not None]
    roe_prev = roes[1] if len(roes) > 1 else None
    val = get({"reportName": "RPT_VALUEANALYSIS_DET", "columns": "PE_TTM,PB_MRQ",
               "filter": f'(SECURITY_CODE="{code}")(TRADE_DATE<=\'{asof}\')',
               "pageSize": 1, "sortColumns": "TRADE_DATE", "sortTypes": -1})
    pe = val[0].get("PE_TTM") if val else None
    return {
        "name": fin[0].get("SECURITY_NAME_ABBR", code),
        "annuals": len(annuals),
        "roe_last": roes[0] if roes else None,
        "roe_min": min(roes) if roes else None,
        "gm_last": gms[0] if gms else None,
        "div": next((x["ZXGXL"] for x in annuals if x.get("ZXGXL") is not None), None),
        "roe_prev": roe_prev,
        "pe": pe,
    }


def decide(s: dict, held: bool, weight: float) -> tuple[str, str]:
    roe, roe_min, pe = s["roe_last"], s["roe_min"], s["pe"]
    prev = s.get("roe_prev")
    if prev and roe is not None and prev > 12 and roe < prev * 0.6:
        return "减仓", f"ROE 从 {prev:.0f}% 掉到 {roe:.0f}%，先核实是不是一次性因素"
    if roe is not None and roe < 10:
        return "清仓", f"ROE {roe:.0f}% 破了底线"
    if pe is None:
        return "持有", "缺估值"
    if pe > 30:
        return ("减仓" if held else "不买"), f"PE {pe:.0f} 太贵"
    if pe > 25:
        return ("减仓" if held else "观察"), f"PE {pe:.0f} 偏贵"
    if pe <= 15 and roe is not None and roe >= 15:
        if held and weight >= 0.25:
            return "持有", f"PE {pe:.0f} 便宜，但仓位 {weight:.0%} 已到上限"
        return ("加仓" if held else "建仓"), f"PE {pe:.0f}、ROE {roe:.0f}%"
    return "持有", f"PE {pe:.0f} 合理"


def main() -> int:
    ap = argparse.ArgumentParser(description="季度推演")
    ap.add_argument("--codes", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()
    codes = [c.strip().zfill(6) for c in args.codes.split(",") if c.strip()]
    qs = quarters(args.start, args.end)

    print("推演 · 非巴菲特本人观点｜每个季度用当时已公布的财报重算一次\n")
    for code in codes:
        print(f"### {code}")
        held = False
        weight = 0.0
        for q in qs:
            s = snapshot(code, q)
            if not s:
                print(f"  {q}  取数失败")
                continue
            act, why = decide(s, held, weight)
            if act in ("建仓", "加仓"):
                held = True
                weight = min(weight + 0.1, 0.25)
            elif act == "清仓":
                held, weight = False, 0.0
            elif act == "减仓":
                weight = max(weight - 0.1, 0.0)
            print(f"  {q}  PE {s['pe']:>6.1f}｜ROE {s['roe_last']:>5.1f}%｜毛利 "
                  f"{(s['gm_last'] or 0):>5.1f}%｜股息 {(s['div'] or 0):>4.2f}%  → {act}（{why}）")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
