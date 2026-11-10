import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\buffett-pack\skills\buffett-mind")
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)
PAPER, INK, MUTED, LIME = "#f4f1e9", "#121313", "#666962", "#f4ff71"


def font(size, bold=False):
    p = r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"
    return ImageFont.truetype(p, size)


def mono(size):
    return ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", size)


def answer_card():
    text = (ROOT / "examples" / "voice-ashare2024.txt").read_text(encoding="utf-8")
    paras = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("推演")]
    wrapped = []
    for para in paras:
        wrapped.extend(textwrap.wrap(para, width=30) + [""])
    W = 1400
    H = 200 + len(wrapped) * 54 + 130
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=LIME)
    d.text((70, 60), "BUFFETT MIND", font=font(28), fill=MUTED)
    d.text((W - 70, 60), "AI reconstruction", font=font(26), fill=MUTED, anchor="ra")
    y = 150
    for line in wrapped:
        d.text((70, y), line, font=font(34), fill=INK)
        y += 54 if line else 24
    d.text((70, H - 100), "推演 · 非巴菲特本人观点 · 不构成投资建议", font=font(24), fill=MUTED)
    img.save(OUT / "answer-demo.png")


def demo_card():
    txt = subprocess.run(["python", "scripts/demo.py"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8").stdout.strip()
    lines = [l.replace("✓", "[ok]").replace("✗", "[x]").replace("·", "-") for l in txt.splitlines()]
    W = 1420
    H = 130 + len(lines) * 40
    img = Image.new("RGB", (W, H), "#121313")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 44], fill="#2a2b28")
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        d.ellipse([18 + i * 26, 15, 32 + i * 26, 29], fill=c)
    y = 70
    for line in lines:
        color = "#9ee493" if "✓" in line else ("#ff8f8f" if "✗" in line else "#d8d4c8")
        d.text((36, y), line, font=mono(21), fill=color)
        y += 36
    img.save(OUT / "demo-output.png")


if __name__ == "__main__":
    answer_card()
    demo_card()
    src = ROOT / "out" / "portfolio-nav.png"
    if src.exists():
        Image.open(src).save(OUT / "nav-curve.png")
    for f in OUT.glob("*.png"):
        print(f.name, f"{f.stat().st_size/1024:.0f} KB")
