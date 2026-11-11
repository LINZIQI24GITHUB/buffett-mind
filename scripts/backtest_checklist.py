#!/usr/bin/env python3
"""清单式组合回测：买入「六条全过」的公司，只在某条变否时卖出。

规则（全部来自清单，不用排名）：
  · 每个调仓日，持有「最新一期清单通过」的股票
  · 已持有但本期不通过 → 卖出（对应「conditions change, we sell」）
  · 新通过且未持有 → 买入，与腾出的资金一起等权分配
  · 上限 MAX_HOLD 只，超出时按 PE 从低到高取
  · 不做季度再平衡（对应「when in doubt, we keep holding」）

用法：
  python scripts/backtest_checklist.py --start 2025-05-06 --end 2026-11-11
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "screen"
sys.path.insert(0, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\lib")
from ashare_core.providers.eltdx_provider import EltdxProvider  # noqa: E402
from ashare_core.store import BarsCache  # noqa: E402

DATA = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\data")
CAPITAL = 1_000_000.0
MAX_HOLD = 10


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-05-06")
    ap.add_argument("--end", default="2026-11-11")
    args = ap.parse_args()

    files = sorted(CACHE.glob("checklist-*.json"))
    files = [f for f in files if args.start <= f.stem[-10:] <= args.end]
    if not files:
        print("没有 checklist 结果")
        return 2

    pass_sets: dict[str, dict[str, float]] = {}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        pass_sets[d["date"]] = {r["code"]: r["pe"] for r in d["passed"]}

    codes = sorted({c for s in pass_sets.values() for c in s})
    with EltdxProvider() as p:
        cache = BarsCache(p, DATA)
        px = {}
        for c in codes + ["510300"]:
            try:
                df = cache.get(c, args.start, args.end, "qfq")
                px[c] = pd.Series(df["close"].astype(float).values,
                                  index=pd.to_datetime(df["date"].astype(str)))
            except Exception:
                continue
    bench = px.pop("510300")
    dates = sorted(set().union(*[set(s.index) for s in px.values()], set(bench.index)))
    dates = [d for d in dates if pd.Timestamp(args.start) <= d <= pd.Timestamp(args.end)]
    px = {c: s.reindex(dates).ffill() for c, s in px.items()}
    bench = bench.reindex(dates).ffill()

    rebal = {}
    for date in sorted(pass_sets):
        after = [d for d in dates if d >= pd.Timestamp(date)]
        if after:
            rebal[after[0]] = pass_sets[date]

    cash, shares = CAPITAL, {}
    nav, trades = [], []
    for d in dates:
        if d in rebal:
            ok = rebal[d]
            value = cash + sum(sh * px[c].loc[d] for c, sh in shares.items() if c in px)
            # 卖出不再通过清单的
            for c in list(shares):
                if c not in ok:
                    cash += shares.pop(c) * px[c].loc[d]
                    trades.append((d.date(), "sell", c))
            # 买入新通过的，等权
            targets = [c for c in ok if c not in shares and c in px]
            targets.sort(key=lambda c: ok[c] or 999)
            targets = targets[: max(0, MAX_HOLD - len(shares))]
            if targets:
                alloc = cash / len(targets)
                for c in targets:
                    shares[c] = alloc / px[c].loc[d]
                    cash -= alloc
                    trades.append((d.date(), "buy", c))
        nav.append((d, cash + sum(sh * px[c].loc[d] for c, sh in shares.items() if c in px)))

    nav_s = pd.Series([v for _, v in nav], index=[d for d, _ in nav])
    years = len(nav_s) / 243
    ret = nav_s.iloc[-1] / CAPITAL - 1
    dd = (nav_s / nav_s.cummax() - 1).min()
    b = bench / bench.iloc[0]
    bret = b.iloc[-1] - 1

    print(f"区间 {dates[0].date()} ~ {dates[-1].date()}｜{len(nav_s)} 个交易日")
    print(f"清单组合：{nav_s.iloc[-1]:,.0f}｜累计 {ret*100:+.2f}%｜年化 {((1+ret)**(1/years)-1)*100:+.2f}%"
          f"｜最大回撤 {dd*100:.2f}%")
    print(f"沪深300ETF：累计 {bret*100:+.2f}%")
    print(f"超额：{(ret-bret)*100:+.2f}pp｜交易 {len(trades)} 笔")
    for t in trades:
        print(f"  {t[0]} {t[1]:<4} {t[2]}")

    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    fig.patch.set_facecolor("#f4f1e9")
    ax.set_facecolor("none")
    ax.plot(nav_s.index, nav_s / CAPITAL * 100, color="#c0392b", lw=1.8, label="清单组合")
    ax.plot(bench.index, b * 100, color="#8d8b83", lw=1.2, ls=(0, (5, 2)), label="沪深300ETF")
    ax.axhline(100, color="#d9d3c5", lw=0.9)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor="#3d3e3a")
    ax.set_ylabel("净值（起点=100）", fontsize=9, color="#666962")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="y", color="#ece6d8", lw=0.8)
    ax.tick_params(colors="#666962", labelsize=8, length=0)
    fig.text(0.01, 0.98, "清单式组合（六条全过才买）", fontsize=15, fontweight="bold",
             color="#121313", va="top")
    fig.text(0.01, 0.90, "推演 · 非巴菲特本人观点", fontsize=9, color="#666962", va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    out = ROOT / "out" / "checklist-nav.png"
    fig.savefig(out, facecolor="#f4f1e9")
    print(f"\n净值曲线 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
