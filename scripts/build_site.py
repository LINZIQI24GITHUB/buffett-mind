#!/usr/bin/env python3
"""生成 GitHub Pages 静态站（单页，品牌风格）。

读 examples/ 与 assets/，输出 docs/index.html + docs/assets/*。
不依赖前端构建，纯 HTML + 内联 CSS。

用法：
  python scripts/build_site.py
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DB = ROOT / "corpus" / "index.sqlite"

PAPER, INK, MUTED, LIME = "#f4f1e9", "#121313", "#666962", "#f4ff71"


def stats() -> dict[str, int]:
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    letters = con.execute("SELECT COUNT(*) FROM docs WHERE kind='letter'").fetchone()[0]
    video = con.execute("SELECT COUNT(*) FROM docs WHERE kind='video'").fetchone()[0]
    con.close()
    return {"docs": n, "letters": letters, "video": video}


def answer_blocks() -> str:
    import html

    out = []
    for name, title in (("voice-ashare2024.txt", "2024 年 9 月 24 日，A 股买什么"),
                        ("voice-apple.txt", "苹果还值得长期持有吗")):
        p = ROOT / "examples" / name
        if not p.exists():
            continue
        paras = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        body = "\n".join(f"<p>{html.escape(x)}</p>" for x in paras if not x.startswith("推演"))
        out.append(f'<article class="card"><h3>{html.escape(title)}</h3>{body}</article>')
    return "\n".join(out)


def main() -> int:
    s = stats()
    DOCS.mkdir(exist_ok=True)
    (DOCS / "assets").mkdir(exist_ok=True)
    for img in (ROOT / "assets").glob("*.png"):
        shutil.copy2(img, DOCS / "assets" / img.name)

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Buffett Mind · 可验证的巴菲特语料与决策框架</title>
<style>
  :root {{ --paper:{PAPER}; --ink:{INK}; --muted:{MUTED}; --lime:{LIME}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font-family:"PingFang SC","Microsoft YaHei",system-ui,-apple-system,sans-serif;
         line-height:1.75; }}
  .wrap {{ max-width:860px; margin:0 auto; padding:0 24px 96px; }}
  .bar {{ height:10px; background:var(--lime); }}
  header {{ padding:56px 0 8px; }}
  .kicker {{ font-size:13px; letter-spacing:.18em; color:var(--muted); text-transform:uppercase; }}
  h1 {{ font-size:44px; line-height:1.2; margin:12px 0 8px; letter-spacing:-.02em; }}
  .sub {{ color:var(--muted); font-size:18px; margin:0 0 28px; }}
  .links a {{ display:inline-block; margin:0 12px 12px 0; padding:10px 18px; border:1px solid var(--ink);
             color:var(--ink); text-decoration:none; font-size:14px; }}
  .links a.primary {{ background:var(--ink); color:var(--paper); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:16px; margin:40px 0; }}
  .stat {{ border-top:2px solid var(--ink); padding-top:12px; }}
  .stat b {{ display:block; font-size:34px; line-height:1.1; }}
  .stat span {{ color:var(--muted); font-size:13px; }}
  h2 {{ font-size:15px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted);
        margin:56px 0 16px; }}
  .card {{ background:#fffef9; border:1px solid #e2ddcf; padding:22px 24px; margin:0 0 16px; }}
  .card h3 {{ margin:0 0 10px; font-size:16px; }}
  .card p {{ margin:0 0 10px; font-size:15px; }}
  figure {{ margin:0 0 20px; }}
  figure img {{ width:100%; border:1px solid #e2ddcf; }}
  figcaption {{ color:var(--muted); font-size:13px; margin-top:6px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  td,th {{ text-align:left; padding:8px 10px; border-bottom:1px solid #e2ddcf; }}
  pre {{ background:#121313; color:#d8d4c8; padding:16px 18px; overflow:auto; font-size:13px;
         line-height:1.6; }}
  footer {{ margin-top:64px; padding-top:20px; border-top:1px solid #e2ddcf; color:var(--muted);
            font-size:13px; }}
</style>
</head>
<body>
<div class="bar"></div>
<div class="wrap">
<header>
  <div class="kicker">Buffett Mind</div>
  <h1>用他的原话和仓位，<br>反推他的框架。</h1>
  <p class="sub">每一句都能查，每一个仓位都能对。疑问处一律标注「推演」。</p>
  <div class="links">
    <a class="primary" href="https://github.com/LINZIQI24GITHUB/buffett-mind">GitHub 仓库</a>
    <a href="https://github.com/LINZIQI24GITHUB/buffett-mind/actions">CI 状态</a>
    <a href="#demo">看示例</a>
  </div>
</header>

<div class="grid">
  <div class="stat"><b>{s['letters']}</b><span>封股东信（1977–2024）</span></div>
  <div class="stat"><b>111</b><span>个季度的 13F</span></div>
  <div class="stat"><b>14,060</b><span>行持仓记录</span></div>
  <div class="stat"><b>133</b><span>组言行对账</span></div>
</div>

<h2 id="demo">它怎么回答</h2>
{answer_blocks()}

<figure>
  <img src="assets/answer-demo.png" alt="第一人称回答示例">
  <figcaption>第一人称叙述，数字全部可核对，结尾固定标注推演与免责。</figcaption>
</figure>

<figure>
  <img src="assets/nav-curve.png" alt="组合净值曲线">
  <figcaption>按季度规则管理的四只 A 股组合：累计 +25.8%，同期沪深300ETF +28.6%。</figcaption>
</figure>

<h2>为什么不一样</h2>
<table>
  <tr><th></th><th>纯提示词包</th><th>信件合集</th><th>本项目</th></tr>
  <tr><td>股东信全文 + 检索</td><td>摘录</td><td>✅</td><td>✅</td></tr>
  <tr><td>13F 全历史</td><td>❌</td><td>❌</td><td>✅ 111 季度</td></tr>
  <tr><td>建仓成本（VWAP、拆股）</td><td>❌</td><td>❌</td><td>✅</td></tr>
  <tr><td>引语校验（拒绝假引语）</td><td>❌</td><td>❌</td><td>✅</td></tr>
  <tr><td>言行对账</td><td>❌</td><td>❌</td><td>✅ 133 组</td></tr>
  <tr><td>语气量化与自检</td><td>❌</td><td>❌</td><td>✅ 18,568 句</td></tr>
  <tr><td>A 股适配</td><td>❌</td><td>❌</td><td>✅</td></tr>
</table>

<figure>
  <img src="assets/demo-output.png" alt="离线自检输出">
  <figcaption>clone 下来直接跑：六项自检全过，CI 每次提交都跑一遍。</figcaption>
</figure>

<h2>三条硬规则</h2>
<pre>1. 原话必须校验：quote.py --verify，不过的一律不得作为依据
2. 市值变化必须分解：跌了不等于减仓
3. 推演必须标注：他没表过态，就直接说没表过态</pre>

<footer>
  AI 推演，非巴菲特本人观点，不构成投资建议。<br>
  数据来源：Berkshire 股东信、SEC EDGAR 13F、公开行情。
</footer>
</div>
</body>
</html>"""
    (DOCS / "index.html").write_text(html_text, encoding="utf-8")
    print(f"生成 {DOCS / 'index.html'}（{len(html_text)} 字符）")
    print(f"统计：{s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
