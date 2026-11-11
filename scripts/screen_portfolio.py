#!/usr/bin/env python3
"""用全市场筛选结果做组合回测：每个季度末换一次仓，等权持有 Top N。

依赖 screen_market.py 产出的 data/screen/screen-<date>.json。
价格来自 eltdx（A 股日线，前复权）。

用法：
  python scripts/screen_portfolio.py --start 2024-12-31 --end 2026-11-11 --top 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCREEN = ROOT / "data" / "screen"
sys.path.insert(0, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\lib")
from ashare_core.providers.eltdx_provider import EltdxProvider  # noqa: E402
from ashare_core.store import BarsCache  # noqa: E402

DATA = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\data")
CAPITAL = 1_000_000.0


def load_prices(codes: list[str], start: str, end: str) -> dict[str, pd.Series]:
    out = {}
    with EltdxProvider() as p:
        cache = BarsCache(p, DATA)
        for i, c in enumerate(codes):
            try:
                df = cache.get(c, start, end, "qfq")
            except Exception:
                continue
            if df is None or len(df) == 0:
                continue
            s = pd.Series(df["close"].astype(float).values,
                          index=pd.to_datetime(df["date"].astype(str)))
            out[c] = s
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-12-31")
    ap.add_argument("--end", default="2026-11-11")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--tag", default="", help="读取 screen<tag>-*.json")
    args = ap.parse_args()

    screens = sorted(SCREEN.glob(f"screen{args.tag}-*.json"))
    screens = [s for s in screens if args.start <= s.stem.split("-", 1)[1] <= args.end]
    if not screens:
        print("没有筛选结果，先跑 screen_market.py")
        return 2

    picks: dict[str, list[dict]] = {}
    for f in screens:
        date = f.stem.split("-", 1)[1]
        rows = json.loads(f.read_text(encoding="utf-8"))
        picks[date] = rows[: args.top]
        print(f"{date}: " + "、".join(f"{r['name']}({r['score']:.0f})" for r in picks[date]))

    codes = sorted({r["code"] for rows in picks.values() for r in rows})
    px = load_prices(codes + ["510300"], args.start, args.end)
    bench = px.pop("510300")
    px = {c: s for c, s in px.items() if c in codes}
    print(f"\n价格覆盖 {len(px)}/{len(codes)} 只")

    dates = sorted(set().union(*[set(s.index) for s in px.values()], set(bench.index)))
    dates = [d for d in dates if pd.Timestamp(args.start) <= d <= pd.Timestamp(args.end)]
    px = {c: s.reindex(dates).ffill() for c, s in px.items()}
    bench = bench.reindex(dates).ffill()

    rebal = {}
    for date in sorted(picks):
        ts = pd.Timestamp(date)
        after = [d for d in dates if d >= ts]
        if after:
            rebal[after[0]] = picks[date]

    cash, shares = CAPITAL, {}
    nav = []
    for d in dates:
        if d in rebal:
            value = cash + sum(sh * px[c].loc[d] for c, sh in shares.items() if c in px)
            target = [r["code"] for r in rebal[d] if r["code"] in px]
            if not target:
                continue
            alloc = value / len(target)
            shares = {c: alloc / px[c].loc[d] for c in target}
            cash = value - sum(sh * px[c].loc[d] for c, sh in shares.items())
        nav.append((d, cash + sum(sh * px[c].loc[d] for c, sh in shares.items() if c in px)))

    nav_s = pd.Series([v for _, v in nav], index=[d for d, _ in nav])
    bench_n = bench / bench.iloc[0]
    years = len(nav_s) / 243
    ret = nav_s.iloc[-1] / CAPITAL - 1
    cagr = (nav_s.iloc[-1] / CAPITAL) ** (1 / years) - 1
    dd = (nav_s / nav_s.cummax() - 1).min()
    bret = bench_n.iloc[-1] - 1
    bdd = (bench_n / bench_n.cummax() - 1).min()

    print(f"\n区间 {dates[0].date()} ~ {dates[-1].date()}｜{len(nav_s)} 个交易日")
    print(f"组合：{nav_s.iloc[-1]:,.0f}｜累计 {ret*100:+.2f}%｜年化 {cagr*100:+.2f}%｜最大回撤 {dd*100:.2f}%")
    print(f"沪深300ETF：累计 {bret*100:+.2f}%｜最大回撤 {bdd*100:.2f}%")
    print(f"超额：{(ret-bret)*100:+.2f}pp")

    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    fig.patch.set_facecolor("#f4f1e9")
    ax.set_facecolor("none")
    ax.plot(nav_s.index, nav_s / CAPITAL * 100, color="#c0392b", lw=1.8, label="全A筛选组合")
    ax.plot(bench.index, bench_n * 100, color="#8d8b83", lw=1.2, ls=(0, (5, 2)), label="沪深300ETF")
    ax.axhline(100, color="#d9d3c5", lw=0.9)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor="#3d3e3a")
    ax.set_ylabel("净值（起点=100）", fontsize=9, color="#666962")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="y", color="#ece6d8", lw=0.8)
    ax.tick_params(colors="#666962", labelsize=8, length=0)
    fig.text(0.01, 0.98, "全 A 筛选组合（季度换仓）", fontsize=15, fontweight="bold",
             color="#121313", va="top")
    fig.text(0.01, 0.90, "推演 · 非巴菲特本人观点", fontsize=9, color="#666962", va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    out = ROOT / "out" / f"screen-nav{args.tag}.png"
    fig.savefig(out, facecolor="#f4f1e9")
    print(f"\n净值曲线 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
