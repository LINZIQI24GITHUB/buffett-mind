# Contributing

Thanks for looking. Three ways to help:

## 1. Report a wrong quote

Open an issue with the sentence and where you saw it. Every citation in this repo is supposed to be
verifiable against `corpus/`; if one is not, that is a bug, and the most valuable one.

```bash
python scripts/quote.py "<the sentence>" --verify
```

## 2. Fix a data error

13F parsing is the fragile part: amendments, legacy text tables, split adjustments. If a position or
a cost looks wrong, include the accession number and the quarter.

## 3. Add coverage

- More letters (pre-1977, partnership letters)
- Meeting transcripts (`scripts/transcribe_video.py` + `build_video_corpus.py`)
- New A-share mappings in `scripts/ashare_fit.py`

## Ground rules

- Never add a quote that fails `--verify`
- Never ship an inference without the `[推演]` / `[inference]` label
- Numbers must be traceable to a filing or a letter

## Run the checks

```bash
python scripts/demo.py          # must be 6/6
python scripts/tone_check.py --file examples/voice-apple.txt
python scripts/tone_check.py --file examples/voice-apple-en.txt --lang en
```
