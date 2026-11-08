#!/usr/bin/env python3
"""对账：把「他说的」和「他做的」配对，标出冲突与一致。

判定是规则式的，不假装懂语义：
  1. 给每条言论打情绪（负面 / 正面 / 中性），用词表，不猜
  2. 负面言论之后 3 年内出现建仓/加仓 → 冲突候选
     正面言论之后 3 年内出现清仓/大幅减仓 → 冲突候选
  3. 同一实体连续 4 个季度以上单向减仓 → 行为漂移
  4. 行业级言论只算「需语境」，不算明确冲突

输出的是**候选**，不是判决：每条都带原话和操作，让人自己看。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import entities  # noqa: E402
import timeline as T  # noqa: E402

# 只收「评价性」词。own / buy / bought 这类动作词会命中"我们持有……"的陈述句，
# 把中性描述误判成看好，进而把任何减仓都当成矛盾——这是第一版最大的噪声来源。
NEG = ("lousy", "terrible", "bad investment", "avoid", "don't understand", "do not understand",
       "no interest", "too hard", "not for us", "overpriced", "bubble",
       "poor", "difficult", "unattractive", "skeptic", "stupid", "nuts")
POS = ("wonderful", "great business", "great company", "attractive", "cheap", "undervalued",
       "love", "fantastic", "excellent", "moat", "durable competitive", "confident",
       "cheer", "happy", "terrific", "superb")


LISTING = ("such as", "household names", "consist of", "consists of", "include")


def buffett_part(text: str) -> str:
    """FAQ 里常把提问和回答拼在一起，只保留回答部分。"""
    if "WB:" in text:
        return text.split("WB:")[-1]
    if "Buffett:" in text:
        return text.split("Buffett:")[-1]
    m = re.match(r"\s*\[Q[^\]]*\]\s*(.*)$", text, re.S)
    return m.group(1) if m else text


def sentiment(text: str) -> str:
    low = buffett_part(text).lower()
    # 「我们持有苹果、运通等知名公司」是陈述持仓，不是评价
    if any(k in low for k in LISTING):
        return "neu"
    neg = sum(1 for w in NEG if w in low)
    pos = sum(1 for w in POS if w in low)
    if neg > pos:
        return "neg"
    if pos > neg:
        return "pos"
    return "neu"


def names_in(text: str) -> int:
    """一句话里点了多少家公司的名。≥3 基本就是持仓清单，不是观点。"""
    low = text.lower()
    n = 0
    for ticker, info in entities.COMPANIES.items():
        for alias in entities.english_aliases(info):
            if alias.lower() in low:
                n += 1
                break
    return n


def year_of(date: str) -> int:
    m = re.match(r"(\d{4})", date)
    return int(m.group(1)) if m else 0


def consistent(acts: list[dict], qs: list[dict]) -> list[dict]:
    """说看好 → 之后长期持有；说不碰 → 之后确实没买。"""
    out = []
    for q in qs:
        s = sentiment(q["text"])
        y = q["year"] or 0
        if not y or s == "neu":
            continue
        later = [a for a in acts if 0 < year_of(a["date"]) - y <= 3]
        if s == "pos" and later and all(a["kind"] in ("建仓", "加仓") for a in later):
            out.append({"quote_year": y, "text": q["text"], "kind": "看好并加仓"})
        if s == "neg" and not later:
            out.append({"quote_year": y, "text": q["text"], "kind": "看空且未买入"})
    return out


def pair(ticker: str, info: dict) -> dict:
    """把「重大操作」与「前后 2 年内的言论」配对，交给读者判断。

    不做情绪判决：词表法把「房地产泡沫」判成看空富国、把「奥运会赞助」判成
    看空可口可乐，噪声比信号多。这里只负责把证据摆到一起。
    """
    acts = T.actions(ticker, info)
    qs = T.quotes(ticker, info, 40)

    major = []
    for a in acts:
        prev = a.get("prev", 0) or 0
        if a["kind"] in ("建仓", "清仓"):
            major.append(a)
        elif prev and abs(a["shares"]) / prev >= 0.50:
            major.append(a)

    rows = []
    for a in major:
        ay = year_of(a["date"])
        # 只往回看：他说过什么，然后做了什么。
        # 窗口 10 年——巴菲特的"说"和"做"经常隔五六年（2011 讲运通/美银，2017 才行权）。
        near = [q for q in qs if q["year"] and 0 <= ay - q["year"] <= 10
                and names_in(q["text"]) <= 2]
        near = sorted(near, key=lambda q: -q["year"])[:6]
        if not near:
            continue
        for q in near:
            rows.append({"ticker": ticker, "name": info["name"],
                         "action": a["kind"], "action_date": a["date"],
                         "quote_year": q["year"], "text": q["text"], "url": q["url"],
                         "level": "行业" if q.get("scope") == "行业" else "公司"})
    return {"ticker": ticker, "name": info["name"], "acts": len(acts),
            "quotes": len(qs), "rows": rows,
            "major": len(major), "ok": []}


def main() -> int:
    ap = argparse.ArgumentParser(description="言行对账（全实体）")
    ap.add_argument("--limit-detail", type=int, default=12)
    args = ap.parse_args()

    results = [pair(t, i) for t, i in entities.COMPANIES.items()]
    print(f"{'实体':<12}{'行为':>5}{'重大操作':>8}{'言论':>5}{'相邻配对':>8}")
    total = 0
    allrows = []
    for r in results:
        total += len(r["rows"])
        allrows.extend(r["rows"])
        print(f"{r['name']:<12}{r['acts']:>5}{r['major']:>8}{r['quotes']:>5}{len(r['rows']):>8}")
    print(f"\n合计相邻配对 {total} 条（重大操作 × 前后 2 年言论）")

    allrows.sort(key=lambda x: (x["level"] != "公司", -x["quote_year"]))
    for i, x in enumerate(allrows[: args.limit_detail], 1):
        print(f"\n[{i}] {x['name']} · {x['level']}言论 {x['quote_year']} → {x['action_date']} {x['action']}")
        print(f"    原话：{x['text'][:150]}")
        print(f"    出处：{x['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
