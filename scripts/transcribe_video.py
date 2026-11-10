#!/usr/bin/env python3
"""把一场视频/音频转写成带时间戳的 JSONL，供语料索引使用。

流程：yt-dlp 下音频 → ffmpeg 转 16k 单声道 → faster-whisper 转写 → JSONL。

为什么用 faster-whisper：本地 CPU 可跑，实测 5.3 倍实时（small + int8 + VAD），
零 API 成本。转写结果只落盘，不进对话上下文。

用法（必须用装了 faster-whisper 的 venv 跑）：
  .venv-whisper\\Scripts\\python.exe scripts/transcribe_video.py \
      --url "https://www.youtube.com/watch?v=..." --out data/video/2024-meeting.jsonl

  --audio 可以跳过下载，直接用本地文件。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / ".cache" / "hf"))

from faster_whisper import WhisperModel  # noqa: E402


def download(url: str, work: Path) -> Path:
    audio = work / "audio.webm"
    if not audio.exists():
        subprocess.run(["yt-dlp", "--no-warnings", "-f", "bestaudio",
                        "-o", str(audio), url], check=True)
    wav = work / "audio.wav"
    if not wav.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio),
                        "-ar", "16000", "-ac", "1", str(wav)], check=True)
    return wav


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--threads", type=int, default=12)
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="asr-"))

    if args.audio:
        wav = Path(args.audio)
    else:
        if not args.url:
            print("✗ 需要 --url 或 --audio")
            return 2
        wav = download(args.url, work)
    print(f"音频: {wav}（{wav.stat().st_size/1e6:.0f} MB）", flush=True)

    # 模型只认本地目录：走 HF 的 snapshot_download 会联网解析版本，在这台机器上会卡住
    target = args.model
    if not Path(target).is_dir():
        local = Path(__file__).resolve().parents[3] / ".models" / f"whisper-{args.model}"
        if local.is_dir():
            target = str(local)

    t0 = time.time()
    model = WhisperModel(target, device="cpu", compute_type="int8",
                         cpu_threads=args.threads)
    print(f"模型加载: {time.time()-t0:.0f}s", flush=True)

    t1 = time.time()
    segments, info = model.transcribe(str(wav), language="en", vad_filter=True,
                                      beam_size=1, condition_on_previous_text=False)
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for seg in segments:
            fh.write(json.dumps({"start": round(seg.start, 2), "end": round(seg.end, 2),
                                 "text": seg.text.strip()}, ensure_ascii=False) + "\n")
            n += 1
            if n % 200 == 0:
                el = time.time() - t1
                print(f"  {n} 段｜{seg.end/60:.0f} 分钟音频｜耗时 {el/60:.1f} 分钟"
                      f"｜{seg.end/el:.1f}x", flush=True)
    dt = time.time() - t1
    print(f"完成：{n} 段｜音频 {info.duration/60:.0f} 分钟｜耗时 {dt/60:.1f} 分钟"
          f"｜{info.duration/dt:.1f}x｜输出 {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
