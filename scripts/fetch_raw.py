#!/usr/bin/env python3
"""把 13F 原始文件下载到本地缓存，供离线解析。

为什么要拆成两步：
  SEC 平均 1–2 秒才返回一个文件，211 份申报要几百次请求；直接边下边解析，
  改一次解析逻辑就得重新联网跑十几分钟。拆开之后：
    1) 本脚本只负责下载，可断点续传（已存在就跳过）
    2) build_holdings 只读本地缓存，重建一次几秒钟，且结果可复现

缓存布局：
  data/raw/<accession>/index.json          文件清单
  data/raw/<accession>/<doc>               信息表 XML 或老格式文本
  data/raw/manifest.json                   申报元数据（period/form/filed/accession）

用法：
  python scripts/fetch_raw.py                 # 增量下载
  python scripts/fetch_raw.py --workers 2     # 并发（默认 1，稳一点）
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

UA = {"User-Agent": "FinanSI research buffett-mind/0.1 (contact: research@finansi.local)"}
CIK = 1067983
SUBS = "https://data.sec.gov/submissions/"
ARCH = "https://www.sec.gov/Archives/edgar/data"
DATA = Path(__file__).resolve().parent.parent / "data"


def get(url: str, timeout: int = 20):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r.content
            if r.status_code in (403, 404):
                return None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1 + attempt)
    return None


def all_filings() -> list[dict]:
    out: list[dict] = []
    base = get(f"{SUBS}CIK{CIK:010d}.json")
    if not base:
        raise SystemExit("✗ 取不到 submissions")
    pages = [json.loads(base)["filings"]["recent"]]
    for f in json.loads(base)["filings"].get("files", []):
        p = get(f"{SUBS}{f['name']}")
        if p:
            pages.append(json.loads(p))

    for page in pages:
        for i, form in enumerate(page["form"]):
            if form.startswith("13F-HR"):
                out.append({
                    "form": form,
                    "accession": page["accessionNumber"][i],
                    "filed": page["filingDate"][i],
                    "period": page["reportDate"][i],
                })
    out.sort(key=lambda x: (x["period"], x["filed"]))
    return out


def fetch_one(f: dict, root: Path) -> str:
    acc = f["accession"]
    d = root / acc
    if (d / "index.json").exists():
        return f"{acc} 已缓存"
    d.mkdir(parents=True, exist_ok=True)
    a = acc.replace("-", "")
    idx = get(f"{ARCH}/{CIK}/{a}/index.json")
    if not idx:
        return f"{acc} index 失败"
    (d / "index.json").write_bytes(idx)
    items = json.loads(idx).get("directory", {}).get("item", [])

    saved = 0
    for it in items:
        name = it["name"]
        low = name.lower()
        if "index" in low:
            continue
        if not low.endswith((".xml", ".txt", ".htm", ".html")):
            continue
        # 只下可能是信息表 / 正文的文件，跳过附件图片等
        body = get(f"{ARCH}/{CIK}/{a}/{name}")
        if body:
            (d / name).write_bytes(body)
            saved += 1
    return f"{acc} 下载 {saved} 个文件"


def main() -> int:
    ap = argparse.ArgumentParser(description="缓存 13F 原始文件")
    ap.add_argument("--out", default=str(DATA / "raw"))
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)

    fl = all_filings()
    (root / "manifest.json").write_text(json.dumps(fl, ensure_ascii=False, indent=2), encoding="utf-8")
    todo = [f for f in fl if not (root / f["accession"] / "index.json").exists()]
    print(f"申报 {len(fl)} 份｜待下载 {len(todo)} 份｜并发 {args.workers}")

    done = 0
    if args.workers <= 1:
        for f in todo:
            print("  " + fetch_one(f, root))
            done += 1
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for msg in ex.map(lambda f: fetch_one(f, root), todo):
                done += 1
                print(f"  [{done}/{len(todo)}] {msg}")

    print(f"\n完成：缓存目录 {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
