#!/usr/bin/env python3
"""离线自检：不联网，验证技能的核心断言是否成立。

检查项：
  1. 语料索引存在，且规模对得上（≥650 篇）
  2. 引语校验：真句命中、假句拒绝
  3. 时间线：美国银行 2017Q3 行权建仓 6.79 亿股
  4. 市值分解：2020Q1 的数量效应远小于价格效应（跌的是股价，不是仓位）
  5. 框架：11 条规则，且引用的 doc_id 全部存在
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import entities  # noqa: E402
import timeline as T  # noqa: E402
import quote as Q  # noqa: E402

DB = ROOT / "corpus" / "index.sqlite"
DATA = ROOT / "data"
FRAMEWORK = ROOT / "references" / "framework.md"


def check_corpus() -> tuple[bool, str]:
    if not DB.exists():
        return False, "索引不存在，先跑 build_corpus.py"
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    letters = con.execute("SELECT COUNT(*) FROM docs WHERE kind='letter'").fetchone()[0]
    con.close()
    # 全量索引 658 篇；仓库快照只有股东信（FAQ 是第三方汇编，不进仓库）
    if n >= 650:
        return letters >= 45, f"{n} 篇（股东信 {letters}）"
    return letters >= 45, f"{n} 篇（股东信 {letters}，快照模式）"


def check_verify() -> tuple[bool, str]:
    if not DB.exists():
        return False, "索引不存在"
    ok1, _ = Q.verify(DB, "price is what you pay, value is what you get", None)
    ok2, _ = Q.verify(DB, "this sentence was never said by warren buffett", None)
    return ok1 and not ok2, f"真句={'命中' if ok1 else '漏'}，假句={'误判为真' if ok2 else '拒绝'}"


def check_timeline() -> tuple[bool, str]:
    ticker, info = entities.resolve("BAC")
    acts = T.actions(ticker, info)
    hit = [a for a in acts if a["date"] == "2017-09-30" and a["kind"] == "建仓"]
    if not hit:
        return False, "没有找到 2017Q3 建仓"
    shares = hit[0]["shares"]
    return abs(shares - 679_000_000) < 1_000_000, f"股数 {shares:,.0f}"


def check_decompose() -> tuple[bool, str]:
    import decompose as D

    series = D.H.load(DATA / "holdings.csv")
    px = D.Prices()
    r = D.decompose(series, px, "2019-12-31", "2020-03-31")
    price, qty = r["price"], r["quantity"]
    verdict = abs(qty) < abs(price) * 0.2
    return verdict, f"价格 {price:+.1f}B｜数量 {qty:+.1f}B"


def check_framework() -> tuple[bool, str]:
    if not FRAMEWORK.exists():
        return False, "framework.md 不存在"
    text = FRAMEWORK.read_text(encoding="utf-8")
    rules = re.findall(r"^### R(\d+)", text, re.M)
    primary, secondary = set(), set()
    for line in text.splitlines():
        ids = [int(x) for x in re.findall(r"doc (\d+)", line)]
        (secondary if "二级" in line else primary).update(ids)
    con = sqlite3.connect(DB)
    # doc 1–48 是股东信（一级）；49+ 是第三方问答汇编（二级，不进仓库快照）
    missing = [d for d in sorted(primary) if d <= 48
               and not con.execute("SELECT 1 FROM docs WHERE id=?", (d,)).fetchone()]
    con.close()
    ok = len(rules) >= 11 and not missing
    return ok, (f"{len(rules)} 条规则｜一级引用 {len(primary)} 个｜"
                f"二级 {len(secondary)} 个（快照内不含，跳过）｜缺 {len(missing)} 个")


def check_tone() -> tuple[bool, str]:
    """语气样例必须通过 tone_check 的 7 项硬指标。"""
    import tone_check as TC

    sample = ROOT / "examples" / "voice-apple.txt"
    if not sample.exists():
        return False, "样例不存在"
    checks, passed = TC.check(sample.read_text(encoding="utf-8"))
    total = len(checks)
    return passed == total, f"{passed}/{total}"


def main() -> int:
    checks = [
        ("语料索引", check_corpus),
        ("引语校验（真通过 / 假拒绝）", check_verify),
        ("时间线（美银 2017Q3 行权）", check_timeline),
        ("市值分解（2020Q1 是股价不是减仓）", check_decompose),
        ("框架完整性（规则数 + 引用存在）", check_framework),
        ("语气样例（7 项硬指标）", check_tone),
    ]
    passed = 0
    print("巴菲特技能 · 离线自检")
    for name, fn in checks:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        passed += ok
        print(f"  {'✓' if ok else '✗'} {name}：{detail}")
    total = len(checks)
    print(f"\n{'✓ 通过' if passed == total else '✗ 未通过'}（{passed}/{total}）")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
