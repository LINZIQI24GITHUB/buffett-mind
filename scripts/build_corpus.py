#!/usr/bin/env python3
"""抓取巴菲特语料并建全文索引。

语料来源（都是公开页面，不需要 key）：
  1. 伯克希尔股东信 1977–2024 —— berkshirehathaway.com/letters
  2. Buffett FAQ —— buffettfaq.com，带出处的问答（含年会年份），补年会/采访

产出：
  corpus/letters/<year>.txt      每封信的纯文本
  corpus/faq.jsonl               每条问答：文本 + 出处 + 年份 + URL
  corpus/index.sqlite            FTS5 全文索引（doc_id, kind, year, source, url, text）

用法：
  python scripts/build_corpus.py --out corpus            # 全量
  python scripts/build_corpus.py --out corpus --limit 3  # 只抓 3 篇，验证用
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

UA = {"User-Agent": "FinanSI research (buffett-mind corpus builder)"}
LETTERS_INDEX = "https://www.berkshirehathaway.com/letters/letters.html"
FAQ_URL = "https://buffettfaq.com/"
SLEEP = 0.3


def fetch(url: str, binary: bool = False):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=40)
            if r.status_code == 200:
                return r.content if binary else r.text
            if r.status_code == 404:
                return None
        except Exception:  # noqa: BLE001 - 网络抖动，重试
            pass
        time.sleep(1.0 + attempt)
    return None


def clean(text: str) -> str:
    text = text.replace("\xa0", " ")
    # FAQ 里用长横线分隔条目，去掉纯分隔行
    text = re.sub(r"^[-_=]{10,}\s*$", "", text, flags=re.M)
    text = text.replace("back to the questions.", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def letter_links() -> list[tuple[int, str]]:
    html = fetch(LETTERS_INDEX)
    if not html:
        raise SystemExit("✗ 股东信索引抓取失败")
    soup = BeautifulSoup(html, "lxml")
    out: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"((?:19|20)\d{2})", href + " " + a.get_text())
        if not m or not re.search(r"\.(html?|pdf)$", href, re.I):
            continue
        year = int(m.group(1))
        if not (1977 <= year <= 2026):
            continue
        url = href if href.startswith("http") else f"https://www.berkshirehathaway.com/letters/{href}"
        out.setdefault(year, url)
    return sorted(out.items())


def letter_text(url: str) -> str:
    if url.lower().endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader

            raw = fetch(url, binary=True)
            if not raw:
                return ""
            reader = PdfReader(io.BytesIO(raw))
            return clean("\n\n".join((p.extract_text() or "") for p in reader.pages))
        except Exception:  # noqa: BLE001
            return ""
    html = fetch(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return clean(soup.get_text("\n"))


def parse_faq(html: str) -> list[dict]:
    """FAQ 每条问答以 <div class="source"> 收尾，正文在它前面。

    用一次深度遍历收集「source div 之外」的文本，遇到 source 就结一条，
    比按分隔线/regex 切更稳（有的条目缺 URL 或 Time）。
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    rows: list[dict] = []
    buf: list[str] = []

    def flush(src_div) -> None:
        body = clean("".join(buf))
        buf.clear()
        body = re.sub(r"\n?\s*(Source|URL|Time):.*$", "", body, flags=re.M | re.S).strip()
        items = [li.get_text(" ", strip=True) for li in src_div.find_all("li")]
        src = next((i.split(":", 1)[1].strip() for i in items if i.lower().startswith("source:")), "")
        url = next((i.split(":", 1)[1].strip() for i in items if i.lower().startswith("url:")), "")
        tmt = next((i.split(":", 1)[1].strip() for i in items if i.lower().startswith("time:")), "")
        if len(body) < 40 or "A compendium of questions" in body[:400]:
            return
        year = None
        for candidate in (tmt, src):
            y = re.search(r"(19|20)\d{2}", candidate)
            if y:
                year = int(y.group(0))
                break
        rows.append({"kind": "faq", "year": year, "source": src[:160],
                     "url": (url if url.startswith("http") else FAQ_URL),
                     "time": tmt, "text": body})

    def walk(node) -> None:
        for child in node.children:
            if isinstance(child, Tag):
                classes = child.get("class") or []
                if "source" in classes:
                    flush(child)
                    continue
                walk(child)
            else:
                buf.append(str(child))

    body_tag = soup.body or soup
    walk(body_tag)
    return rows


def build(out_dir: Path, limit: int | None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    letters_dir = out_dir / "letters"
    letters_dir.mkdir(exist_ok=True)

    links = letter_links()
    if limit:
        links = links[:limit]
    print(f"股东信：{len(links)} 篇（{links[0][0]}–{links[-1][0]}）")

    docs: list[dict] = []
    for i, (year, url) in enumerate(links, 1):
        text = letter_text(url)
        status = f"{len(text):>7} 字符" if text else "失败"
        print(f"  [{i:>2}/{len(links)}] {year}  {status}  {url.rsplit('/', 1)[-1]}")
        if not text:
            continue
        (letters_dir / f"{year}.txt").write_text(text, encoding="utf-8")
        docs.append({"kind": "letter", "year": year, "source": f"{year} 股东信",
                     "url": url, "text": text})
        time.sleep(SLEEP)

    print("Buffett FAQ：抓取并解析")
    html = fetch(FAQ_URL)
    faq_rows = parse_faq(html) if html else []
    (out_dir / "faq.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in faq_rows), encoding="utf-8")
    print(f"  问答条数：{len(faq_rows)}")
    docs.extend(faq_rows)

    db = out_dir / "index.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE docs (id INTEGER PRIMARY KEY, kind TEXT, year INT,
                   source TEXT, url TEXT, text TEXT)""")
    con.execute("CREATE VIRTUAL TABLE docs_fts USING fts5(text, content='docs', content_rowid='id')")
    con.executemany("INSERT INTO docs (kind, year, source, url, text) VALUES (?,?,?,?,?)",
                    [(d["kind"], d.get("year"), d["source"], d["url"], d["text"]) for d in docs])
    con.execute("INSERT INTO docs_fts (docs_fts) VALUES ('rebuild')")
    con.commit()
    n_docs = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    n_letters = con.execute("SELECT COUNT(*) FROM docs WHERE kind='letter'").fetchone()[0]
    chars = con.execute("SELECT SUM(LENGTH(text)) FROM docs").fetchone()[0] or 0
    con.close()

    print(f"\n索引完成：{n_docs} 篇（股东信 {n_letters}）｜共 {chars/1e6:.2f} 百万字符")
    print(f"输出：{out_dir}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="构建巴菲特语料与索引")
    ap.add_argument("--out", default="corpus")
    ap.add_argument("--limit", type=int, default=None, help="只抓前 N 封信，验证用")
    args = ap.parse_args()
    return build(Path(args.out), args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
