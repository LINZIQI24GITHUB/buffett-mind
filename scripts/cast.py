#!/usr/bin/env python3
"""把一段中文口播稿做成竖屏短视频：配音 + 封面 + mp4。

自用原型，不追求音色克隆。TTS 走 Windows 内置语音（零依赖、离线），
后续可换成 Kokoro / GPT-SoVITS / ElevenLabs —— 只要替换 `synthesize()`。

用法：
  python cast.py --script script.txt --title "黄金值不值得买" --out out/gold
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAPER = "#f4f1e9"
INK = "#121313"
MUTED = "#666962"
LIME = "#f4ff71"
FONT_CANDIDATES = [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
                   r"C:\Windows\Fonts\simhei.ttf"]


def find_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def make_cover(path: Path, title: str, subtitle: str) -> None:
    W, H = 1080, 1920
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    # 顶部 lime 条
    d.rectangle([0, 0, W, 14], fill=LIME)
    # 页眉
    d.text((80, 90), "BUFFETT MIND", font=find_font(34), fill=MUTED)
    d.text((W - 80, 90), "AI 演绎", font=find_font(34), fill=MUTED, anchor="ra")
    # 主标题（自动换行）
    f_title = find_font(96)
    y = 620
    for line in textwrap.wrap(title, width=8):
        d.text((80, y), line, font=f_title, fill=INK)
        y += 130
    # 副标题
    f_sub = find_font(44)
    y += 30
    for line in textwrap.wrap(subtitle, width=16):
        d.text((80, y), line, font=f_sub, fill=MUTED)
        y += 66
    # 底部声明
    f_foot = find_font(36)
    d.text((80, H - 170), "AI 生成 · 非巴菲特本人观点", font=f_foot, fill=MUTED)
    d.text((80, H - 120), "不构成投资建议", font=f_foot, fill=MUTED)
    img.save(path)


def synthesize_edge(text: str, wav: Path, voice: str = "zh-CN-YunyangNeural",
                    rate: str = "-10%") -> None:
    """edge-tts：微软在线神经语音，免费无需 key，中文男声质量接近播音员。

    换 TTS 只需替换本函数；GPT-SoVITS 接进来时在这里改成 HTTP POST 到
    127.0.0.1:9880/tts 即可。
    """
    mp3 = wav.with_suffix(".mp3")
    subprocess.run(["edge-tts", "--voice", voice, f"--rate={rate}",
                    "--text", text, "--write-media", str(mp3)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                    "-ar", "44100", "-ac", "1", str(wav)], check=True)
    mp3.unlink(missing_ok=True)


def synthesize(text: str, wav: Path) -> None:
    """Windows SAPI 合成（离线、零依赖）。换 TTS 只改这个函数。"""
    plain = text.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -2; $s.Volume = 100; "
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'zh*' } "
        "| Select-Object -First 1; if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
        f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{plain}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def make_video(cover: Path, wav: Path, mp4: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(cover),
        "-i", str(wav),
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-vf", "scale=1080:1920", "-shortest", str(mp4),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="口播稿 txt")
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tts", default="edge", choices=["edge", "sapi"])
    ap.add_argument("--voice", default="zh-CN-YunyangNeural")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = Path(args.script).read_text(encoding="utf-8").strip()
    if not text:
        print("✗ 稿子为空")
        return 2

    wav = out.with_suffix(".wav")
    cover = out.parent / f"{out.name}-cover.png"
    mp4 = out.with_suffix(".mp4")

    make_cover(cover, args.title, args.subtitle or text[:40])
    print(f"封面 → {cover}")
    if args.tts == "edge":
        synthesize_edge(text, wav, args.voice)
    else:
        synthesize(text, wav)
    print(f"配音 → {wav}（{wav.stat().st_size/1024:.0f} KB）")
    make_video(cover, wav, mp4)
    print(f"视频 → {mp4}（{mp4.stat().st_size/1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
