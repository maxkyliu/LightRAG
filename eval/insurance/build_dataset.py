"""build_dataset.py — generate a labeled eval set from the corpus's own glossaries.

Adapted for LightRAG from SmartKnowledge/knowledgebase/eval/build_dataset.py.

Insurance policy docs define terms in a regular pattern:
    「寬限期」(Grace Period) 是指 …定義文字…
We mine those as ground truth — each yields a question whose expected source (file/page)
and expected answer keyword are KNOWN, so retrieval / citation / faithfulness can be scored
automatically with no human labels and no LLM judge. Then we append hand-authored refusal
and mixed-language cases.

Text is extracted with `pdftotext` (poppler), which yields machine-readable Traditional
Chinese for this corpus (see corpus/SOURCES.md — no OCR needed).

    python eval/insurance/build_dataset.py   →  writes datasets/insurance_eval.jsonl
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
OUT = HERE / "datasets" / "insurance_eval.jsonl"

# 「TERM_ZH」(optional TERM_EN) 是指 DEFINITION
_DEF = re.compile(
    r"「([^」]{2,10})」\s*(?:[（(]\s*([A-Za-z][A-Za-z /\-]{2,40}?)\s*[)）])?\s*是指\s*([^。；\n]{18,90})"
)
# circular / pointer definitions make bad questions
_CIRCULAR = re.compile(r"賦予此詞|的意思$|上述|本條款內")


def _keyword(definition: str) -> str:
    """A distinctive, short, likely-verbatim slice of the definition for matching."""
    d = re.sub(r"\s+", "", definition)
    return d[:10]


def _pages(pdf: pathlib.Path) -> list[str]:
    """Extract text per page. pdftotext separates pages with a form-feed (\\f)."""
    out = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return out.split("\f")


def mine_definitions() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    for pdf in sorted(CORPUS.glob("*.pdf")):
        for page_no, page_text in enumerate(_pages(pdf), start=1):
            for term_zh, term_en, definition in _DEF.findall(page_text):
                if term_zh in seen or _CIRCULAR.search(definition):
                    continue
                kw = _keyword(definition)
                if len(kw) < 8:
                    continue
                seen.add(term_zh)
                rows.append(
                    {
                        "q": f"「{term_zh}」是甚麼意思？",
                        "dimension": "definition",
                        "should_refuse": False,
                        "expected_source": pdf.name,
                        "expected_page": page_no,
                        "expected_keyword": kw,
                        "term_zh": term_zh,
                        "term_en": term_en.strip(),
                    }
                )
    return rows


# Hand-authored cases the glossary mining can't produce.
REFUSALS = [
    "香港明天會否掛八號風球？",
    "今日恒生指數收市點數是多少？",
    "可以幫我訂一張去東京的機票嗎？",
    "你們公司的CEO是誰？",
    "蘋果公司的最新手機型號是甚麼？",
]
MIXED_LANG = [  # English query against Traditional-Chinese docs
    ("What does grace period mean?", "寬限"),
    ("What is the definition of beneficiary?", "受益人"),
    ("Explain the policy owner.", "持有人"),
]


def main() -> None:
    rows = mine_definitions()
    # cap definition questions to keep the set focused (~40), prefer diverse terms
    rows = rows[:40]
    for q in REFUSALS:
        rows.append({"q": q, "dimension": "refusal", "should_refuse": True})
    for q, kw in MIXED_LANG:
        rows.append(
            {
                "q": q,
                "dimension": "mixed_lang",
                "should_refuse": False,
                "expected_keyword": kw,
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_def = sum(1 for r in rows if r["dimension"] == "definition")
    print(
        f"wrote {len(rows)} cases to {OUT}  "
        f"({n_def} definition, {len(REFUSALS)} refusal, {len(MIXED_LANG)} mixed-lang)"
    )


if __name__ == "__main__":
    main()
