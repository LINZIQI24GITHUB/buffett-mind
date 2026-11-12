# Buffett Mind

Reconstruct Warren Buffett's decision framework from **what he actually said** and **what Berkshire
actually held** — then answer investment questions with evidence, not quotes.

Most "Buffett skills" give you a methodology. This one gives you a **verifiable data layer** — and the
part nobody else has: **15 years of annual-meeting video, transcribed and speaker-separated.**

- **2011–2025 annual meetings**: 6,769 transcript segments, 5,280 of them Buffett, 103 Munger,
  1,385 audience questions — each with a `?t=` timestamp back to the video
- **48 shareholder letters** (1977–2024) with full-text search
- **111 quarters of 13F filings** (1998Q4–2026Q2), 14,060 positions, VWAP cost basis, split-adjusted
- **Quote verification**: every citation is checked against the corpus; fabricated quotes are rejected
- **Reconciliation**: 133 evidence pairs comparing what he said with what he did
- **Behaviour statistics**: core positions (top weight quintile) are held 28 quarters and return +114%;
  the smallest quintile is held 2 quarters for +9%
- **Tone model**: 11 style rules derived from 18,568 sentences of his own letters

![First-person answer](assets/answer-demo.png)

## Why video matters

Berkshire stopped publishing annual-meeting transcripts after 2010. Everything since exists only as
video. Transcribing it gives you three things letters cannot:

1. **Unedited answers** — how he thinks on the spot, not how he later wrote it
2. **Time alignment with 13F** — what he said and what he bought in the same quarter
3. **Deep links** — every quote jumps back to the exact second in the source video

```bash
$ python scripts/quote.py "gravity" --limit 3
[问 1753] 2013 · 2013 伯克希尔股东大会 67:27
    …interest rates are to asset prices, sort of like 【gravity】 is to the apple…
    https://www.youtube.com/watch?v=b1-QzoQmprM?t=4047
[问 5601] 2021 · 2021 伯克希尔股东大会 86:17
    …interest rates basically are to the value of assets, what 【gravity】 is to matter…
```

Machine transcription: expect occasional wrong words; check the timestamp before quoting. Munger is
labelled only where confident (~100 segments); the rest defaults to Buffett.

## Quick start

```bash
pip install -r requirements.txt
python scripts/demo.py          # 6 offline checks, no network
python scripts/quote.py --verify "price is what you pay, value is what you get"
python scripts/valuation.py --code 600519 --growth 6 --two-stage
```

## What it can answer

| Question | Command |
|---|---|
| What did he say about gold / banks / airlines / Apple? | `quote.py` / `answer.py` |
| What does "understandable" or "stable business" mean in his words? | `references/understand.md`, `stable-business.md` |
| How does he judge growth rates? | `references/growth.md` |
| When did he buy, how much, what happened after? | `timeline.py` / `holdings.py` |
| He says he holds forever — how long does he actually hold? | `returns.py` / `behavior.py` |
| Market value fell 27% — price or selling? | `decompose.py` |
| Is he consistent between words and actions? | `reconcile.py` |
| What is this business worth at his 10% discount rate? | `valuation.py` |
| What did he buy in this kind of business? | `judge_cases.py` (74 decision cases) |

## Why this is different

| | Prompt-only packs | Letter collections | **This repo** |
|---|---|---|---|
| Source letters | excerpts | ✅ full text | ✅ full text + FTS |
| **2011–2025 meeting video, speaker-split** | ❌ | ❌ | ✅ **15 meetings / 6,769 segments** |
| 13F holdings history | ❌ | ❌ | ✅ 111 quarters |
| Cost basis (VWAP, splits) | ❌ | ❌ | ✅ |
| Quote verification | ❌ | ❌ | ✅ rejects fakes |
| Words-vs-actions reconciliation | ❌ | ❌ | ✅ 133 pairs |
| Core-vs-edge behaviour statistics | ❌ | ❌ | ✅ |
| Parameter provenance audit (CI gate) | ❌ | ❌ | ✅ |
| Quantified tone model | ❌ | ❌ | ✅ 18,568 sentences |
| A-share adaptation | ❌ | ❌ | ✅ |
| Runnable offline demo | ❌ | ❌ | ✅ 6/6 checks |

## Three hard rules

1. **Every quote must verify** — `quote.py --verify` or it cannot be used
2. **Market-value changes must be decomposed** — a drop is not a sale
3. **Inference must be labelled** — if he never spoke on it, say so

Rule 1 is not pedantry: the two most-quoted Buffett lines in Chinese — "if you wouldn't hold it ten
years, don't hold it ten minutes" and "be fearful when others are greedy" — are both real (1996 and
1986 letters). Yet his median holding period across 154 decisions is **2.3 years**.

## Valuation with his discount rate

`valuation.py` uses a 10% discount rate — his own example in the 1991 letter (doc 15), and he said in
2003 he would not lower the bar just because Treasury yields were low (doc 159). Growth is a
two-stage input: three years at your estimate, then 3% perpetual. The safety margin is a parameter,
printed in `--help`, not hidden in code.

## Data

The repo ships a compact, runnable snapshot (letters index + holdings + a small price window).
Full price history, the third-party Q&A compilation, and the meeting transcripts live in the release
asset, not in Git.

## Disclaimer

Inference outputs are AI reconstructions, not Buffett's words, and not investment advice.
