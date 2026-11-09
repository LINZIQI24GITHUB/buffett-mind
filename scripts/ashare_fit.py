#!/usr/bin/env python3
"""把巴菲特框架接到 A 股：用可量化的代理指标给候选股分档。

背景：巴菲特本人几乎不对 A 股公司表态（658 篇语料里，沪深300 前十大零命中），
所以这不是"他怎么看"，而是"用他的尺子量"。输出必须标「推演」。

尺子（对应 references/framework.md）：
  R2 护城河   → 十年 ROE 均值与最低值 + 毛利率（银行无毛利率口径）
  R3 安全边际 → PE_TTM / PB（粗筛，不等于内在价值）
  R7 资本配置 → 股息率（数据可得时）
  R1 能力圈   → 行业是否属于"十年后可预测"的类型

数据源：东方财富 datacenter-web（只走 HTTPS，不依赖行情推送端口，代理环境下可用）
        --local 走本地 10 年财报（离线，仅覆盖 4 家）

用法：
  python scripts/ashare_fit.py --codes 600519,300750,600036
  python scripts/ashare_fit.py --codes 600519 --local
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FinanSI",
      "Referer": "https://data.eastmoney.com/"}
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"

# 行业归类靠代码映射，不靠公司名——「中际旭创」名字里没有「光模块」，
# 「药明康德」名字里也没有「CXO」。
INDUSTRY = {
    "600519": ("白酒", "in"),
    "000333": ("家电", "in"),
    "600036": ("银行", "in"),
    "601318": ("保险", "in"),
    "600900": ("公用事业", "in"),
    "300750": ("电池制造", "edge"),      # 有 BYD 先例，但技术路线仍要判断
    "601899": ("矿业", "out"),
    "603259": ("CXO", "out"),
    "300308": ("光模块", "out"),
    "300502": ("光模块", "out"),
}
TIER_TEXT = {"in": "能力圈内", "edge": "能力圈边缘", "out": "圈外"}

LOCAL_BASE = pathlib.Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace"
                          r"\finansi\skills-src\company-manual\data")
SLUG = {"600519": "moutai", "300750": "catl", "300308": "zjxc", "601318": "pingan"}


def annual(code: str) -> list[dict]:
    params = {
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,REPORTDATE,WEIGHTAVG_ROE,XSMLL,YSTZ,BASIC_EPS,ZXGXL",
        "filter": f'(SECURITY_CODE="{code}")(REPORTDATE>=\'2014-01-01\')',
        "pageSize": 80, "sortColumns": "REPORTDATE", "sortTypes": -1,
    }
    try:
        r = requests.get(DC, headers=UA, params=params, timeout=20)
        data = r.json().get("result", {}).get("data", [])
    except Exception:  # noqa: BLE001
        return []
    return [x for x in data if str(x.get("REPORTDATE", ""))[5:10] == "12-31"]


def valuation(code: str) -> dict:
    params = {"reportName": "RPT_VALUEANALYSIS_DET", "columns": "ALL",
              "filter": f'(SECURITY_CODE="{code}")', "pageSize": 1,
              "sortColumns": "TRADE_DATE", "sortTypes": -1}
    try:
        r = requests.get(DC, headers=UA, params=params, timeout=20)
        row = (r.json().get("result") or {}).get("data", [{}])[0]
    except Exception:  # noqa: BLE001
        row = {}
    return {"pe": row.get("PE_TTM"), "pb": row.get("PB_MRQ"), "mcap": row.get("TOTAL_MARKET_CAP")}


def metrics(code: str) -> dict | None:
    rows = annual(code)
    if not rows:
        return None
    name = rows[0].get("SECURITY_NAME_ABBR") or code
    roes = [r["WEIGHTAVG_ROE"] for r in rows if r.get("WEIGHTAVG_ROE") is not None]
    gms = [r["XSMLL"] for r in rows if r.get("XSMLL") is not None]
    div = next((r["ZXGXL"] for r in rows if r.get("ZXGXL") is not None), None)
    v = valuation(code)
    return {
        "code": code, "name": name, "years": len(rows),
        "roe_mean": sum(roes) / len(roes) if roes else None,
        "roe_min": min(roes) if roes else None,
        "gm_median": sorted(gms)[len(gms) // 2] if gms else None,
        "div_yield": div, "pe": v["pe"], "pb": v["pb"], "mcap": v["mcap"],
    }


def classify(m: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    roe = m["roe_mean"] / 100 if m["roe_mean"] is not None else None
    roe_min = m["roe_min"] / 100 if m["roe_min"] is not None else None
    gm = m["gm_median"] / 100 if m["gm_median"] is not None else None
    pe = m["pe"]
    is_bank = "银行" in (m["name"] or "")

    moat = False
    if roe is not None and roe >= 0.15 and (roe_min or 0) >= 0.10:
        moat = True
        reasons.append(f"ROE 十年均值 {roe*100:.0f}%、最低 {roe_min*100:.0f}%（稳定）")
    elif roe is not None:
        reasons.append(f"ROE 均值 {roe*100:.0f}%、最低 {(roe_min or 0)*100:.0f}%（不够稳）")

    if gm is not None:
        if gm >= 0.40:
            reasons.append(f"毛利率 {gm*100:.0f}%（定价权）")
        else:
            reasons.append(f"毛利率 {gm*100:.0f}%")
    elif is_bank:
        reasons.append("银行无毛利率口径，用 ROE 与 PB 判断")

    cheap = False
    if pe is not None and pe > 0:
        if pe <= 20:
            cheap = True
            reasons.append(f"PE {pe:.1f} ≤20")
        else:
            reasons.append(f"PE {pe:.1f} >20")

    if m["div_yield"]:
        reasons.append(f"股息率 {m['div_yield']:.2f}%")

    industry, circle = INDUSTRY.get(m["code"], ("未归类", "edge"))
    reasons.append(f"行业：{industry}")
    if circle == "out":
        return f"圈外（{industry}）", reasons + ["R1：行业十年后的竞争格局难预测"]
    if circle == "edge":
        return f"能力圈边缘（{industry}）", reasons + ["有先例但需逐个判断技术路线"]
    if moat and cheap:
        return "能力圈内", reasons
    if moat:
        return "能力圈内（估值不便宜）", reasons
    return "存疑", reasons


def fmt(x, suffix="%", nd=1):
    return f"{x:.{nd}f}{suffix}" if isinstance(x, (int, float)) else "—"


def run_online(codes: list[str]) -> int:
    print("推演 · 非巴菲特本人观点")
    print("尺子：R2 护城河（ROE 十年水平+稳定性、毛利率）· R3 安全边际（PE）· R7 资本配置（股息率）\n")
    print(f"{'代码':<8}{'名称':<10}{'ROE均值':>9}{'ROE最低':>9}{'毛利率':>8}{'PE':>7}{'股息率':>8}  档位")
    ok = 0
    for code in codes:
        m = metrics(code)
        if not m:
            print(f"{code:<8}{'—':<10}  取数失败")
            continue
        ok += 1
        tier, reasons = classify(m)
        print(f"{code:<8}{m['name'][:8]:<10}{fmt(m['roe_mean']):>9}{fmt(m['roe_min']):>9}"
              f"{fmt(m['gm_median']):>8}{fmt(m['pe'], '', 1):>7}{fmt(m['div_yield'], '%', 2):>8}  {tier}")
        print(f"         {'；'.join(reasons)}")
    print(f"\n成功 {ok}/{len(codes)}｜数据：东方财富 datacenter（年报口径，2015 起）")
    print("声明：这是用他的尺子做的粗筛，不是他的判断，也不构成买卖建议")
    return 0


def run_local(codes: list[str]) -> int:
    print("推演 · 非巴菲特本人观点｜本地 10 年财报（离线）\n")
    print(f"{'代码':<8}{'名称':<10}{'年数':>4}{'ROE均值':>9}{'ROE最低':>9}{'毛利率':>8}  档位")
    ok = 0
    for code in codes:
        slug = SLUG.get(code)
        path = LOCAL_BASE / slug / "company.json" if slug else None
        if not path or not path.exists():
            print(f"{code:<8}{'—':<10}  本地无财报")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        fins = [f for f in d.get("financials", []) if f.get("revenue")]
        roes = [(f["net_income"] / (f.get("equity") or f.get("total_equity")))
                for f in fins if f.get("net_income") and (f.get("equity") or f.get("total_equity"))]
        gms = [f["gross_profit"] / f["revenue"] for f in fins if f.get("gross_profit")]
        ok += 1
        m = {"name": d.get("name", slug), "roe_mean": (sum(roes)/len(roes)*100) if roes else None,
             "roe_min": (min(roes)*100) if roes else None,
             "gm_median": (sorted(gms)[len(gms)//2]*100) if gms else None,
             "pe": None, "div_yield": None}
        tier, reasons = classify(m)
        print(f"{code:<8}{m['name'][:8]:<10}{len(fins):>4}{fmt(m['roe_mean']):>9}{fmt(m['roe_min']):>9}"
              f"{fmt(m['gm_median']):>8}  {tier}")
        print(f"         {'；'.join(reasons)}")
    print(f"\n覆盖 {ok}/{len(codes)} 家（本地仅 4 家有完整财报）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="用巴菲特框架给 A 股分档（推演）")
    ap.add_argument("--codes", required=True, help="逗号分隔，如 600519,300750")
    ap.add_argument("--local", action="store_true", help="用本地财报（离线）")
    args = ap.parse_args()
    codes = [str(c).strip().zfill(6) for c in args.codes.split(",") if c.strip()]
    return run_local(codes) if args.local else run_online(codes)


if __name__ == "__main__":
    raise SystemExit(main())
