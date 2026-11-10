#!/usr/bin/env python3
"""把 13F 的「股数变化」翻译成「一笔笔决策」，再算事后收益。

一笔持仓 = 连续几个季度持股数 > 0 的一段（建仓 → 清仓，或至今仍持有）。

成本口径：
  建仓当季的 VWAP；若之后有加仓，再按新增股数加权（移动平均）。
  口径前提：假设买入在季内均匀分布。13F 拿不到成交日，这是无偏估计。

收益口径：
  总回报 = 退出季 VWAP（含分红再投资）/ 成本 VWAP（含分红再投资） − 1
  价格收益 = 退出季 VWAP / 成本 VWAP − 1
  仍持有的，退出季用最新可得季度。

用法：
  python scripts/returns.py            # 全部决策，按收益排序
  python scripts/returns.py --top 15
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def load_series() -> dict[str, list[dict]]:
    """复用 holdings.load，保证两处口径一致（含补报合并）。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import holdings as H

    return H.load(DATA / "holdings.csv")


def load_splits() -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    path = DATA / "splits.csv"
    if not path.exists():
        return out
    for r in csv.DictReader(path.open(encoding="utf-8")):
        num = float(r["numerator"] or 0)
        den = float(r["denominator"] or 1)
        if den:
            out[r["ticker"]].append((r["date"], num / den))
    return out


def load_vwap() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for r in csv.DictReader((DATA / "vwap.csv").open(encoding="utf-8")):
        out[(r["cusip"], r["quarter"])] = {
            "vwap": float(r["vwap"]), "adj": float(r["adj_vwap"]),
            "ticker": r["ticker"],
        }
    return out


