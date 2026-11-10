#!/usr/bin/env python3
"""组合回放：从 2024-09-24 起，按季度规则持有四只 A 股，算净值曲线。

规则（来自 replay.py 的季度判定）：
  PE > 25            → 目标仓位 −10 个百分点
  最新年报 ROE < 10% → 清仓
  PE ≤ 15 且 ROE ≥ 15 且仓位 < 25% → +10 个百分点
  其余               → 不动
期末按收盘价再平衡；不计费用与整手限制（会说明）。

数据：eltdx（A 股日线，前复权，含分红再投资），基准用 510300。
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
import pandas as pd  # noqa: E402

LIB = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\lib")
sys.path.insert(0, str(LIB))
from ashare_core.providers.eltdx_provider import EltdxProvider  # noqa: E402
from ashare_core.store import BarsCache  # noqa: E402

DATA = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\a-share-pack\data")
CODES = {"000858": "五粮液", "000651": "格力电器", "000333": "美的集团", "600036": "招商银行"}
START, END = "2024-09-24", "2026-11-09"
CAPITAL = 1_000_000.0
MAX_W = 0.25

# 季度判定结果（replay.py 输出，PE 来自东财历史估值，ROE 来自最新年报）
DECISIONS = {
    "2024-12-31": {"000858": "hold", "000651": "add", "000333": "hold", "600036": "hold"},
    "2025-03-31": {"000858": "hold", "000651": "add", "000333": "hold", "600036": "hold"},
    "2025-06-30": {"000858": "hold", "000651": "add", "000333": "add", "600036": "hold"},
    "2025-09-30": {"000858": "trim", "000651": "hold", "000333": "add", "600036": "hold"},
    "2025-12-31": {"000858": "trim", "000651": "hold", "000333": "add", "600036": "hold"},
    "2026-03-31": {"000858": "trim", "000651": "hold", "000333": "add", "600036": "hold"},
    "2026-06-30": {"000858": "trim", "000651": "hold", "000333": "add", "600036": "hold"},
    "2026-09-30": {"000858": "trim", "000651": "hold", "000333": "add", "600036": "hold"},
}


def load(code: str) -> pd.Series:
    with EltdxProvider() as p:
        cache = BarsCache(p, DATA)
        df = cache.get(code, "2024-09-01", "2026-11-09", "qfq")
    s = pd.Series(df["close"].astype(float).values,
                  index=pd.to_datetime(df["date"].astype(str)))
    return s


def main() -> int:
    px = {c: load(c) for c in CODES}
    bench = load("510300")
    idx = px["000858"].index
    all_days = sorted(set().union(*[set(s.index) for s in px.values()]))
    days = [d for d in all_days if pd.Timestamp(START) <= d <= pd.Timestamp(END)]
    px = {c: s.reindex(days).ffill() for c, s in px.items()}
    bench = bench.reindex(days).ffill()

    weights = {c: 0.0 for c in CODES}
    shares = {c: 0.0 for c in CODES}
    cash = CAPITAL
    start_day = days[0]
    for c in CODES:                      # 初始等权建仓
        price = px[c].loc[start_day]
        budget = CAPITAL * MAX_W
        shares[c] = budget / price
        cash -= budget
        weights[c] = MAX_W

    nav, rows = [], []
    q_ends = [d for d in days
              if (d.month in (3, 6, 9, 12)) and (d + pd.Timedelta(days=1)).month != d.month]
    snapshots: list[dict] = []
    rebal_days = {pd.Timestamp(k): v for k, v in DECISIONS.items()}

    for d in days:
        value = cash + sum(shares[c] * px[c].loc[d] for c in CODES)
        nav.append((d, value))

        if d in rebal_days:
            for c, act in rebal_days[d].items():
                target = weights[c]
                if act == "add":
                    target = min(weights[c] + 0.10, MAX_W)
                elif act == "trim":
                    target = max(weights[c] - 0.10, 0.0)
                elif act == "exit":
                    target = 0.0
                if abs(target - weights[c]) < 1e-9:
                    continue
                # 现金约束：买入不能超过手头现金
                if target > weights[c]:
                    max_add = cash / value
                    target = min(target, weights[c] + max_add)
                price = px[c].loc[d]
                delta_shares = (target - weights[c]) * value / price
                shares[c] += delta_shares
                cash -= delta_shares * price
                weights[c] = target
            # 重算权重
            value = cash + sum(shares[c] * px[c].loc[d] for c in CODES)
            for c in CODES:
                weights[c] = shares[c] * px[c].loc[d] / value

        if d in q_ends:
            v = cash + sum(shares[c] * px[c].loc[d] for c in CODES)
            snapshots.append({"date": d, "value": v, "cash": cash / v,
                              "w": {c: shares[c] * px[c].loc[d] / v for c in CODES}})

    nav_s = pd.Series([v for _, v in nav], index=[d for d, _ in nav])
    cum = nav_s / CAPITAL - 1
    bench_cum = bench / bench.iloc[0] - 1
    peak = nav_s.cummax()
    dd = (nav_s / peak - 1).min()
    years = len(nav_s) / 243
    cagr = (nav_s.iloc[-1] / CAPITAL) ** (1 / years) - 1 if years > 0 else 0

    print(f"区间 {days[0].date()} ~ {days[-1].date()}｜交易日 {len(days)}")
    print(f"期末净值 {nav_s.iloc[-1]:,.0f}｜累计 {cum.iloc[-1]*100:+.2f}%｜年化 {cagr*100:+.2f}%"
          f"｜最大回撤 {dd*100:.2f}%")
    print(f"基准 510300 同期 {bench_cum.iloc[-1]*100:+.2f}%\n")

    # 季度末持仓快照
    print(f"{'季度末':<12}{'五粮液':>10}{'格力':>10}{'美的':>10}{'招行':>10}{'现金':>10}{'净值':>12}")
    for snap in snapshots:
        d, v, w = snap["date"], snap["value"], snap["w"]
        print(f"{d.date()!s:<12}{w['000858']*100:>9.1f}%{w['000651']*100:>9.1f}%"
              f"{w['000333']*100:>9.1f}%{w['600036']*100:>9.1f}%{snap['cash']*100:>9.1f}%{v:>12,.0f}")

    # 净值曲线
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=150)
    fig.patch.set_facecolor("#f4f1e9")
    ax.set_facecolor("none")
    ax.plot(nav_s.index, nav_s.values / CAPITAL * 100, color="#c0392b", lw=1.8, label="组合净值")
    ax.plot(bench.index, (1 + bench_cum.values) * 100, color="#8d8b83", lw=1.2,
            ls=(0, (5, 2)), label="沪深300ETF")
    ax.axhline(100, color="#d9d3c5", lw=0.9)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor="#3d3e3a")
    ax.set_ylabel("净值（起点=100）", fontsize=9, color="#666962")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#ece6d8", lw=0.8)
    ax.tick_params(colors="#666962", labelsize=8, length=0)
    fig.text(0.01, 0.98, "我的 A 股组合（2024-09-24 起）", fontsize=15, fontweight="bold",
             color="#121313", va="top")
    fig.text(0.01, 0.90, "推演 · 非巴菲特本人观点", fontsize=9, color="#666962", va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    out = Path(__file__).resolve().parent.parent / "out" / "portfolio-nav.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="#f4f1e9")
    print(f"\n净值曲线 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
