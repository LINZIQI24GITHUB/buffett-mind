#!/usr/bin/env python3
"""清单式判定：把巴菲特的六个问题变成「是/否 + 证据」，不做打分排序。

和 screen_market.py 的区别：
  · 没有权重、没有总分、没有 Top10
  · 每只股票对六条各自给「是 / 否 / 数据不足」
  · 任何一条为「否」就不买——清单制的通过率天然很低
  · 卖出只在某条从「是」变「否」时发生

六条对应原文（详见 references/framework.md）：
  Q1 十年后还知道它长什么样吗 —— 1998 年会「know what they're going to look like in 10 years」
  Q2 有定价权吗 —— R2 护城河 = 定价权
  Q3 赚的钱怎么分配 —— R7 资本配置
  Q4 这个价格留有余地吗 —— R3 安全边际
  Q5 在我能力圈里吗 —— R1
  Q6 最差年份还赚钱吗 —— 压力测试（他反复讲「坏年份」）

注意：每条判定用的都是**代理指标**（营收稳定性、毛利率、股息率、PE、行业、最差 ROE），
代理不等于他的判断；输出里会写明用了哪个指标。

用法：
  python scripts/screen_checklist.py --dates 2025-05-06,2025-09-01 --top 15
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "screen"

OUT_OF_CIRCLE = ("半导体", "光模块", "芯片", "CXO", "创新药", "矿业", "军工", "软件", "游戏")


def load_period(p: str) -> list[dict]:
    f = CACHE / f"q-{p}.json"
    if not f.exists():
        f = CACHE / f"fin-{p[:4]}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def annuals_upto(date: str) -> list[str]:
    y, m, d = map(int, date.split("-"))
    return [f"{yy}-12-31" for yy in range(y - 10, y + 1)
            if (yy + 1, 4, 30) < (y, m, d)][-10:]


def build_stats(periods: list[str]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for p in periods:
        for r in load_period(p):
            code = r["SECURITY_CODE"]
            s = stats.setdefault(code, {"name": r.get("SECURITY_NAME_ABBR", ""),
                                        "rev": [], "profit": [], "roe": [], "gm": [], "div": None})
            if r.get("TOTAL_OPERATE_INCOME") is not None:
                s["rev"].append(r["TOTAL_OPERATE_INCOME"])
            if r.get("PARENT_NETPROFIT") is not None:
                s["profit"].append(r["PARENT_NETPROFIT"])
            if r.get("WEIGHTAVG_ROE") is not None:
                s["roe"].append(r["WEIGHTAVG_ROE"])
            if r.get("XSMLL") is not None:
                s["gm"].append(r["XSMLL"])
            if r.get("ZXGXL") is not None:
                s["div"] = r["ZXGXL"]
    return stats


def judge(s: dict, pe: float | None, mcap: float) -> dict:
    """六条清单，逐条给「是/否/数据不足」+ 依据。"""
    q: dict[str, dict] = {}

    rev, profit, roe, gm = s["rev"], s["profit"], s["roe"], s["gm"]
    # Q1 可预测性：营收正增长的年份占比 ≥70%，且没有亏损年
    if len(rev) >= 6:
        up = sum(1 for a, b in zip(rev, rev[1:]) if b > a)
        loss = sum(1 for p in profit if p < 0)
        ok = up / max(1, len(rev) - 1) >= 0.7 and loss == 0
        q["Q1"] = {"ok": ok, "why": f"营收增长年 {up}/{len(rev)-1}；亏损年 {loss}"}
    else:
        q["Q1"] = {"ok": None, "why": "营收年限不足"}

    # Q2 定价权：毛利率中位 ≥30% 且最低 ≥20%
    if len(gm) >= 5:
        mid = sorted(gm)[len(gm) // 2]
        lo = min(gm)
        q["Q2"] = {"ok": mid >= 30 and lo >= 20, "why": f"毛利率中位 {mid:.0f}%、最低 {lo:.0f}%"}
    else:
        q["Q2"] = {"ok": None, "why": "毛利率数据不足（可能是金融股）"}

    # Q3 资本配置：股息率 ≥1.5%
    div = s["div"]
    q["Q3"] = {"ok": (div or 0) >= 1.5, "why": f"股息率 {(div or 0):.2f}%"}

    # Q4 价格：PE ≤20（金融 ≤10）
    is_fin = any(k in s["name"] for k in ("银行", "保险", "证券", "信托"))
    cap = 10 if is_fin else 20
    q["Q4"] = {"ok": pe is not None and 0 < pe <= cap,
               "why": f"PE {pe:.1f}（上限 {cap}）" if pe else "PE 缺失"}

    # Q5 能力圈：行业
    out = [k for k in OUT_OF_CIRCLE if k in s["name"]]
    q["Q5"] = {"ok": not out, "why": f"行业关键词 {out}" if out else "非技术迭代行业"}

    # Q6 压力：最差年份 ROE ≥8%
    if len(roe) >= 5:
        lo = min(roe)
        q["Q6"] = {"ok": lo >= 8, "why": f"最差年 ROE {lo:.1f}%"}
    else:
        q["Q6"] = {"ok": None, "why": "ROE 年限不足"}

    passed = all(v["ok"] is True for v in q.values())
    return {"code": "", "name": s["name"], "pe": pe, "mcap": mcap,
            "checks": q, "pass": passed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", required=True)
    ap.add_argument("--top", type=int, default=15, help="通过者超过这个数时按 PE 从低到高取")
    ap.add_argument("--min-mcap", type=float, default=0.0,
                    help="市值下限（十亿）。默认 0＝不设限；他的规模约束是伯克希尔体量所致，"
                         "不是选股标准（1999 年会：需要几十亿美元级别的投资，所以排除很多市场）")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    for date in [d.strip() for d in args.dates.split(",") if d.strip()]:
        periods = annuals_upto(date)
        stats = build_stats(periods)
        vf = CACHE / f"val-{date}.json"
        if not vf.exists():
            print(f"{date}: 缺估值快照")
            continue
        vals = json.loads(vf.read_text(encoding="utf-8"))

        rows = []
        for v in vals:
            code = v["SECURITY_CODE"]
            s = stats.get(code)
            if not s or len(s["roe"]) < 5:
                continue
            mcap = v.get("TOTAL_MARKET_CAP") or 0
            if mcap < args.min_mcap * 1e9:
                continue
            if any(k in s["name"] for k in ("ST", "退")):
                continue
            r = judge(s, v.get("PE_TTM"), mcap)
            r["code"] = code
            rows.append(r)

        passed = [r for r in rows if r["pass"]]
        passed.sort(key=lambda x: (x["pe"] or 999))
        picked = passed[: args.top]
        print(f"\n=== {date}｜候选 {len(rows)}｜六条全过 {len(passed)}｜入选 {len(picked)}")
        for r in picked:
            print(f"  {r['code']} {r['name'][:8]:<10} PE {r['pe']:.1f}  " +
                  "；".join(f"{k}:{v['why']}" for k, v in r["checks"].items()))
        out = CACHE / f"checklist{args.tag}-{date}.json"
        out.write_text(json.dumps({"date": date, "picked": picked,
                                   "passed": [{"code": r["code"], "name": r["name"], "pe": r["pe"]}
                                              for r in passed]}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
