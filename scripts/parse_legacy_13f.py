#!/usr/bin/env python3
"""解析 2013 年之前的 13F：那时没有 XML 信息表，只有 SGML/HTML 文本表格。

老格式长这样（固定宽度、可跨行）：

    Name of Issuer    Title of Class  CUSIP     Market Value   Shares ...
    AMERICAN
      EXPRESS CO        COM           025816109      112,209     1,952,142 ...

难点：
  - 发行人名会跨多行，要先把「无 CUSIP 的行」攒起来
  - 市值单位是千美元（2013 年前的惯例）
  - 有的申报是 <TABLE> SGML，有的是 <table> HTML

用法：
  python scripts/parse_legacy_13f.py --accession 0001193125-13-060317   # 单份试跑
"""
from __future__ import annotations

import argparse
import re
import sys

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "FinanSI research buffett-mind/0.1 (contact: research@finansi.local)"}
ARCH = "https://www.sec.gov/Archives/edgar/data/1067983"

CUSIP_RE = re.compile(r"\b([0-9A-Z]{8}[0-9])\b")
ROW_RE = re.compile(r"\b([0-9A-Z]{8}[0-9])\b\s+([\d,]+)\s+([\d,]+)\s*(.*)$")


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=UA, timeout=40)
        return r.text if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


def documents(acc: str) -> list[str]:
    """返回候选文档 URL：优先非 index 的 .txt/.html，最后退回整份提交。"""
    a = acc.replace("-", "")
    urls: list[str] = []
    try:
        r = requests.get(f"{ARCH}/{a}/index.json", headers=UA, timeout=30)
        if r.status_code == 200:
            for it in r.json()["directory"]["item"]:
                name = it["name"]
                if "index" in name.lower() or not name.lower().endswith((".txt", ".htm", ".html")):
                    continue
                urls.append(f"{ARCH}/{a}/{name}")
    except Exception:  # noqa: BLE001
        pass
    urls.append(f"{ARCH}/{a}/{acc}.txt")
    return urls


def table_regions(text: str) -> list[str]:
    """取出表格区域：SGML <TABLE> 或 HTML <table>。"""
    regions: list[str] = []
    for m in re.finditer(r"(?is)<table[^>]*>(.*?)</table>", text):
        regions.append(m.group(1))
    return regions


def strip_tags(region: str) -> str:
    region = re.sub(r"(?is)<caption>.*?</caption>", " ", region)
    region = re.sub(r"(?is)<(s|c|th|td|tr|p|br|page)[^>]*>", "\n", region)
    region = re.sub(r"(?s)<[^>]+>", " ", region)
    return region


def parse_region(region: str) -> list[dict]:
    """同时兼容两种老排版：

    1998 式：CUSIP 被列宽拆成 "025816 10 9"，同一发行人后续批次只列
              市值与股数（续行），没有名称和 CUSIP。
    2012 式：CUSIP 是紧凑 9 位，一行一条。
    """
    text = strip_tags(region)
    lines = [ln.rstrip() for ln in text.splitlines()]
    rows: list[dict] = []
    buf: list[str] = []
    cur: dict | None = None

    # CUSIP 有三种写法：紧凑 9 位、6+3（如 "025816 109"）、6+2+1（如 "025816 10 9"）。
    # 用「三段可选空格」一个正则覆盖，避免每遇到一种排版就漏一张表。
    row_re = re.compile(r"\b([0-9A-Z]{6})\s*([0-9A-Z]{2})\s*([0-9A-Z])\b\s+([\d,]+)\s+([\d,]+)\s*(.*)$")
    cont = re.compile(r"^\s*([\d,]+)\s+([\d,]+)\b(.*)$")

    for line in lines:
        if not line.strip():
            continue
        low = line.lower()
        if re.fullmatch(r"[-=\s<>]+", line):
            continue
        if (re.match(r"^\s*(issuer|name of|title of|class|cusip|market value|shares|column)\b", low)
                or "name of issuer" in low or ("cusip" in low and "value" in low)):
            buf = []
            continue

        m = row_re.search(line)
        if m:
            cusip = (m.group(1) + m.group(2) + m.group(3)).upper()
            value, shares, tail = m.group(4), m.group(5), m.group(6)
            prefix = line[: m.start()].strip()

        if m:
            name_blob = " ".join(buf + ([prefix] if prefix else []))
            buf = []
            parts = re.split(r"\s{2,}", name_blob.strip())
            name = parts[0].strip() if parts else ""
            klass = parts[1].strip() if len(parts) > 1 else ""
            cur = {"name": re.sub(r"\s+", " ", name), "klass": klass, "cusip": cusip}
        elif cur is not None and cont.match(line):
            c = cont.match(line)
            value, shares, tail = c.group(1), c.group(2), c.group(3)
            cusip = cur["cusip"]
        else:
            buf.append(line.strip())
            continue

        pc = ""
        if re.search(r"\bput\b", tail or "", re.I):
            pc = "put"
        elif re.search(r"\bcall\b", tail or "", re.I):
            pc = "call"
        rows.append({
            "nameOfIssuer": cur["name"],
            "titleOfClass": cur["klass"],
            "cusip": cusip,
            "value": int(value.replace(",", "")),
            "shares": int(shares.replace(",", "")),
            "put_call": pc,
        })
    return rows


def parse_accession(acc: str) -> list[dict]:
    for url in documents(acc):
        text = fetch(url)
        if not text:
            continue
        rows: list[dict] = []
        regions = table_regions(text)
        has_cusip = bool(re.search(r"cusip", text, re.I))
        if regions:
            # 表格可能跨页拆成多个 <TABLE>，续行状态要连续，所以拼起来一次解析
            rows = parse_region("\n".join(regions))
        if len(rows) < 5:
            # 老提交里没有 <TABLE> 标签，整份文档按固定宽度文本再试一次
            rows = parse_region(text)
        # 修正版可能只列 2 条新增持仓，阈值放低到 1（有 CUSIP 表头即可信）
        if len(rows) >= 5 or (rows and has_cusip):
            return rows
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="解析老格式 13F")
    ap.add_argument("--accession", required=True)
    args = ap.parse_args()
    rows = parse_accession(args.accession)
    print(f"{args.accession}: {len(rows)} 行")
    total = sum(r["value"] for r in rows)
    print(f"合计市值（千美元）= {total:,}  → ${total/1e6:.1f}B")
    for r in rows[:8]:
        print(f"  {r['nameOfIssuer'][:26]:<26}{r['titleOfClass'][:8]:<9}{r['cusip']}  "
              f"{r['value']:>10,}  {r['shares']:>12,}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
