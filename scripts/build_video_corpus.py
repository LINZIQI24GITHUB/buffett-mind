#!/usr/bin/env python3
"""把转写好的 JSONL 合并成段落，写进语料索引（kind='video'）。

为什么要合并：Whisper 每段只有几秒，直接入库会让检索命中一堆碎片。
按 ~700 字符合并成一段，带上起止时间，检索时返回「视频链接 + 秒数」可直跳。

用法：
  python scripts/build_video_corpus.py \
      --segments data/video/2024-meeting.jsonl \
      --title "2024 伯克希尔股东大会" --url "https://youtu.be/xxx" --year 2024
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "corpus" / "index.sqlite"
CHUNK_CHARS = 700


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def chunk(segs: list[dict], size: int = CHUNK_CHARS) -> list[dict]:
    """合并成 ~size 字符的段落；说话人（Q/A）变化时强制断开，避免问答混在一段。"""
    out, buf, start, end = [], [], None, None
    speaker = None
    for s in segs:
        spk = s.get("speaker", "A")
        if start is None:
            start, speaker = s["start"], spk
        if spk != speaker and sum(len(x) for x in buf) >= 200:
            out.append({"start": start, "end": end, "text": " ".join(buf), "speaker": speaker})
            buf, start, speaker = [], s["start"], spk
        buf.append(s["text"])
        end = s["end"]
        if sum(len(x) for x in buf) >= size:
            out.append({"start": start, "end": end, "text": " ".join(buf), "speaker": speaker})
            buf, start, speaker = [], None, None
    if buf and start is not None:
        out.append({"start": start, "end": end, "text": " ".join(buf), "speaker": speaker})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--db", default=str(DB))
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print("✗ 索引不存在，先跑 build_corpus.py")
        return 2

    segs = load(Path(args.segments))
    chunks = chunk(segs)
    rows = []
    for c in chunks:
        text = re.sub(r"\s+", " ", c["text"]).strip()
        if len(text) < 80:
            continue
        t = int(c["start"])
        tag = "提问" if c.get("speaker") == "Q" else "回答"
        rows.append((args.year, f"{args.title} {t//60:02d}:{t%60:02d}",
                     f"{args.url}?t={t}", f"[{tag}] {text}"))

    con = sqlite3.connect(db)
    before = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    con.executemany("INSERT INTO docs (kind, year, source, url, text) VALUES ('video',?,?,?,?)", rows)
    con.execute("INSERT INTO docs_fts (docs_fts) VALUES ('rebuild')")
    con.commit()
    after = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    vids = con.execute("SELECT COUNT(*) FROM docs WHERE kind='video'").fetchone()[0]
    con.close()

    print(f"段落 {len(rows)}｜文档 {before} → {after}（视频类共 {vids}）")
    print(f"例：{rows[0][1]} → {rows[0][2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
