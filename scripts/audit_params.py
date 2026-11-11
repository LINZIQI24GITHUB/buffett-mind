#!/usr/bin/env python3
"""参数自检：找出「没有出处」的规则和阈值。

检查三件事：
  1. framework.md 的每条规则是否至少有一个 doc 引用；一级（doc≤48，股东信）还是二级（FAQ）
  2. 筛选脚本里是否有硬编码阈值（人工确认是否有出处）
  3. references/parameter-audit.md 是否存在（无出处参数清单）

退出码：0 = 通过；1 = 发现问题。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "references" / "framework.md"
AUDIT = ROOT / "references" / "parameter-audit.md"
SCREEN = ROOT / "scripts"


def check_rules() -> list[str]:
    text = RULES.read_text(encoding="utf-8")
    blocks = re.split(r"^### (R\d+)", text, flags=re.M)
    problems = []
    print("规则引用审计：")
    for i in range(1, len(blocks), 2):
        rid, body = blocks[i], blocks[i + 1]
        docs = sorted({int(x) for x in re.findall(r"doc (\d+)", body)})
        primary = [d for d in docs if d <= 48]
        secondary = [d for d in docs if d > 48]
        status = "OK"
        if not docs:
            status = "无引用（已注明为数据观察才可保留）"
            if "数据观察" not in body:
                problems.append(f"{rid} 无引用")
        elif not primary:
            status = "仅二级材料"
        print(f"  {rid}: {len(docs)} 引用（一级 {len(primary)}、二级 {len(secondary)}）→ {status}")
        if docs and not primary and "仅二级" not in body and "二级材料" not in body:
            problems.append(f"{rid} 只有二级材料，但正文没标注")
    return problems


def scan_thresholds() -> list[str]:
    hits = []
    for f in SCREEN.glob("screen_*.py"):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            if re.search(r"(>=|<=|>|<)\s*0?\.\d+", line) or re.search(r"(>=|<=|>|<)\s*\d{2,}", line):
                hits.append(f"{f.name}:{n}  {line.strip()[:80]}")
    return hits


def main() -> int:
    problems = check_rules()

    print("\n筛选脚本中的硬编码阈值：")
    hits = scan_thresholds()
    for h in hits:
        print("  " + h)

    print("\n无出处参数清单：", "存在" if AUDIT.exists() else "缺失")
    if not AUDIT.exists():
        problems.append("parameter-audit.md 缺失")

    if problems:
        print("\n✗ 发现问题：")
        for p in problems:
            print("  - " + p)
        return 1
    print("\n✓ 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
