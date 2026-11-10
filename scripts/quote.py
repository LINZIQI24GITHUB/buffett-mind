#!/usr/bin/env python3
"""在巴菲特语料里检索原话，并校验引用是否真的存在。

为什么单独一个脚本：这个技能的红线是「原话必须可回溯」。
模型可以写分析，但不能自己编一句"巴菲特说过"，所以检索与校验放在工具层，
输出时带上 doc_id / 年份 / 出处，调用方无法绕过。

用法：
  python scripts/quote.py "airlines" --limit 5
  python scripts/quote.py "technology" --year-from 2010 --limit 5
  python scripts/quote.py --verify "price is what you pay" --doc-id 12
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "corpus" / "index.sqlite"


_TYPO = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
         "\u2013": "-", "\u2014": "-", "\u2212": "-"}


def norm(text: str) -> str:
    text = text.replace("\u00a0", " ")
    for k, v in _TYPO.items():
        text = text.replace(k, v)
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def search(db: Path, query: str, limit: int, year_from: int | None, year_to: int | None):
    con = sqlite3.connect(db)
    sql = ("SELECT d.id, d.kind, d.year, d.source, d.url, "
           "snippet(docs_fts, 0, '【', '】', '…', 24) "
           "FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid WHERE docs_fts MATCH ?")
    params: list = [query]
    if year_from:
        sql += " AND d.year >= ?"
        params.append(year_from)
    if year_to:
        sql += " AND d.year <= ?"
        params.append(year_to)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    rows = con.execute(sql, params).fetchall()
    con.close()
    return rows


def verify(db: Path, quote: str, doc_id: int | None) -> tuple[bool, str]:
    con = sqlite3.connect(db)
    sql = "SELECT id, text, source, year FROM docs"
    if doc_id:
        sql += " WHERE id = ?"
        rows = con.execute(sql, (doc_id,)).fetchall()
    else:
        rows = con.execute(sql).fetchall()
    con.close()
    needle = norm(quote)
    for rid, text, source, year in rows:
        if needle in norm(text):
            return True, f"命中 doc {rid}｜{year}｜{source}"
    return False, "未找到原文（拒绝引用）"


def main() -> int:
    ap = argparse.ArgumentParser(description="检索并校验巴菲特原话")
    ap.add_argument("query", nargs="?", help="关键词（FTS5 语法，支持 AND/OR/NEAR）")
    ap.add_argument("--db", default=str(DB))
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--year-from", type=int, default=None)
    ap.add_argument("--year-to", type=int, default=None)
    ap.add_argument("--verify", default=None, help="校验一句话是否真的在语料里")
    ap.add_argument("--doc-id", type=int, default=None)
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"✗ 索引不存在：{db}\n  先跑 python scripts/build_corpus.py --out corpus")
        return 2

    if args.verify:
        ok, msg = verify(db, args.verify, args.doc_id)
        print(f"{'✓' if ok else '✗'} {msg}")
        return 0 if ok else 1

    if not args.query:
        print("✗ 需要关键词，或使用 --verify")
        return 2

    rows = search(db, args.query, args.limit, args.year_from, args.year_to)
    if not rows:
        print("无命中")
        return 0
    for rid, kind, year, source, url, snip in rows:
        tag = "信" if kind == "letter" else "问"
        print(f"[{tag} {rid}] {year or '?'} · {source[:56]}")
        print(f"    {snip}")
        print(f"    {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
