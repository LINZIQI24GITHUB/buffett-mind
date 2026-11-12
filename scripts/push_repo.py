import base64
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\buffett-pack\skills\buffett-mind")
SNAP = ROOT / "dist" / "snapshot"
REPO = "LINZIQI24GITHUB/buffett-mind"
API = f"https://api.github.com/repos/{REPO}"


def token() -> str:
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [l.split("=", 1)[1] for l in out.splitlines() if l.startswith("password=")][0]


H = {"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json",
     "User-Agent": "dsh"}

files: dict[str, Path] = {}
for name in ("README.md", "README_EN.md", "CONTRIBUTING.md", "CITATION.cff", "SKILL.md",
             "LICENSE", "requirements.txt", ".gitignore"):
    p = ROOT / name
    if p.exists():
        files[name] = p
for p in (ROOT / "assets").glob("*.png"):
    files[f"assets/{p.name}"] = p
for p in (ROOT / "references").glob("*.md"):
    files[f"references/{p.name}"] = p
for p in (ROOT / "examples").glob("*.txt"):
    files[f"examples/{p.name}"] = p
for p in (ROOT / "scripts").glob("*.py"):
    files[f"scripts/{p.name}"] = p

# 浠撳簱鍐呯殑鏁版嵁蹇収
if SNAP.exists():
    files["NOTICE.md"] = SNAP / "NOTICE.md"
    files["corpus/index.sqlite"] = SNAP / "corpus" / "index.sqlite"
    for name in ("holdings.csv", "vwap.csv", "splits.csv", "cusip-map.json"):
        files[f"data/{name}"] = SNAP / "data" / name
    for p in (SNAP / "data" / "prices").glob("*.csv"):
        files[f"data/prices/{p.name}"] = p

print(f"寰呮帹閫?{len(files)} 涓枃浠讹紝"
      f"{sum(p.stat().st_size for p in files.values())/1e6:.1f} MB")

ref = requests.get(f"{API}/git/ref/heads/main", headers=H, timeout=20).json()
sha = ref["object"]["sha"]
tree = requests.get(f"{API}/git/commits/{sha}", headers=H, timeout=20).json()["tree"]["sha"]

entries = []
for i, (path, p) in enumerate(sorted(files.items()), 1):
    data = p.read_bytes()
    r = requests.post(f"{API}/git/blobs", headers=H, timeout=120,
                      json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
    r.raise_for_status()
    entries.append({"path": path, "mode": "100644", "type": "blob", "sha": r.json()["sha"]})
    if i % 15 == 0:
        print(f"  {i}/{len(files)}")
print(f"blob 瀹屾垚 {len(entries)}")

new_tree = requests.post(f"{API}/git/trees", headers=H, timeout=120,
                         json={"base_tree": tree, "tree": entries}).json()["sha"]
msg = """Package for discovery: badges, screenshots, English README, runnable data snapshot

- ship a 7 MB snapshot (48 letters + 111 quarters of 13F + price window): clone and `demo.py` passes 6/6
- add English README, CONTRIBUTING, CITATION
- add three screenshots (first-person answer, offline self-check, NAV curve)
- demo.py: snapshot-aware (letters-only index, FAQ citations counted as secondary)
- add make_snapshot.py / make_assets.py, video transcription and number-validation scripts"""
commit = requests.post(f"{API}/git/commits", headers=H, timeout=60,
                       json={"message": msg, "tree": new_tree, "parents": [sha]}).json()
upd = requests.patch(f"{API}/git/refs/heads/main", headers=H, timeout=60,
                     json={"sha": commit["sha"]})
upd.raise_for_status()
print("pushed:", commit["sha"][:12])

topics = ["warren-buffett", "berkshire-hathaway", "value-investing", "13f", "sec-edgar",
          "agent-skills", "claude-code", "ai-agent", "investment-research", "financial-analysis",
          "stock-analysis", "fundamental-analysis", "corpus", "llm", "quantitative-finance",
          "a-share", "china-stock", "portfolio-management", "data-engineering", "python"]
tr = requests.put(f"{API}/topics", headers=H, timeout=30, json={"names": topics})
print("topics:", tr.status_code, tr.json().get("names") if tr.ok else tr.text[:100])

