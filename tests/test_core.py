"""把 demo.py 的六项自检变成 pytest，方便别人提 PR 时验证。

跑法：
    pytest -q
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import demo  # noqa: E402
import tone_check as TC  # noqa: E402


def test_corpus_index():
    ok, detail = demo.check_corpus()
    assert ok, detail


def test_quote_verification_rejects_fakes():
    ok, detail = demo.check_verify()
    assert ok, detail


def test_timeline_bac_2017q3():
    ok, detail = demo.check_timeline()
    assert ok, detail


def test_decompose_2020q1_is_price_not_selling():
    ok, detail = demo.check_decompose()
    assert ok, detail


def test_framework_citations_exist():
    ok, detail = demo.check_framework()
    assert ok, detail


def test_tone_chinese_sample():
    sample = ROOT / "examples" / "voice-apple.txt"
    checks, passed = TC.check(sample.read_text(encoding="utf-8"))
    assert passed == len(checks), [c for c in checks if not c[1]]


def test_tone_english_sample():
    sample = ROOT / "examples" / "voice-apple-en.txt"
    checks, passed = TC.check_en(sample.read_text(encoding="utf-8"))
    assert passed == len(checks), [c for c in checks if not c[1]]


def test_no_fabricated_quote_in_examples():
    """样例里不允许出现校验不过的引号引语。"""
    import quote as Q

    db = ROOT / "corpus" / "index.sqlite"
    ok, _ = Q.verify(db, "make money while you sleep", None)
    assert not ok, "已知伪引语不应通过校验"
