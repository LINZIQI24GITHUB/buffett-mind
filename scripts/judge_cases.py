#!/usr/bin/env python3
"""用「判例」做判断：候选公司 → 他在同类生意上的实际动作与原话。

不做阈值判断。只回答三种情况：
  1. 他在这个行业**买过** → 列出买了什么、理由、结果
  2. 他**明确回避**过 → 列出原话（avoid / never buy / didn't buy / passed）
  3. **没表过态** → 直接说没表态，不外推

用法：
  python scripts/judge_cases.py --name 招商银行
  python scripts/judge_cases.py --name 中际旭创 --industry technology
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "cases.jsonl"

# A 股行业 → 他谈过的行业词
MAP = [
    ("银行", "bank"), ("保险", "insurance"), ("证券", None),
    ("家电", "furniture"), ("电力", "utility"), ("公用", "utility"),
    ("煤", "oil"), ("石油", "oil"), ("石化", "oil"),
    ("航空", "airline"), ("铁路", "railroad"), ("高速", "railroad"),
    ("传媒", "newspaper"), ("出版", "newspaper"), ("报纸", "newspaper"),
    ("零售", "retail"), ("百货", "retail"),
    ("半导体", "technology"), ("光模块", "technology"), ("芯片", "technology"),
    ("软件", "technology"), ("科技", "technology"), ("通信", "technology"),
    ("纺织", "textile"), ("服装", "textile"), ("鞋", "shoe"),
    ("食品", "candy"), ("糖果", "candy"), ("零食", "candy"),
    ("珠宝", "jewelry"),
    ("光模块", "technology"), ("光通信", "technology"), ("光电", "technology"),
    ("旭创", "technology"), ("新易盛", "technology"),
    ("酒", None), ("药", None), ("医疗", None),
    ("矿业", None), ("矿", None), ("化工", None),
]


# 名称里不含行业词的常见公司
COMPANY_MAP = {
    "中国平安": "insurance", "平安银行": "bank", "中国太保": "insurance",
    "中信证券": "securities", "海康威视": "technology", "京东方": "technology",
    "中国神华": "oil", "陕西煤业": "oil", "中国石油": "oil", "中国石化": "oil",
    "京沪高铁": "railroad", "大秦铁路": "railroad", "中国建筑": "construction",
    "万科": "realestate", "保利": "realestate",
}


def industry_of(name: str, override: str | None) -> str | None:
    if override:
        return override
    for k, v in COMPANY_MAP.items():
        if k in name:
            return v
    for kw, ind in MAP:
        if kw in name:
            return ind
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--industry", default=None)
    args = ap.parse_args()

    ind = industry_of(args.name, args.industry)
    cases = [json.loads(l) for l in CASES.open(encoding="utf-8")] if CASES.exists() else []

    print(f"候选：{args.name}｜对应他的行业词：{ind or '无对应'}")
    if not ind:
        print("\n结论：**他没表过态**（语料中没有这个行业的买卖判例）。")
        print("按要求：不外推，不给建议。")
        return 0

    hits = [c for c in cases if ind in c["industries"]]
    buys = [c for c in hits if c["action"] in ("bought", "purchased", "have bought")]
    avoids = [c for c in hits if c["action"] in ("avoid", "never buy", "didn't buy",
                                                 "did not buy", "passed")]

    if not hits:
        print(f"\n结论：**他在「{ind}」上没有判例**，等于没表态。")
        return 0

    print(f"\n他在 {ind} 上的判例：买入 {len(buys)} 条、回避 {len(avoids)} 条")
    for group, label in ((buys, "买入判例"), (avoids, "回避判例")):
        for c in group[:4]:
            print(f"\n  [{label}] {c['year']} doc {c['doc']}（{c['action']}）")
            print(f"    {c['text'][:220]}")

    if buys and not avoids:
        print("\n结论：他在这个行业**买过**——但买的是具体公司，不是行业。")
    elif avoids and not buys:
        print("\n结论：他**明确回避**过这个行业。")
    else:
        print("\n结论：**买过也回避过**——行业不足以判断，要看具体生意。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
