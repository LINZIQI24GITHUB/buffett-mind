#!/usr/bin/env python3
"""抓取伯克希尔全部 13F 持仓（含历史分页），整理成逐季明细。

数据源：SEC EDGAR（公开，无需 key）
  1. data.sec.gov/submissions/CIK0001067983.json          近期申报（约 1000 条）
  2. data.sec.gov/submissions/CIK0001067983-submissions-001.json   历史分页（1998–2017）
  3. Archives/edgar/data/<cik>/<accession>/index.json      每次申报的文件清单
  4. 其中的信息表 XML（文件名不固定，靠解析判断）

产出：
  data/holdings/<period>/<accession>.json   单次申报的原始行
  data/holdings.csv                          合并明细
  data/holdings-summary.json                 季度级汇总（供报告用）

注意：
  - 2023 年之前 13F 的 value 单位是「千美元」，之后是「美元」，按申报日切换。
  - 13F-HR/A 是修正版：建表时保留，取某一期时用最新申报覆盖旧版。
"""
from __future__ import annotations

import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from pathlib import Path

from parse_legacy_13f import parse_accession as parse_legacy

UA = {"User-Agent": "FinanSI research buffett-mind/0.1 (contact: research@finansi.local)"}
CIK = 1067983
SUBS = "https://data.sec.gov/submissions/"
ARCH = "https://www.sec.gov/Archives/edgar/data"
SLEEP = 0.15


def get_json(url: str):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (403, 404):
                return None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.8 + attempt)
    return None


def filings() -> list[dict]:
    """近期 + 历史分页，合并所有 13F-HR（含 /A）。"""
    out: list[dict] = []
    base = get_json(f"{SUBS}CIK{CIK:010d}.json")
    if not base:
        raise SystemExit("✗ 取不到 submissions")
    pages = [base["filings"]["recent"]]
    for f in base["filings"].get("files", []):
        p = get_json(f"{SUBS}{f['name']}")
        if p:
            pages.append(p)

    for page in pages:
        forms = page["form"]
        for i, form in enumerate(forms):
            if not form.startswith("13F-HR"):
                continue
            out.append({
                "form": form,
                "accession": page["accessionNumber"][i],
                "filed": page["filingDate"][i],
                "period": page["reportDate"][i],
            })
    out.sort(key=lambda x: (x["period"], x["filed"]))
    return out


def parse_info_table_file(path: Path) -> list[dict] | None:
    try:
        return _parse_xml(path.read_bytes())
    except Exception:  # noqa: BLE001
        return None


def parse_info_table(url: str) -> list[dict] | None:
    try:
        r = requests.get(url, headers=UA, timeout=40)
        if r.status_code != 200:
            return None
        return _parse_xml(r.content)
    except Exception:  # noqa: BLE001
        return None


def _parse_xml(content: bytes) -> list[dict] | None:
    try:
        root = ET.fromstring(content)
    except Exception:  # noqa: BLE001
        return None
    rows: list[dict] = []
    for info in root.iter():
        if info.tag.split("}")[-1] != "infoTable":
            continue
        d: dict = {"shares": None, "share_type": "", "put_call": ""}
        for ch in info:
            tag = ch.tag.split("}")[-1]
            if tag == "shrsOrPrnAmt":
                for sub in ch:
                    st = sub.tag.split("}")[-1]
                    if st == "sshPrnamt":
                        d["shares"] = int(float(sub.text or 0))
                    elif st == "sshPrnamtType":
                        d["share_type"] = (sub.text or "").strip()
            else:
                d[tag] = (ch.text or "").strip()
        if d.get("cusip"):
            rows.append(d)
    return rows or None


def filing_kind(f: dict, out_dir: Path) -> str:
    """区分修正版类型：补报新增、重述、原报。

    "adds new holdings" 的修正版只列出以前保密、现在解禁的持仓，
    不能覆盖原报，必须与原报合并；"restatement" 才是整体替换。
    """
    if not f["form"].endswith("/A"):
        return "original"

    cache_path = out_dir / "amend-kinds.json"
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cache = {}
    if f["accession"] in cache:
        return cache[f["accession"]]

    acc = f["accession"].replace("-", "")
    idx = get_json(f"{ARCH}/{CIK}/{acc}/index.json")
    if not idx:
        return "amendment"
    for item in idx.get("directory", {}).get("item", []):
        name = item["name"]
        if not name.lower().endswith(".txt") or "index" in name.lower():
            continue
        try:
            r = requests.get(f"{ARCH}/{CIK}/{acc}/{name}", headers=UA, timeout=15)
            if r.status_code != 200:
                continue
            low = r.text.lower()
        except Exception:  # noqa: BLE001
            continue
        kind = ("adds" if "adds new holdings" in low
                else "restatement" if "is a restatement" in low else "amendment")
        cache[f["accession"]] = kind
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        return kind
    return "amendment"


RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch_filing(f: dict) -> list[dict] | None:
    acc = f["accession"]
    cache_dir = RAW / acc
    idx = None
    if (cache_dir / "index.json").exists():
        try:
            idx = json.loads((cache_dir / "index.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            idx = None
    if not idx:
        idx = get_json(f"{ARCH}/{CIK}/{acc.replace('-','')}/index.json")
    if not idx:
        return None
    for item in idx.get("directory", {}).get("item", []):
        name = item["name"]
        if not name.lower().endswith(".xml") or "primary_doc" in name.lower():
            continue
        local = cache_dir / name
        rows = parse_info_table_file(local) if local.exists() else \
            parse_info_table(f"{ARCH}/{CIK}/{acc.replace('-','')}/{name}")
        if rows:
            return rows

    # 2013 年之前没有 XML 信息表，退回文本表格解析
    import parse_legacy_13f as P

    local_rows: list[dict] = []
    if cache_dir.exists():
        for doc in sorted(cache_dir.glob("*")):
            if doc.name == "index.json" or not doc.suffix.lower() in (".txt", ".htm", ".html"):
                continue
            try:
                text = doc.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            regions = P.table_regions(text)
            if regions:
                local_rows = P.parse_region("\n".join(regions))
                if len(local_rows) >= 5:
                    break
    legacy = local_rows or parse_legacy(f["accession"])
    if legacy:
        for r in legacy:
            r.setdefault("share_type", "")
        return legacy
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取伯克希尔 13F 全历史")
    ap.add_argument("--out", default="data")
    ap.add_argument("--limit", type=int, default=None, help="只抓最近 N 次，验证用")
    ap.add_argument("--period", default=None, help="只重抓某一季度，其余沿用已有 JSON")
    args = ap.parse_args()
    out_dir = Path(args.out)
    (out_dir / "holdings").mkdir(parents=True, exist_ok=True)

    fl = filings()
    if args.period:
        fl = [f for f in fl if f["period"] == args.period]
    if args.limit:
        fl = fl[-args.limit:]
    print(f"13F 申报：{len(fl)} 次（{fl[0]['period']} ~ {fl[-1]['period']}）")

    records: list[dict] = []
    ok = 0
    kinds: dict[str, str] = {}
    for i, f in enumerate(fl, 1):
        rows = fetch_filing(f)
        if not rows:
            print(f"  [{i:>3}/{len(fl)}] {f['period']} {f['accession']}  解析失败")
            continue
        ok += 1
        kind = kinds[f["accession"]] if f["accession"] in kinds else filing_kind(f, out_dir)
        multiplier = 1000 if f["filed"] < "2023-01-01" else 1
        recs = []
        for r in rows:
            rec = {
                "period": f["period"], "accession": f["accession"], "form": f["form"],
                "amend": kind,
                "filed": f["filed"], "cusip": r.get("cusip", ""),
                "issuer": r.get("nameOfIssuer", ""), "title": r.get("titleOfClass", ""),
                "value": int(float(r.get("value", 0) or 0)) * multiplier,
                "shares": r.get("shares") or 0,
                "share_type": r.get("share_type", ""), "put_call": r.get("put_call", ""),
            }
            recs.append(rec)
            records.append(rec)
        d = out_dir / "holdings" / f["period"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{f['accession']}.json").write_text(
            json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        total = sum(r["value"] for r in recs) / 1e9
        print(f"  [{i:>3}/{len(fl)}] {f['period']}  {len(recs):>3} 行  ${total:>8.1f}B  {f['form']}")
        time.sleep(SLEEP)

    if not records:
        print("✗ 没有任何记录")
        return 1

    import csv

    fields = ["period", "filed", "accession", "form", "amend", "cusip", "issuer", "title",
              "value", "shares", "share_type", "put_call"]
    with (out_dir / "holdings.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(records)

    periods = sorted({r["period"] for r in records})
    summary = {
        "filings_ok": ok,
        "filings_total": len(fl),
        "periods": len(periods),
        "first_period": periods[0],
        "last_period": periods[-1],
        "rows": len(records),
        "cusips": len({r["cusip"] for r in records}),
    }
    (out_dir / "holdings-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成：{len(periods)} 个季度｜{len(records)} 行｜{summary['cusips']} 个 CUSIP")
    print(f"区间：{periods[0]} ~ {periods[-1]}｜输出 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
