"""run_eval.py — the quality gate. RAG fails silently; this catches it.

Adapted for LightRAG from SmartKnowledge/knowledgebase/eval/run_eval.py. Instead of
querying a local qdrant store, it drives the running LightRAG server over HTTP
(POST /query with include_chunk_content=True, which returns the answer plus the
retrieved source references and their chunk text).

Scores the labeled set built by build_dataset.py. No human labels, no LLM judge — every
metric is checkable against ground truth mined from the corpus glossaries:

  retrieval@k     : the expected source document is among the retrieved references
  citation        : a returned reference points to text that contains the expected
                    answer keyword (the citation actually supports the answer)
  faithfulness*   : the answer contains the expected keyword or the term (lenient, no judge)
  answered        : answerable questions are NOT refused
  refusal         : out-of-corpus questions ARE refused (no fabrication)

    python eval/insurance/run_eval.py [--mode mix] [--top-k 5] [--base http://localhost:9621]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re

import requests

HERE = pathlib.Path(__file__).resolve().parent
DATASET = HERE / "datasets" / "insurance_eval.jsonl"

DEFAULT_BASE = os.getenv("LIGHTRAG_BASE_URL", "http://localhost:9621")
DEFAULT_MODE = os.getenv("LIGHTRAG_QUERY_MODE", "mix")
TOP_K = 5
# Refusal detection. LightRAG only emits the hardcoded `[no-context]` sentinel
# (PROMPTS["fail_response"]) when retrieval returns *nothing*. More often, irrelevant
# chunks are retrieved and the LLM produces a natural-language refusal, because the prompt
# instructs it to "state that you do not have enough information to answer" (prompt.py:356).
# These markers are matched whitespace-normalized and chosen to be refusal-specific
# (unlikely to appear in a genuine term-definition answer).
REFUSAL_MARKERS = (
    "[no-context]",
    "沒有足夠",  # 沒有足夠的信息 / 沒有足夠的資訊 (don't have enough info)
    "沒有權限",  # no permission/ability (e.g. "can't book a flight")
    "沒有提到",  # "[the context] does not mention ..."
    "沒有關於",  # "I have no information about ..."
    "沒有相關資訊",
    "無法回答",  # unable to answer
    "do not have enough information",
    "don't have enough information",
    "not able to provide an answer",
    "no relevant information",
    "cannot help",
)


def _norm(s: str) -> str:
    """Drop whitespace — PDF-extracted Chinese has spurious, inconsistent spaces, so keyword
    matching must be whitespace-insensitive (expected keywords are already space-stripped)."""
    return re.sub(r"\s+", "", s or "")


def _load(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class LightRAGClient:
    def __init__(self, base: str, mode: str, top_k: int, timeout: int = 600):
        self.base = base.rstrip("/")
        self.mode = mode
        self.top_k = top_k
        self.timeout = timeout
        self.session = requests.Session()
        api_key = os.getenv("LIGHTRAG_API_KEY")
        if api_key:
            self.session.headers["X-API-Key"] = api_key

    def answer(self, query: str) -> dict:
        """Return {answer, refused, references:[{file, texts:[...]}]}.

        references[*].texts are the actual chunk contents (include_chunk_content=True),
        used for retrieval/citation scoring.
        """
        payload = {
            "query": query,
            "mode": self.mode,
            "chunk_top_k": self.top_k,
            "include_references": True,
            "include_chunk_content": True,
        }
        resp = self.session.post(
            f"{self.base}/query", json=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("response", "") or ""
        answer_norm = _norm(answer)
        refused = any(_norm(m) in answer_norm for m in REFUSAL_MARKERS)
        refs = []
        for ref in data.get("references") or []:
            refs.append(
                {
                    "file": pathlib.PurePath(ref.get("file_path", "")).name,
                    "texts": ref.get("content") or [],
                }
            )
        return {"answer": answer, "refused": refused, "references": refs}


def run(client: LightRAGClient, dataset_path: pathlib.Path = DATASET) -> dict:
    cases = _load(dataset_path)
    agg: dict[str, list[bool]] = {
        k: [] for k in ["retrieval", "citation", "faithfulness", "answered", "refusal"]
    }
    failures: list[str] = []

    for c in cases:
        q = c["q"]
        try:
            r = client.answer(q)
        except Exception as e:  # noqa: BLE001 — endpoint error → record as failure, keep going
            failures.append(f"[ERROR] {q[:30]} :: {e}")
            continue

        if c["dimension"] == "refusal":
            ok = r["refused"] is True
            agg["refusal"].append(ok)
            if not ok:
                failures.append(
                    f"[refusal] should refuse but answered: {q[:30]} → {r['answer'][:40]}"
                )
            continue

        # answerable (definition / mixed_lang)
        kw = c.get("expected_keyword", "")
        src = c.get("expected_source")
        # All retrieved chunk texts (whitespace-normalized), and the set of source files.
        ref_files = {ref["file"] for ref in r["references"]}
        ref_texts = [_norm(t) for ref in r["references"] for t in ref["texts"]]

        if src:
            # Terms are often defined in MULTIPLE docs, so "expected source in references" OR
            # the answer keyword appearing in any retrieved chunk both count as correct retrieval.
            got = (src in ref_files) or (bool(kw) and any(kw in t for t in ref_texts))
            agg["retrieval"].append(got)
            if not got:
                failures.append(
                    f"[retrieval] {q[:24]} expected {src} / '{kw}' not in references"
                )
        if kw:
            # Citation-accuracy = a cited passage actually contains the answer keyword (it
            # genuinely supports the claim). Whitespace-insensitive; doc identity doesn't
            # matter for a multiply-defined term — what matters is the citation backs the answer.
            cite_ok = any(kw in t for t in ref_texts)
            agg["citation"].append(cite_ok)
            if not cite_ok and not r["refused"]:
                failures.append(f"[citation] {q[:24]} no reference contains '{kw}'")

        agg["answered"].append(not r["refused"])
        if kw:
            faithful = (kw in _norm(r["answer"])) or (
                c.get("term_zh", "\0") in _norm(r["answer"])
            )
            agg["faithfulness"].append(faithful)
            if not faithful and not r["refused"]:
                failures.append(f"[faithful] {q[:24]} missing '{kw}' in answer")

    scores = {
        k: (round(100 * sum(v) / len(v)) if v else None, len(v)) for k, v in agg.items()
    }
    return {"n_cases": len(cases), "scores": scores, "failures": failures}


def sum_str(pct: int, n: int) -> str:
    return f"{round(pct * n / 100)}/{n}"


def main() -> int:
    ap = argparse.ArgumentParser(description="LightRAG insurance eval")
    ap.add_argument("--base", default=DEFAULT_BASE, help="LightRAG server base URL")
    ap.add_argument(
        "--mode",
        default=DEFAULT_MODE,
        choices=["local", "global", "hybrid", "naive", "mix"],
        help="query mode",
    )
    ap.add_argument("--top-k", type=int, default=TOP_K, help="chunk_top_k for retrieval")
    ap.add_argument("--dataset", default=str(DATASET), help="path to eval jsonl")
    args = ap.parse_args()

    client = LightRAGClient(args.base, args.mode, args.top_k)
    res = run(client, pathlib.Path(args.dataset))
    print(
        f"\nEVAL — {res['n_cases']} cases  (mode={args.mode}, top_k={args.top_k})\n"
        + "-" * 48
    )
    for dim, (pct, n) in res["scores"].items():
        bar = "—" if pct is None else f"{pct:3d}%  ({sum_str(pct, n)})"
        print(f"  {dim:14s} {bar}")
    if res["failures"]:
        print(f"\n{len(res['failures'])} failures (first 12):")
        for f in res["failures"][:12]:
            print("  " + f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
