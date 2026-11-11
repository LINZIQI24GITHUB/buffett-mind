#!/usr/bin/env python3
"""按「披露节奏」做全 A 筛选：选股日放在财报截止日之后，只用当时已公开的报告。

披露截止日（A 股）：
  一季报 4/30 ｜ 中报 8/31 ｜ 三季报 10/31 ｜ 年报 次年 4/30

所以选股日是 5 月初、9 月初、11 月初的第一个交易日。每个时点取「已披露的最新报告」，
季报只用来判断景气（营收/净利同比），十年 ROE 稳定性仍然用年报——避免拿三个月 ROE
去和年度均值比。

用法：
  python scripts/screen_season.py --dates 2025-05-06,2025-09-01,2025-11-03
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 FinanSI", "Referer": "https://data.eastmoney.com/"}
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "screen"
CACHE.mkdir(parents=True, exist_ok=True)

COLS_FIN = ("SECURITY_CODE,SECURITY_NAME_ABBR,REPORTDATE,WEIGHTAVG_ROE,XSMLL,ZXGXL,"
            "YSTZ,SJLTZ,TOTAL_OPERATE_INCOME,PARENT_NETPROFIT")


def page(report: str, columns: str, filt: str, page_no: int, size: int = 500) -> list[dict]:
    params = {"reportName": report, "columns": columns, "filter": filt,
              "pageSize": size, "pageNumber": page_no,
              "sortColumns": "SECURITY_CODE", "sortTypes": 1}
    for _ in range(3):
        try:
            r = requests.get(DC, headers=UA, params=params, timeout=30)
            return (r.json().get("result") or {}).get("data") or []
        except Exception:
            time.sleep(0.5)
    return []


def fetch_all(report: str, columns: str, filt: str, workers: int = 8) -> list[dict]:
    first = page(report, columns, filt, 1)
    if not first:
        return []
    total = len(first)
    out = list(first)
    # 先探一下总页数：不断翻页直到不满
    if total == 500:
        pno = 2
        batches = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            while True:
                futs = [ex.submit(page, report, columns, filt, p) for p in range(pno, pno + workers)]
                got = [f.result() for f in futs]
                for g in got:
                    out.extend(g)
                if any(len(g) < 500 for g in got):
                    break
                pno += workers
    return out



INDUSTRY_RULES = [
    ("白酒", ["酒"]),
    ("医药", ["药", "医疗", "生物", "制药", "疫苗"]),
    ("家电", ["电器", "家电", "厨电"]),
    ("能源", ["能源", "煤", "电力", "燃气", "石油", "石化"]),
    ("化工材料", ["化工", "材料", "化学", "新材"]),
    ("传媒游戏", ["传媒", "互娱", "游戏", "影视", "网络", "分众"]),
    ("电子科技", ["电子", "科技", "光电", "半导体", "通信", "软件", "信息", "智能"]),
    ("纺织服装", ["服饰", "服装", "纺织", "家纺", "鞋"]),
    ("食品饮料", ["食品", "乳业", "露露", "饮品", "饮料"]),
    ("金融", ["银行", "保险", "证券", "信托"]),
    ("地产建筑", ["地产", "置业", "建设", "建筑", "工程", "设计", "技术"]),
]


def industry_of(name: str) -> str:
    for bucket, keys in INDUSTRY_RULES:
        if any(k in name for k in keys):
            return bucket
    return "其他"


def report_period(year: int, kind: str) -> str:
    return {"q1": f"{year}-03-31", "h1": f"{year}-06-30",
            "q3": f"{year}-09-30", "fy": f"{year}-12-31"}[kind]


def latest_reports(asof: str) -> list[str]:
    """返回截至 asof 已披露的报告期（按披露截止日判断）。"""
    y, m, d = map(int, asof.split("-"))
    out = []
    # 年报：次年 4/30
    for year in range(y - 2, y + 1):
        if (year + 1, 4, 30) < (y, m, d) or (year + 1 == y and (m, d) > (4, 30)):
            out.append(report_period(year, "fy"))
    # 一季报：当年 4/30
    if (m, d) > (4, 30):
        out.append(report_period(y, "q1"))
    if (m, d) > (8, 31):
        out.append(report_period(y, "h1"))
    if (m, d) > (10, 31):
        out.append(report_period(y, "q3"))
    return out


def quarterly(period: str) -> list[dict]:
    cache = CACHE / f"q-{period}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    data = fetch_all("RPT_LICO_FN_CPD", COLS_FIN, f"(REPORTDATE='{period}')")
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def valuation(date: str) -> list[dict]:
    cache = CACHE / f"val-{date}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    cols = "SECURITY_CODE,SECURITY_NAME_ABBR,PE_TTM,PB_MRQ,TOTAL_MARKET_CAP"
    data = fetch_all("RPT_VALUEANALYSIS_DET", cols, f"(TRADE_DATE='{date}')")
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", required=True, help="逗号分隔的选股日")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-mcap", type=float, default=3.0)
    ap.add_argument("--tag", default="season")
    ap.add_argument("--dump-all", action="store_true", help="保存全部评分，便于解释调仓")
    args = ap.parse_args()

    for date in [d.strip() for d in args.dates.split(",") if d.strip()]:
        y, m, d = map(int, date.split("-"))
        # 十年年报：第 Y 年年报在 (Y+1)/4/30 之后可用
        annuals_needed = [f"{yy}-12-31" for yy in range(y - 10, y + 1)
                          if (yy, 4, 30) < (y, m, d) or (yy + 1, 4, 30) < (y, m, d)]
        annuals_needed = [p for p in annuals_needed if p <= date][-10:]
        periods = annuals_needed[:]
        # 最新季报（按披露截止日）
        q_candidates = [(f"{yy}-03-31", (yy, 4, 30)) for yy in (y - 1, y)]
        q_candidates += [(f"{yy}-06-30", (yy, 8, 31)) for yy in (y - 1, y)]
        q_candidates += [(f"{yy}-09-30", (yy, 10, 31)) for yy in (y - 1, y)]
        avail_q = [p for p, dl in q_candidates if dl < (y, m, d)]
        latest_q = max(avail_q) if avail_q else None
        if latest_q:
            periods.append(latest_q)
        print(f"\n=== {date}｜已披露 {periods}｜最新季报 {latest_q}", flush=True)

        # 十年年报 ROE / 毛利 / 股息
        stats: dict[str, dict] = {}
        for p in sorted(annuals_needed)[-10:]:
            for r in quarterly(p):
                code = r["SECURITY_CODE"]
                s = stats.setdefault(code, {"name": r.get("SECURITY_NAME_ABBR", ""),
                                            "roes": [], "gms": [], "div": None, "growth": None})
                if r.get("WEIGHTAVG_ROE") is not None:
                    s["roes"].append(r["WEIGHTAVG_ROE"])
                if r.get("XSMLL") is not None:
                    s["gms"].append(r["XSMLL"])
                if r.get("ZXGXL") is not None:
                    s["div"] = r["ZXGXL"]
        if latest_q:
            for r in quarterly(latest_q):
                code = r["SECURITY_CODE"]
                if code in stats and r.get("SJLTZ") is not None:
                    stats[code]["growth"] = r["SJLTZ"]

        vals = valuation(date)
        scored = []
        for v in vals:
            code = v["SECURITY_CODE"]
            s = stats.get(code)
            if not s or len(s["roes"]) < 6:
                continue
            pe = v.get("PE_TTM")
            mcap = v.get("TOTAL_MARKET_CAP") or 0
            if not pe or pe <= 0 or mcap < args.min_mcap * 1e9:
                continue
            name = s["name"]
            if any(k in name for k in ("ST", "退")):
                continue
            roe_mean = sum(s["roes"]) / len(s["roes"])
            roe_min = min(s["roes"])
            roes = s["roes"]
            if len(roes) >= 4 and roes[-1] < roes[-2] < roes[-3] and roes[-1] < roes[0] * 0.7:
                continue  # 连续下滑且累计降幅大，剔除
            gm = sorted(s["gms"])[len(s["gms"]) // 2] if s["gms"] else None
            is_fin = any(k in name for k in ("银行", "保险", "证券", "信托"))
            sc = 0.0
            if roe_mean >= 15 and roe_min >= 10:
                sc += 40
            elif roe_mean >= 12 and roe_min >= 8:
                sc += 25
            elif roe_mean >= 10:
                sc += 10
            if not is_fin and gm is not None:
                sc += 20 if gm >= 40 else (10 if gm >= 25 else 0)
            cap = 10 if is_fin else 20
            sc += 25 if pe <= cap * 0.6 else (18 if pe <= cap else (8 if pe <= cap * 1.5 else 0))
            div = s["div"] or 0
            sc += 15 if div >= 3 else (10 if div >= 2 else (5 if div >= 1 else 0))
            g = s["growth"]
            if g is not None:
                sc += 8 if g > 20 else (4 if g > 0 else (-10 if g < -20 else 0))
            scored.append({"code": code, "name": name, "score": round(sc, 1),
                           "roe_mean": round(roe_mean, 1), "roe_min": round(roe_min, 1),
                           "gm": round(gm, 1) if gm is not None else None,
                           "pe": round(pe, 1), "div": round(div, 2),
                           "growth": round(g, 1) if g is not None else None,
                           "mcap": round(mcap / 1e8, 0)})
        scored.sort(key=lambda x: -x["score"])
        picked, per_ind = [], {}
        for x in scored:
            ind = industry_of(x["name"])
            if per_ind.get(ind, 0) >= 2:
                continue
            per_ind[ind] = per_ind.get(ind, 0) + 1
            x["industry"] = ind
            picked.append(x)
            if len(picked) == args.top:
                break
        print(f"  可评分 {len(scored)}｜行业上限 Top {args.top}")
        for x in picked:
            print(f"  {x['code']} {x['name'][:6]:<8}{x['score']:>6.1f}  ROE {x['roe_mean']:.0f}%"
                  f"/{x['roe_min']:.0f}%  PE {x['pe']:.1f}  增速 {x['growth']}")
        out = CACHE / f"screen-{args.tag}-{date}.json"
        payload = scored if args.dump_all else picked
        if args.dump_all:
            for x in payload:
                x["industry"] = industry_of(x["name"])
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
