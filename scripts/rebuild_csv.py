#!/usr/bin/env python3
"""从本地缓存的 data/holdings/*/*.json 重建 holdings.csv（不联网）。

用处：解析器改进后，只要重新抓那几份有问题的申报，其余季度沿用已解析结果，
      再跑本脚本合并成 CSV。避免每次改动都全量重下 211 份申报。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FIELDS = ["period", "filed", "accession", "form", "amend", "cusip", "issuer", "title",
          "value", "shares", "share_type", "put_call"]


def main() -> int:
    root = DATA / "holdings"
    rows: list[dict] = []
    kinds_path = DATA / "amend-kinds.json"
    kinds = json.loads(kinds_path.read_text(encoding="utf-8")) if kinds_path.exists() else {}

    for f in sorted(root.glob("*/*.json")):
        for r in json.loads(f.read_text(encoding="utf-8")):
            r.setdefault("amend", "original")
            r["amend"] = r["amend"] or kinds.get(r["accession"], "original")
            rows.append({k: r.get(k, "") for k in FIELDS})

    with (DATA / "holdings.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    periods = sorted({r["period"] for r in rows})
    print(f"合并 {len(rows)} 行｜{len(periods)} 个季度｜{periods[0]} ~ {periods[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
