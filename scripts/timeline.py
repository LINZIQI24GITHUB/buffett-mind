#!/usr/bin/env python3
"""某家公司的「言行时间线」：他做了什么（13F）与他讲了什么（语料）按时间交错。

数据来源：
  行为  data/holdings.csv（已做拆股口径、修正版合并）
  言论  corpus/index.sqlite（股东信 + Buffett FAQ，逐条带出处）

输出每行都带来源：
  行为  季度 + 股数变化 + 市值
  言论  年份 + 出处 + 原文片段（FTS 命中，可直接回溯）

用法：
  python scripts/timeline.py --company AAPL
  python scripts/timeline.py --company 苹果 --max-quotes 30
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import entities  # noqa: E402
import holdings as H  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "index.sqlite"

FINANCE_WORDS = ("stock", "shares", "share", "invest", "business", "company", "buy",
                 "bought", "sell", "sold", "hold", "holding", "position", "valu",
                 "price", "earn", "capital", "moat", "brand")


def looks_like_table(text: str) -> bool:
    """股东信里的持仓表会被 FTS 命中，但那不是「观点」。

    判据放宽过一版：只看数字占比会把「回购了多少股」这类正文误杀，
    所以要求同时出现多个金额符号（$ / %）才算表格。
    """
    low = text.lower()
    if any(k in low for k in ("yearend ownership", "berkshire's share in",
                              "retained earnings(2)", "dividends(1)")):
        return True
    if re.search(r"\.{5,}", text):          # 股东信表格用连续句点对齐
        return True
    digits = sum(c.isdigit() for c in text)
    money = text.count("$") + text.count("%")
    if money >= 5 and digits > len(text) * 0.18:
        return True
    return digits > len(text) * 0.28 and money >= 3


def is_relevant(text: str) -> bool:
    low = text.lower()
    if looks_like_table(text):
        return False
    return any(w in low for w in FINANCE_WORDS)


def load_splits() -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    path = DATA / "splits.csv"
    if not path.exists():
        return out
    import csv

    for r in csv.DictReader(path.open(encoding="utf-8")):
        den = float(r["denominator"] or 1)
        if den:
            out.setdefault(r["ticker"], []).append((r["date"], float(r["numerator"]) / den))
    return out


def cusip_tickers() -> dict[str, str]:
    """CUSIP → 代码的映射（OpenFIGI 建好那份），比按名字匹配可靠。"""
    import json

    path = DATA / "cusip-map.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {c: (v.get("ticker") or "").replace("/", "-").upper() for c, v in raw.items()}


def actions(ticker: str, info: dict) -> list[dict]:
    """13F 行为：建仓/加仓/减仓/清仓，股数按拆股口径折算。"""
    series = H.load(DATA / "holdings.csv")
    periods = list(series)
    splits = load_splits()
    sp = splits.get(ticker, [])

    def adj(sh: int, period: str) -> float:
        f = 1.0
        for d, ratio in sp:
            if d > period:
                f *= ratio
        return sh * f

    cmap = cusip_tickers()
    hist: dict[str, float] = {}
    values: dict[str, float] = {}
    for p in periods:
        agg = H.aggregate(series[p])
        for c, v in agg.items():
            mapped = cmap.get(c, "")
            hit = (mapped == ticker.upper()) if mapped else entities.match_issuer(v["issuer"], ticker)
            if hit:
                hist[p] = hist.get(p, 0.0) + adj(v["shares"], p)
                values[p] = values.get(p, 0.0) + v["value"]

    out: list[dict] = []
    prev = 0.0
    for p in periods:
        sh = hist.get(p, 0.0)
        val = values.get(p, 0.0)
        if sh > 0 and prev == 0:
            out.append({"date": p, "kind": "建仓", "shares": sh, "prev": 0, "value": val})
        elif sh == 0 and prev > 0:
            out.append({"date": p, "kind": "清仓", "shares": 0, "prev": prev, "value": 0})
        elif sh > prev * 1.01:
            out.append({"date": p, "kind": "加仓", "shares": sh - prev, "prev": prev, "value": val})
        elif prev > 0 and sh < prev * 0.99:
            out.append({"date": p, "kind": "减仓", "shares": sh - prev, "prev": prev, "value": val})
        prev = sh
    return out


def quotes(ticker: str, info: dict, limit: int) -> list[dict]:
    """语料检索：每个英文别名单独查，按 doc 去重。"""
    if not CORPUS.exists():
        return []
    con = sqlite3.connect(CORPUS)
    hits: dict[int, dict] = {}
    for alias in entities.english_aliases(info):
        query = f'"{alias}"'
        try:
            rows = con.execute(
                "SELECT d.id, d.year, d.source, d.url, "
                "snippet(docs_fts, 0, '【', '】', '…', 45) "
                "FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid "
                "WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?", (query, limit)).fetchall()
        except Exception:  # noqa: BLE001 - 语法不兼容就跳过该别名
            continue
        for rid, year, source, url, snip in rows:
            snip = re.sub(r"\s+", " ", snip).strip()
            if len(snip) < 60 or not is_relevant(snip):
                continue
            if rid not in hits:
                hits[rid] = {"date": f"{year}-??-??" if year else "????", "year": year,
                             "kind": "言论", "source": source, "url": url, "text": snip, "doc": rid}
    industry = entities.industry_of(ticker)
    if industry:
        for term in industry["terms"]:
            try:
                rows = con.execute(
                    "SELECT d.id, d.year, d.source, d.url, "
                    "snippet(docs_fts, 0, '【', '】', '…', 45) "
                    "FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid "
                    "WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?", (f'"{term}"', limit)).fetchall()
            except Exception:  # noqa: BLE001
                continue
            for rid, year, source, url, snip in rows:
                snip = re.sub(r"\s+", " ", snip).strip()
                if len(snip) < 60 or not is_relevant(snip) or rid in hits:
                    continue
                hits[rid] = {"date": f"{year}-??-??" if year else "????", "year": year,
                             "kind": "言论", "scope": "行业", "source": source,
                             "url": url, "text": snip, "doc": rid}
    con.close()
    out = sorted(hits.values(), key=lambda h: (h["year"] or 0))
    return out[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description="言行时间线")
    ap.add_argument("--company", required=True, help="代码 / 中文名 / 英文名")
    ap.add_argument("--max-quotes", type=int, default=25)
    ap.add_argument("--actions-only", action="store_true")
    args = ap.parse_args()

    ticker, info = entities.resolve(args.company)
    if not ticker:
        print(f"✗ 不认识「{args.company}」。已收录：{', '.join(entities.COMPANIES)}")
        return 2

    acts = actions(ticker, info)
    qs = [] if args.actions_only else quotes(ticker, info, args.max_quotes)
    events = acts + qs
    events.sort(key=lambda e: (e["date"], 0 if e["kind"] == "言论" else 1))

    print(f"{info['name']}（{ticker}） 言行时间线｜行为 {len(acts)} 条 · 言论 {len(qs)} 条\n")
    for e in events:
        if e["kind"] == "言论":
            tag = "[行业] " if e.get("scope") == "行业" else ""
            print(f"{e['date'][:4]}  📄 {tag}{e['source'][:30]:<30} {e['text']}")
            print(f"      {e['url']}")
        else:
            sh = e["shares"]
            if e["kind"] == "清仓":
                print(f"{e['date']}  ■ 清仓")
            else:
                print(f"{e['date']}  ■ {e['kind']} {sh:>+14,.0f} 股  ${e['value']/1e9:.2f}B")
    if not events:
        print("（这一家没有可对齐的记录）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
