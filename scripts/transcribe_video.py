#!/usr/bin/env python3
"""把一场视频/音频转写成带时间戳的 JSONL，供语料索引使用。

流程：yt-dlp 下音频 → ffmpeg 转 16k 单声道 → 按块切分 → faster-whisper 转写 → JSONL。

为什么要切块：faster-whisper 对小文件一次算完没问题，但 5 小时以上的长音频
会在特征提取阶段申请 5–6 GB 数组，机器内存紧张时直接 MemoryError。
按 30 分钟切块后，单块峰值约 300 MB，且时间戳可以按块偏移拼回原始时间轴。

用法（必须用装了 faster-whisper 的 venv 跑）：
  .venv-whisper\\Scripts\\python.exe scripts/transcribe_video.py \
      --url "https://www.youtube.com/watch?v=..." --out data/video/2024-meeting.jsonl

  --audio  跳过下载，直接用本地文件
  --chunk-min  切块长度（分钟），默认 30
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
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


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def split_wav(wav: Path, work: Path, chunk_min: int) -> list[tuple[Path, float]]:
    """按固定时长切块，返回 [(分块路径, 起始秒)]。"""
    dur = audio_duration(wav)
    step = chunk_min * 60
    parts: list[tuple[Path, float]] = []
    t = 0.0
    i = 0
    while t < dur:
        part = work / f"part{i:02d}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-t", str(step),
             "-i", str(wav), "-ar", "16000", "-ac", "1", str(part)],
            check=True)
        parts.append((part, t))
        t += step
        i += 1
    return parts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--chunk-min", type=int, default=30)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--keep", action="store_true", help="保留临时音频")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = Path(args.workdir) if args.workdir else Path(tempfile.gettempdir())
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="asr-", dir=base))

    try:
        return _run(args, work, out)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


def _run(args, work: Path, out: Path) -> int:
    if args.audio:
        wav = Path(args.audio)
    else:
        if not args.url:
            print("✗ 需要 --url 或 --audio")
            return 2
        wav = download(args.url, work)
    print(f"音频: {wav}（{wav.stat().st_size/1e6:.0f} MB）", flush=True)

    target = args.model
    if not Path(target).is_dir():
        candidates = [
            Path(os.environ.get("WHISPER_MODEL_DIR", "D:/dsh-data/models")) / f"whisper-{args.model}",
            Path(__file__).resolve().parents[3] / ".models" / f"whisper-{args.model}",
        ]
        for local in candidates:
            if local.is_dir():
                target = str(local)
                break

    t0 = time.time()
    model = WhisperModel(target, device="cpu", compute_type="int8",
                         cpu_threads=args.threads)
    print(f"模型加载: {time.time()-t0:.0f}s", flush=True)

    dur = audio_duration(wav)
    chunk_sec = args.chunk_min * 60
    if dur > chunk_sec * 1.2:
        parts = split_wav(wav, work, args.chunk_min)
        print(f"切块: {len(parts)} 块 × {args.chunk_min} 分钟", flush=True)
    else:
        parts = [(wav, 0.0)]

    t1 = time.time()
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for part, offset in parts:
            segments, _info = model.transcribe(str(part), language="en", vad_filter=True,
                                               beam_size=1, condition_on_previous_text=False)
            for seg in segments:
                fh.write(json.dumps({"start": round(offset + seg.start, 2),
                                     "end": round(offset + seg.end, 2),
                                     "text": seg.text.strip()}, ensure_ascii=False) + "\n")
                n += 1
                if n % 200 == 0:
                    el = time.time() - t1
                    print(f"  {n} 段｜{(offset + seg.end)/60:.0f} 分钟音频｜耗时 {el/60:.1f} 分钟"
                          f"｜{(offset + seg.end)/el:.1f}x", flush=True)
            part.unlink(missing_ok=True)
    dt = time.time() - t1
    print(f"完成：{n} 段｜音频 {dur/60:.0f} 分钟｜耗时 {dt/60:.1f} 分钟"
          f"｜{dur/dt:.1f}x｜输出 {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
