#!/usr/bin/env python3
"""回答引擎：把「问题」变成一份可回答的证据包。

这个脚本不写结论——它负责把回答一个问题所必需的东西按顺序摆好：

  1. 归类（公司 / 行业 / 资产 / 时机 / 宏观）
  2. 命中哪些规则（references/framework.md 里的 R1–R10）
  3. 他关于同类问题说过什么（原话 + doc_id + 链接，全部可回溯）
  4. 他实际怎么做的（13F 动作 + 季度 + 股数）
  5. 必须标注什么、哪里是边界、证据够不够

结论由调用它的 Agent 基于证据包写，且必须带「推演」标签。

用法：
  python scripts/answer.py --question "现在怎么看黄金"
  python scripts/answer.py --question "苹果还值得长期持有吗" --json
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import entities  # noqa: E402
import timeline as T  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "index.sqlite"
FRAMEWORK = ROOT / "references" / "framework.md"

# 问题类型 → 触发词
TYPES = {
    "公司": ["这家公司", "苹果", "可口可乐", "运通", "银行", "股票", "值不值得买", "能不能买", "持有"],
    "行业": ["行业", "银行股", "航空", "石油", "科技股", "保险", "能源", "半导体"],
    "资产": ["黄金", "比特币", "房地产", "债券", "大宗商品", "原油", "现金"],
    "时机": ["现在", "什么时候", "抄底", "追高", "估值", "贵不贵"],
    "宏观": ["利率", "通胀", "衰退", "经济", "美联储", "汇率"],
}

# 规则 → 触发词
RULES = {
    "R1 能力圈": ["看不懂", "能力圈", "科技", "预测", "十年", "竞争格局"],
    "R2 护城河": ["护城河", "定价权", "提价", "品牌", "转换成本"],
    "R3 安全边际": ["安全边际", "便宜", "贵", "估值", "价格", "内在价值"],
    "R4 长期持有": ["长期", "持有", "拿住", "十年", "复利"],
    "R5 集中": ["集中", "分散", "仓位", "重仓"],
    "R6 少出手": ["机会", "出手", "等待", "现金"],
    "R7 资本配置": ["回购", "分红", "资本配置"],
    "R8 逆向": ["恐惧", "贪婪", "危机", "暴跌", "抄底"],
    "R9 不预测宏观": ["预测", "宏观", "利率", "经济"],
    "R10 认错": ["卖出", "止损", "认错", "清仓"],
    "R11 资产分类": ["黄金", "比特币", "大宗商品", "资产", "现金", "债券", "房地产"],
}

# 中文资产/行业 → 英文检索词（语料是英文的）
THEME_EN = {
    "黄金": ["gold"], "比特币": ["bitcoin", "crypto"], "房地产": ["real estate"],
    "债券": ["bonds"], "大宗商品": ["commodities"], "原油": ["oil", "oil prices"],
    "银行": ["banks", "banking"], "航空": ["airlines"], "科技": ["technology"],
    "保险": ["insurance"], "能源": ["energy"], "半导体": ["semiconductor", "chips"],
    "通胀": ["inflation"], "利率": ["interest rates"], "衰退": ["recession"],
    "现金": ["cash"], "估值": ["valuation", "intrinsic value"],
}

# 主题词（黄金/比特币等）必须和"资产语境"同现，否则会命中 "raining gold" 这类比喻
ASSET_CTX = ("asset", "commodity", "metal", "bullion", "price", "invest", "inflation",
             "hedge", "currency", "store of value", "supply")
THEME_TERMS = {t for ens in THEME_EN.values() for t in ens}

STOP = set("的 了 吗 呢 现在 怎么 如何 什么 值不值得 能不能 应该 请问 一个 这家 这个 我们 the a an is are to of for and or in on with how what should can".split())


def classify(question: str) -> tuple[list[str], str | None, dict | None]:
    types = [t for t, kws in TYPES.items() if any(k in question for k in kws)]
    ticker, info = entities.resolve(question)
    return types, ticker, info


def hit_rules(question: str) -> list[str]:
    return [r for r, kws in RULES.items() if any(k in question for k in kws)]


def search_terms(question: str, ticker: str | None, info: dict | None) -> list[str]:
    terms: list[str] = []
    if info:
        terms.extend(entities.english_aliases(info))
    for cn, ens in THEME_EN.items():
        if cn in question:
            terms.extend(ens)
    # 英文单词直接用
    for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", question):
        if w.lower() not in STOP:
            terms.append(w)
    return list(dict.fromkeys(terms))[:8]


def names_in(text: str) -> int:
    """一句话里点了几家公司的名；≥3 基本是持仓清单，不是观点。"""
    low = text.lower()
    n = 0
    for _t, info in entities.COMPANIES.items():
        for alias in entities.english_aliases(info):
            if alias.lower() in low:
                n += 1
                break
    return n


def quotes(terms: list[str], limit: int = 6) -> tuple[list[dict], int]:
    if not CORPUS.exists():
        return [], 0
    con = sqlite3.connect(CORPUS)
    hits: dict[int, dict] = {}
    scanned = 0
    for term in terms:
        try:
            rows = con.execute(
                "SELECT d.id, d.year, d.source, d.url, "
                "snippet(docs_fts, 0, '【', '】', '…', 45) "
                "FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid "
                "WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?",
                (f'"{term}"', limit * 3)).fetchall()
        except Exception:  # noqa: BLE001
            continue
        for rid, year, source, url, snip in rows:
            scanned += 1
            snip = re.sub(r"\s+", " ", snip).strip()
            if len(snip) < 50 or T.looks_like_table(snip) or not T.is_relevant(snip):
                continue
            if term in THEME_TERMS and not any(w in snip.lower() for w in ASSET_CTX):
                continue
            if names_in(snip) >= 3:
                continue
            hits.setdefault(rid, {"doc": rid, "year": year, "source": source,
                                  "url": url, "text": snip})
    con.close()
    out = sorted(hits.values(), key=lambda h: -(h["year"] or 0))
    return out[:limit], scanned


def industry_members(question: str) -> list[tuple[str, dict]]:
    out = []
    for key, cfg in entities.INDUSTRIES.items():
        if key in question or any(t in question for t in cfg["terms"]):
            out.extend((t, entities.COMPANIES[t]) for t in cfg["tickers"])
    if "银行" in question:
        out.extend((t, entities.COMPANIES[t]) for t in ("BAC", "WFC"))
    return list(dict(out).items())


def acts(ticker: str | None, info: dict | None, limit: int = 8,
         question: str = "") -> list[dict]:
    rows: list[dict] = []
    targets = [(ticker, info)] if ticker and info else industry_members(question)
    for t, i in targets:
        for a in T.actions(t, i)[-limit:]:
            a["name"] = i["name"]
            rows.append(a)
    rows.sort(key=lambda a: a["date"])
    return rows[-limit:]


def build(question: str) -> dict:
    types, ticker, info = classify(question)
    rules = hit_rules(question)
    terms = search_terms(question, ticker, info)
    qs, scanned = quotes(terms)
    actions = acts(ticker, info, question=question)
    return {
        "question": question,
        "types": types or ["未归类"],
        "entity": (info["name"] if info else None),
        "ticker": ticker,
        "rules": rules,
        "terms": terms,
        "quotes": qs,
        "actions": actions,
        "scanned": scanned,
        "enough": len(qs) >= 3,
    }


def render_md(p: dict) -> str:
    L: list[str] = []
    L.append(f"# 证据包：{p['question']}\n")
    L.append(f"- 归类：{'、'.join(p['types'])}" +
             (f"｜实体：{p['entity']}（{p['ticker']}）" if p["entity"] else ""))
    L.append(f"- 命中规则：{'、'.join(p['rules']) if p['rules'] else '（未命中，按通用框架处理）'}")
    L.append(f"- 检索词：{', '.join(p['terms']) if p['terms'] else '（无）'}")
    L.append(f"- 证据量：原话 {len(p['quotes'])} 条（扫描 {p['scanned']} 条）｜操作 {len(p['actions'])} 条\n")

    L.append("## A. 他本人说过什么（逐条可回溯）\n")
    if not p["quotes"]:
        L.append("（没有检索到相关原话——**禁止编造引语**，回答时直接说明他未就此类问题表态）\n")
    for i, q in enumerate(p["quotes"], 1):
        L.append(f"**A{i}** {q['year'] or '年份不详'}｜{q['source']}")
        L.append(f"> {q['text']}")
        L.append(f"出处：{q['url']}（doc {q['doc']}）\n")

    L.append("## B. 他实际怎么做的\n")
    if not p["actions"]:
        L.append("（该问题不涉及具体标的，或标的没有 13F 记录）\n")
    for a in p["actions"]:
        who = f"{a['name']}｜" if a.get("name") else ""
        if a["kind"] == "清仓":
            L.append(f"- {who}{a['date']} 清仓")
        else:
            L.append(f"- {who}{a['date']} {a['kind']} {a['shares']:+,.0f} 股（${a['value']/1e9:.2f}B）")
    L.append("")

    L.append("## C. 回答时必须遵守\n")
    L.append("- 首行标注「**推演 · 非巴菲特本人观点**」")
    L.append("- 每个判断至少挂 1 条 A 类原话 + 1 条 B 类操作；挂不上就降低结论强度")
    L.append("- 引语必须逐字来自 A 类，不得改写、不得编造")
    L.append("- 说明边界：他的框架在什么情况下不适用（能力圈外、无价格记录、非美股）")
    L.append("- 不给买卖建议，不预测点位\n")

    if not p["enough"]:
        L.append("## D. 证据不足提示\n")
        L.append(f"只找到 {len(p['quotes'])} 条原话（阈值 3 条）。回答时**必须**说明：")
        L.append("「他在这个问题上没有可直接引用的表述，以下只是按框架外推。」\n")

    L.append("## E. 相关规则（详见 references/framework.md）\n")
    if not p["rules"]:
        L.append("（未命中具体规则，按 R1 能力圈 + R3 安全边际 的通用顺序推演）")
    for r in p["rules"]:
        L.append(f"- {r}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="把问题变成证据包")
    ap.add_argument("--question", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    packet = build(args.question)
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    else:
        print(render_md(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