def quarter_of_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y}-Q{(m - 1) // 3 + 1}"


def positions(series: dict[str, list[dict]]) -> list[dict]:
    periods = list(series)
    held: dict[str, dict[str, int]] = defaultdict(dict)   # cusip -> period -> shares
    names: dict[str, str] = {}
    for period, rows in series.items():
        agg: dict[str, int] = defaultdict(int)
        for r in rows:
            if (r["put_call"] or "").lower():
                continue                                   # 期权不算多头持仓
            agg[r["cusip"]] += int(r["shares"] or 0)
            names[r["cusip"]] = r["issuer"]
        for cusip, sh in agg.items():
            held[cusip][period] = sh

    out: list[dict] = []
    for cusip, by_period in held.items():
        episodes: list[list[tuple[str, int]]] = []
        run: list[tuple[str, int]] = []
        for period in periods:
            sh = by_period.get(period, 0)
            if sh > 0:
                run.append((period, sh))
            elif run:
                episodes.append(run)
                run = []
        if run:
            episodes.append(run)

        prev_exit = None
        for i, ep in enumerate(episodes):
            out.append({
                "cusip": cusip, "name": names[cusip], "episode": ep,
                "seq": i,                 # 第几段持仓（0 = 首次）
                "prev_exit": prev_exit,   # 上一段清仓的季度
            })
            prev_exit = ep[-1][0]
    return out


SPLIT_RATIOS = (1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 20.0)


def is_split(ratio: float, prev_vwap: float, cur_vwap: float) -> float | None:
    """股数突然成倍增加、同时价格反向下跌，判定为拆股而不是加仓。

    13F 报的是季度末实际持股数，4:1 拆股会让股数直接乘 4，
    如果当成买入，成本会被算到拆股后高价上（苹果 2020-09 就是这样）。
    """
    for r in SPLIT_RATIOS:
        if abs(ratio / r - 1) < 0.03:
            price_ratio = prev_vwap / cur_vwap if cur_vwap else 0
            if abs(price_ratio / r - 1) < 0.30:
                return r
    return None


def compute(pos: dict, vwap: dict, first_period: str,
            splits: dict[str, list[tuple[str, float]]]) -> dict | None:
    ep = pos["episode"]
    entry_period, entry_sh = ep[0]
    entry_q = quarter_of_period(entry_period)
    cusip = pos["cusip"]

    cost_v = vwap.get((cusip, entry_q))
    if not cost_v:
        return None
    ticker = cost_v["ticker"]
    sp = splits.get(ticker, [])

    def adj(sh: int, period: str) -> int:
        """把当时股数换算到今天的拆股口径，否则拆股会被当成加仓。"""
        f = 1.0
        for d, ratio in sp:
            if d > period:
                f *= ratio
        return int(round(sh * f))

    ep = [(p_, adj(sh, p_)) for p_, sh in ep]

    # 用「成本池 / 股数」维护每股成本：减仓时按比例缩减成本池，
    # 否则成本会被摊到剩下的小股数上，算出几万块的"成本价"。
    basis = cost_v["vwap"] * entry_sh
    adj_basis = cost_v["adj"] * entry_sh
    qty = entry_sh

    splits = 0
    prev_q_vwap = cost_v["vwap"]
    for period, sh in ep[1:]:
        q = quarter_of_period(period)
        v = vwap.get((cusip, q))
        if sh > qty:
            ratio = sh / qty
            hit = is_split(ratio, prev_q_vwap, v["vwap"] if v else 0)
            if hit:
                splits += 1
                qty = sh                      # 拆股：股数变，成本池不变
            else:
                add = sh - qty
                if v:
                    basis += v["vwap"] * add
                    adj_basis += v["adj"] * add
                qty = sh
        elif sh < qty:
            ratio = sh / qty
            basis *= ratio
            adj_basis *= ratio
            qty = sh

    cost = basis / qty
    cost_adj = adj_basis / qty

    exit_period, exit_sh = ep[-1]
    exit_q = quarter_of_period(exit_period)
    exit_v = vwap.get((cusip, exit_q))
    if not exit_v:
        return None

    total_ret = exit_v["adj"] / cost_adj - 1
    price_ret = exit_v["vwap"] / cost - 1
    return {
        "name": pos["name"], "ticker": exit_v["ticker"], "cusip": cusip,
        "entry": entry_period, "entry_q": entry_q, "exit": exit_period,
        "holding": len(ep), "shares": entry_sh,
        "cost": cost, "last": exit_v["vwap"], "splits": splits,
        "censored": entry_period == first_period,
        "seq": pos.get("seq", 0),
        "prev_exit": pos.get("prev_exit"),
        "total_return": total_ret, "price_return": price_ret,
        "still_held": exit_period == max(exit_period for exit_period in [exit_period]),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="决策级事后收益")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--min-quarters", type=int, default=1)
    args = ap.parse_args()

    series = load_series()
    vwap = load_vwap()
    splits = load_splits()
    latest_period = max(series)
    rows = []
    for pos in positions(series):
        if len(pos["episode"]) < args.min_quarters:
            continue
        rec = compute(pos, vwap, min(series), splits)
        if rec:
            rec["still_held"] = rec["exit"] == latest_period
            rows.append(rec)

    rows.sort(key=lambda r: -r["total_return"])
    print(f"可计算的决策：{len(rows)} 笔（有完整 VWAP 的）\n")
    def kind_of(r: dict) -> str:
        if r.get("seq", 0) > 0 and r.get("prev_exit"):
            return f"重建(前次{r['prev_exit'][:4]})"
        if r.get("censored"):
            return "数据起点"
        return "首次建仓"

    print(f"{'发行人':<20}{'建仓':<12}{'退出':<12}{'季':>4}{'成本':>8}{'最新':>8}"
          f"{'总回报':>8}{'状态':>5}  性质")
    for r in rows[: args.top]:
        state = "持有" if r["still_held"] else "已清"
        print(f"{r['name'][:18]:<20}{r['entry']:<12}{r['exit']:<12}{r['holding']:>4}"
              f"{r['cost']:>8.2f}{r['last']:>8.2f}{r['total_return']*100:>7.0f}%{state:>5}  {kind_of(r)}")
    print("\n最差：")
    for r in rows[-5:]:
        state = "持有" if r["still_held"] else "已清"
        print(f"{r['name'][:18]:<20}{r['entry']:<12}{r['exit']:<12}{r['holding']:>4}"
              f"{r['cost']:>8.2f}{r['last']:>8.2f}{r['total_return']*100:>7.0f}%{state:>5}  {kind_of(r)}")

    if rows:
        wins = [r for r in rows if r["total_return"] > 0]
        print(f"\n胜率 {len(wins)}/{len(rows)} = {len(wins)/len(rows)*100:.0f}%｜"
              f"中位收益 {sorted(r['total_return'] for r in rows)[len(rows)//2]*100:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
