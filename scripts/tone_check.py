#!/usr/bin/env python3
"""语气自检：把稿子按 references/voice.md 的硬指标打一遍分。

检查项（阈值来自 35 封股东信的统计）：
  1. 平均句长 ≤ 25 字
  2. 40 字以上的长句占比 ≤ 15%
  3. 具体数字 ≥ 3 个
  4. 第一人称「我」出现 ≥ 2 次
  5. 无禁用词（必涨、稳赚、目标价、尊敬的投资、EBITDA…）
  6. 无感叹号
  7. 结尾含免责声明

用法：
  python scripts/tone_check.py --file out/draft.md
  echo "…" | python scripts/tone_check.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BANNED_EN = ["ebitda", "alpha", "synergy", "leverage ratio", "risk-adjusted",
             "target price", "guaranteed", "can't lose", "to the moon"]
BANNED = ["必涨", "稳赚", "目标价", "尊敬的投资者", "各位朋友", "EBITDA", "alpha",
          "因子暴露", "包赚", "翻倍", "梭哈"]
DISCLAIMER_HINTS = ("不构成投资建议", "非巴菲特本人", "AI 生成", "AI 推演")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|亿|万|千|倍|股|年|美元|元)?")


def check_en(text: str) -> tuple[list[tuple[str, bool, str]], int]:
    """英文稿对照他本人信件的统计特征（35 封 / 18,568 句）。"""
    sents = [x for x in re.split(r"(?<=[.!?])\s+", text) if len(x.split()) >= 3]
    lens = [len(x.split()) for x in sents] or [0]
    avg = sum(lens) / len(lens)
    long_ratio = sum(1 for x in lens if x >= 40) / len(lens)
    num_sents = sum(1 for x in sents if re.search(r"\d", x)) / len(sents)
    first_person = sum(1 for x in sents if re.search(r"\b(I|we)\b", x)) / len(sents)
    banned = [w for w in BANNED_EN if w in text.lower()]
    n_tags = len(re.findall(r"\[[^\]]+\]", text))
    checks = [
        ("平均句长 12–25 词", 12 <= avg <= 25, f"{avg:.1f} 词（{len(sents)} 句）"),
        ("长句（≥40 词）≤10%", long_ratio <= 0.10, f"{long_ratio*100:.0f}%"),
        ("带数字的句子 ≥30%", num_sents >= 0.30, f"{num_sents*100:.0f}%"),
        ("第一人称句子 ≥8%", first_person >= 0.08, f"{first_person*100:.0f}%"),
        ("无行话", not banned, ", ".join(banned) or "无"),
        ("含免责声明", any(h in text for h in ("not investment advice", "AI reconstruction", "not my words")), ""),
        ("来源标注 ≥3 处", n_tags >= 3, f"{n_tags} 处"),
    ]
    passed = sum(1 for _, ok, _ in checks if ok)
    return checks, passed


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n]+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 4]


def check(text: str) -> tuple[list[tuple[str, bool, str]], int]:
    sents = split_sentences(text)
    lens = [len(s) for s in sents] or [0]
    avg = sum(lens) / len(lens)
    long_ratio = sum(1 for x in lens if x > 40) / len(lens)
    numbers = NUM_RE.findall(text)
    first_person = text.count("我")
    banned_hits = [w for w in BANNED if w in text]
    exclaims = text.count("！") + text.count("!")
    has_disclaimer = any(h in text for h in DISCLAIMER_HINTS)
    # 来源可以写成方括号标签，也可以写进第一人称句子里（「我 2011 年的信里写过」）
    tags = len(re.findall(r"\[(?:原文|意译|13F|推演)[^\]]*\]", text))
    tags += len(re.findall(r"我[^。；\n]{0,40}(?:信里|写信|申报|财报|年报|算的|写过的|说过)", text))

    checks = [
        ("平均句长 ≤25 字", avg <= 25, f"{avg:.1f} 字（{len(sents)} 句）"),
        ("长句（>40 字）≤15%", long_ratio <= 0.15, f"{long_ratio*100:.0f}%"),
        ("具体数字 ≥3 个", len(numbers) >= 3, f"{len(numbers)} 个"),
        ("第一人称「我」≥2 次", first_person >= 2, f"{first_person} 次"),
        ("无禁用词", not banned_hits, ", ".join(banned_hits) or "无"),
        ("无感叹号", exclaims == 0, f"{exclaims} 个"),
        ("含免责声明", has_disclaimer, "有" if has_disclaimer else "缺"),
        ("来源可追溯 ≥3 处", tags >= 3, f"{tags} 处"),
    ]
    passed = sum(1 for _, ok, _ in checks if ok)
    return checks, passed


def main() -> int:
    ap = argparse.ArgumentParser(description="语气自检")
    ap.add_argument("--file", default=None)
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    args = ap.parse_args()
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not text.strip():
        print("✗ 没有内容")
        return 2
    checks, passed = (check_en(text) if args.lang == "en" else check(text))
    print(f"语气自检（{'英文：对照 35 封股东信统计' if args.lang == 'en' else '中文：对照 references/voice.md'}）")
    for name, ok, detail in checks:
        print(f"  {'✓' if ok else '✗'} {name}：{detail}")
    total = len(checks)
    print(f"\n{'✓ 通过' if passed == total else '✗ 未通过'}（{passed}/{total}）")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
