#!/usr/bin/env python3
"""全 A 股筛选：用估值 + 十年财务，按巴菲特框架给每只股票打分。

数据源：东方财富 datacenter（批量接口，一次一页 500 只）。
  RPT_VALUEANALYSIS_DET  某交易日全市场 PE/PB/总市值
  RPT_LICO_FN_CPD        某报告期全市场 ROE/毛利率/股息率/营收/净利

打分（对应 references/framework.md 的 R2/R3/R7）：
  R2 护城河：十年 ROE 均值 ≥15% 且最低 ≥10%；毛利率中位数 ≥40%（银行无毛利率，单列）
  R3 安全边际：PE_TTM ≤ 20（金融股 ≤ 10）
  R7 资本配置：股息率 ≥ 2%
权重：R2 60%、R3 25%、R7 15%，满分 100。

用法：
  python scripts/screen_market.py --asof 2026-09-30 --top 20
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 FinanSI", "Referer": "https://data.eastmoney.com/"}
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "screen"
CACHE.mkdir(parents=True, exist_ok=True)


def fetch_all(report: str, columns: str, filt: str, sort: str = "SECURITY_CODE",
              page_size: int = 500, limit_pages: int = 40) -> list[dict]:
    out: list[dict] = []
    for page in range(1, limit_pages + 1):
        params = {"reportName": report, "columns": columns, "filter": filt,
                  "pageSize": page_size, "pageNumber": page,
                  "sortColumns": sort, "sortTypes": 1}
        for attempt in range(3):
            try:
                r = requests.get(DC, headers=UA, params=params, timeout=30)
                res = (r.json().get("result") or {})
                data = res.get("data") or []
                break
            except Exception:
                time.sleep(1)
        else:
            break
        out.extend(data)
        if len(data) < page_size:
            break
    return out


def annual_financials(year: int) -> list[dict]:
    cache = CACHE / f"fin-{year}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    cols = ("SECURITY_CODE,SECURITY_NAME_ABBR,WEIGHTAVG_ROE,XSMLL,ZXGXL,"
            "TOTAL_OPERATE_INCOME,PARENT_NETPROFIT")
    data = fetch_all("RPT_LICO_FN_CPD", cols, f"(REPORTDATE='{year}-12-31')")
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def valuation_snapshot(date: str) -> list[dict]:
    cache = CACHE / f"val-{date}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    cols = "SECURITY_CODE,SECURITY_NAME_ABBR,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
    data = fetch_all("RPT_VALUEANALYSIS_DET", cols, f"(TRADE_DATE='{date}')")
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


MIN_MCAP = 3e9


def score(stock: dict) -> dict | None:
    roes = stock["roes"]
    if len(roes) < 6:
        return None
    roe_mean = sum(roes) / len(roes)
    roe_min = min(roes)
    pe = stock.get("pe")
    if pe is None or pe <= 0:
        return None
    mcap = stock.get("mcap") or 0
    if mcap < MIN_MCAP:
        return None
    name = stock["name"]
    if any(k in name for k in ("ST", "退")):
        return None

    is_fin = any(k in name for k in ("银行", "保险", "证券", "信托"))
    gm = stock.get("gm")

    s2 = 0.0
    if roe_mean >= 15 and roe_min >= 10:
        s2 += 40
    elif roe_mean >= 12 and roe_min >= 8:
        s2 += 25
    elif roe_mean >= 10:
        s2 += 10
    if not is_fin and gm is not None:
        if gm >= 40:
            s2 += 20
        elif gm >= 25:
            s2 += 10

    pe_cap = 10 if is_fin else 20
    if pe <= pe_cap * 0.6:
        s3 = 25.0
    elif pe <= pe_cap:
        s3 = 18.0
    elif pe <= pe_cap * 1.5:
        s3 = 8.0
    else:
        s3 = 0.0

    div = stock.get("div") or 0
    s7 = 15.0 if div >= 3 else (10.0 if div >= 2 else (5.0 if div >= 1 else 0.0))

    return {"code": stock["code"], "name": name, "score": round(s2 + s3 + s7, 1),
            "roe_mean": round(roe_mean, 1), "roe_min": round(roe_min, 1),
            "gm": round(gm, 1) if gm is not None else None,
            "pe": round(pe, 1), "div": round(div, 2),
            "mcap": round(mcap / 1e8, 0), "financial": is_fin}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", required=True, help="交易日 YYYY-MM-DD（季度末）")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-mcap", type=float, default=3.0, help="市值下限（十亿）")
    ap.add_argument("--tag", default="", help="输出文件名后缀")
    args = ap.parse_args()

    global MIN_MCAP
    MIN_MCAP = args.min_mcap * 1e9
    year = int(args.asof[:4])
    annuals = {}
    for y in range(year - 10, year):
        rows = annual_financials(y)
        for r in rows:
            code = r["SECURITY_CODE"]
            annuals.setdefault(code, {"roes": [], "gms": [], "div": None})
            if r.get("WEIGHTAVG_ROE") is not None:
                annuals[code]["roes"].append(r["WEIGHTAVG_ROE"])
            if r.get("XSMLL") is not None:
                annuals[code]["gms"].append(r["XSMLL"])
            if r.get("ZXGXL") is not None:
                annuals[code]["div"] = r["ZXGXL"]
        print(f"  年报 {y}: {len(rows)} 只", flush=True)

    vals = valuation_snapshot(args.asof)
    print(f"  估值 {args.asof}: {len(vals)} 只", flush=True)

    stocks = []
    for v in vals:
        code = v["SECURITY_CODE"]
        if code not in annuals:
            continue
        gms = annuals[code]["gms"]
        stocks.append({"code": code, "name": v.get("SECURITY_NAME_ABBR", ""),
                       "pe": v.get("PE_TTM"), "mcap": v.get("TOTAL_MARKET_CAP"),
                       "roes": annuals[code]["roes"],
                       "gm": sorted(gms)[len(gms) // 2] if gms else None,
                       "div": annuals[code].get("div")})

    scored = [s for s in (score(x) for x in stocks) if s]
    scored.sort(key=lambda x: -x["score"])
    print(f"\n可评分 {len(scored)} 只｜Top {args.top}:")
    print(f"{'代码':<8}{'名称':<10}{'分':>6}{'ROE均':>7}{'ROE低':>7}{'毛利':>7}{'PE':>7}{'市值亿':>8}")
    for s in scored[: args.top]:
        print(f"{s['code']:<8}{s['name'][:8]:<10}{s['score']:>6.1f}{s['roe_mean']:>6.1f}%"
              f"{s['roe_min']:>6.1f}%{(s['gm'] if s['gm'] is not None else 0):>7.1f}"
              f"{s['pe']:>7.1f}{s['mcap']:>8.0f}")

    out = CACHE / f"screen{args.tag}-{args.asof}.json"
    out.write_text(json.dumps(scored, ensure_ascii=False), encoding="utf-8")
    print(f"\n已写 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
