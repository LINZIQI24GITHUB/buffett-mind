#!/usr/bin/env python3
"""生成可以放进 Git 仓库的数据快照（体积小、clone 即可跑 demo）。

包含：
  corpus/index.sqlite     只保留股东信（48 篇）——第三方汇编的 FAQ 不进仓库
  data/holdings.csv       13F 全历史（111 季度）
  data/vwap.csv           建仓均价
  data/splits.csv         拆股
  data/cusip-map.json     CUSIP → ticker
  data/prices/            只保留 2019-06 ~ 2020-06 的收盘价（够 demo 的分解用例）

不包含：FAQ 语料、全量价格（48MB）、视频转写。

用法：
  python scripts/make_snapshot.py --out dist/snapshot
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def build_sqlite(dst: Path) -> tuple[int, int]:
    src = ROOT / "corpus" / "index.sqlite"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    con = sqlite3.connect(dst)
    con.execute("DELETE FROM docs WHERE kind != 'letter'")
    con.execute("INSERT INTO docs_fts (docs_fts) VALUES ('rebuild')")
    con.commit()
    con.execute("VACUUM")
    n = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    con.close()
    return n, dst.stat().st_size


def trim_prices(dst_dir: Path) -> tuple[int, float]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    wanted = {"2019-12-31", "2020-03-31"}
    cmap = json.loads((DATA / "cusip-map.json").read_text(encoding="utf-8"))
    tickers: set[str] = set()
    for row in csv.DictReader((DATA / "holdings.csv").open(encoding="utf-8")):
        if row["period"] not in wanted:
            continue
        info = cmap.get(row["cusip"]) or {}
        t = (info.get("ticker") or "").replace("/", "-")
        if t:
            tickers.add(t)
    total = 0.0
    n = 0
    for t in sorted(tickers):
        src = DATA / "prices" / f"{t}.csv"
        if not src.exists():
            continue
        rows = [r for r in csv.DictReader(src.open(encoding="utf-8"))
                if "2019-06-01" <= r["date"] <= "2020-06-30"]
        if not rows:
            continue
        out = dst_dir / f"{t}.csv"
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        total += out.stat().st_size
        n += 1
    return n, total / 1e6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/snapshot")
    args = ap.parse_args()
    out = Path(args.out)

    n, size = build_sqlite(out / "corpus" / "index.sqlite")
    print(f"索引：{n} 篇股东信｜{size/1e6:.2f} MB")

    (out / "data").mkdir(parents=True, exist_ok=True)
    for name in ("holdings.csv", "vwap.csv", "splits.csv", "cusip-map.json"):
        shutil.copy2(DATA / name, out / "data" / name)
    nt, sz = trim_prices(out / "data" / "prices")
    print(f"价格：{nt} 只｜{sz:.2f} MB")

    notice = """数据来源与许可

- 股东信：berkshirehathaway.com 公开 PDF，仅用于研究与检索
- 13F 持仓：SEC EDGAR 公开申报，按季度解析
- 价格：公开行情数据，仅保留 demo 所需的时间窗
- 第三方汇编（buffettfaq.com）的问答不在本仓库内，见 Release 附件

本项目不构成投资建议。引用请注明来源。
"""
    (out / "NOTICE.md").write_text(notice, encoding="utf-8")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"快照总计：{total:.2f} MB → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
