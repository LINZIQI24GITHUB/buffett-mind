#!/usr/bin/env python3
"""估值小工具：用他的 10% 折现率 + 你的增长假设，算「合理 PE、合理价、买入价」。

公式来自 1991 年信（doc 15）：增长 g、折现率 r 的永续现金流，价值 = 1/(r-g) 倍盈利。
  合理 PE = 1 / (r − g)
  买入价  = 合理价 × (1 − 安全边际)

r 默认 10%：2003 年问答（doc 159）他明说不会因为国债收益率低就下调门槛。

增长假设是**你的判断**，不是数据能给的——工具只负责把判断翻译成价格。

用法：
  python scripts/valuation.py --code 600519 --growth 8
  python scripts/valuation.py --code 600519 --growth 5 --mos 40 --rate 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\lib")
from ashare_core.providers.eltdx_provider import EltdxProvider  # noqa: E402
from ashare_core.store import BarsCache  # noqa: E402

DATA = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\data")
UA = {"User-Agent": "Mozilla/5.0 FinanSI", "Referer": "https://data.eastmoney.com/"}
DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def latest_pe(code: str) -> tuple[float, str] | None:
    params = {"reportName": "RPT_VALUEANALYSIS_DET", "columns": "TRADE_DATE,PE_TTM",
              "filter": f'(SECURITY_CODE="{code}")', "pageSize": 1,
              "sortColumns": "TRADE_DATE", "sortTypes": -1}
    try:
        row = (requests.get(DC, headers=UA, params=params, timeout=20).json()
               .get("result") or {}).get("data", [{}])[0]
    except Exception:
        return None
    pe = row.get("PE_TTM")
    if not pe or pe <= 0:
        return None
    return float(pe), str(row.get("TRADE_DATE", ""))[:10]


def latest_price(code: str) -> float | None:
    with EltdxProvider() as p:
        df = BarsCache(p, DATA).get(code, "2025-01-01", "2026-11-11", "none")
    return float(df["close"].iloc[-1]) if len(df) else None


def fair_pe(g: float, r: float, terminal: float | None = None, years: int = 3) -> float | None:
    """永续模型；给了 terminal 就用两阶段（前 years 年 g，之后 terminal）。"""
    if terminal is None:
        return 1.0 / (r - g) if r > g else None
    if r <= terminal:
        return None
    pv = sum((1 + g) ** t / (1 + r) ** t for t in range(1, years + 1))
    e = (1 + g) ** years
    pv += (e * (1 + terminal) / (r - terminal)) / (1 + r) ** years
    return pv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True)
    ap.add_argument("--growth", type=float, required=True, help="永续增长假设（百分数，如 8）")
    ap.add_argument("--rate", type=float, default=10.0, help="折现率（百分数，默认 10）")
    ap.add_argument("--mos", type=float, default=30.0, help="安全边际（百分数，默认 30）")
    ap.add_argument("--pe", type=float, default=None, help="手动指定 PE，跳过自动取数")
    ap.add_argument("--two-stage", action="store_true",
                    help="两阶段：前 3 年按 growth 外推，之后按 --terminal 永续（默认 3%%）")
    ap.add_argument("--terminal", type=float, default=3.0, help="永续增速（百分数，默认 3）")
    args = ap.parse_args()

    code = args.code.zfill(6)
    got = (args.pe, "手动") if args.pe else latest_pe(code)
    if not got:
        print("取不到 PE")
        return 2
    pe, asof = got
    price = latest_price(code)

    g, r = args.growth / 100, args.rate / 100
    terminal = args.terminal / 100 if args.two_stage else None
    fp = fair_pe(g, r, terminal)
    print(f"标的 {code}｜PE {pe:.1f}（{asof}）｜现价 {price:.2f}" if price else f"标的 {code}｜PE {pe:.1f}")
    print(f"折现率 {r*100:.0f}%（他的门槛，1991 信 doc 15 / 2003 问答 doc 159）")
    model = (f"两阶段：前 3 年 {g*100:.0f}%，之后永续 {args.terminal:.0f}%"
             if args.two_stage else f"永续增长 {g*100:.0f}%")
    print(f"模型 {model}\n")

    if fp is None:
        print(f"✗ 增长假设 {g*100:.0f}% ≥ 折现率 {r*100:.0f}%，戈登模型无解——这种增长假设本身要打折")
        return 1

    buy_pe = fp * (1 - args.mos / 100)
    print(f"{'指标':<16}{'数值':>12}")
    print(f"{'合理 PE':<16}{fp:>11.1f}x")
    print(f"{'买入 PE 上限':<16}{buy_pe:>11.1f}x   （合理 PE × (1−{args.mos:.0f}%)）")
    print(f"{'当前 PE':<16}{pe:>11.1f}x")
    if price:
        fair_price = price * fp / pe
        buy_price = fair_price * (1 - args.mos / 100)
        print(f"{'合理价':<16}{fair_price:>11.2f}")
        print(f"{'买入价':<16}{buy_price:>11.2f}")
        verdict = "便宜" if price <= buy_price else ("合理但无安全边际" if price <= fair_price else "贵")
        print(f"\n判断：**{verdict}**（现价 {price:.2f} vs 买入价 {buy_price:.2f}）")

    print("\n增长假设敏感性（合理 PE）：")
    for gg in (0, 3, 5, 8, 10, 12, 15):
        v = fair_pe(gg / 100, r, terminal)
        mark = " ←假设" if gg == args.growth else ""
        print(f"  g={gg:>2}% → " + (f"{v:>6.1f}x" if v else "无解") + mark)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
