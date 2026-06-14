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
import concurrent.futures
import json
import os
import pathlib
import re
import threading
import time

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
    def __init__(
        self,
        base: str,
        mode: str,
        top_k: int,
        timeout: int = 600,
        response_type: str | None = None,
        max_total_tokens: int | None = None,
        max_entity_tokens: int | None = None,
        max_relation_tokens: int | None = None,
        query_top_k: int | None = None,
    ):
        self.base = base.rstrip("/")
        self.mode = mode
        self.top_k = top_k
        self.timeout = timeout
        # Optional context-budget / output controls. The defaults (None) leave LightRAG's
        # server-side defaults untouched; setting them shrinks the prompt prefill (the
        # dominant generation cost) and/or the answer length, speeding queries up markedly.
        self.response_type = response_type
        self.max_total_tokens = max_total_tokens
        self.max_entity_tokens = max_entity_tokens
        self.max_relation_tokens = max_relation_tokens
        self.query_top_k = query_top_k
        # One session per thread — requests.Session isn't guaranteed thread-safe.
        self._local = threading.local()
        self._api_key = os.getenv("LIGHTRAG_API_KEY")

    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            if self._api_key:
                s.headers["X-API-Key"] = self._api_key
            self._local.session = s
        return s

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
        if self.response_type:
            payload["response_type"] = self.response_type
        if self.max_total_tokens:
            payload["max_total_tokens"] = self.max_total_tokens
        if self.max_entity_tokens:
            payload["max_entity_tokens"] = self.max_entity_tokens
        if self.max_relation_tokens:
            payload["max_relation_tokens"] = self.max_relation_tokens
        if self.query_top_k:
            payload["top_k"] = self.query_top_k

        # The LLM backend (llama.cpp via llama-swap) has a fixed number of parallel slots
        # and returns 429/503 when saturated. Under concurrency, retry those a few times
        # with backoff rather than recording a spurious failure.
        last_exc: Exception | None = None
        for attempt in range(4):
            resp = self._session().post(
                f"{self.base}/query", json=payload, timeout=self.timeout
            )
            if resp.status_code in (429, 503):
                last_exc = requests.HTTPError(f"{resp.status_code} backpressure")
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            break
        else:
            raise last_exc or RuntimeError("query failed after retries")

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


def run(
    client: LightRAGClient,
    dataset_path: pathlib.Path = DATASET,
    workers: int = 1,
) -> dict:
    cases = _load(dataset_path)
    agg: dict[str, list[bool]] = {
        k: [] for k in ["retrieval", "citation", "faithfulness", "answered", "refusal"]
    }
    failures: list[str] = []

    # Fan out the (independent) queries across `workers` threads, then aggregate the
    # results in dataset order so scoring stays deterministic regardless of completion order.
    t0 = time.time()
    results: list[tuple[dict, dict | None, Exception | None]] = [None] * len(cases)  # type: ignore

    def _work(i: int, c: dict):
        try:
            return i, c, client.answer(c["q"]), None
        except Exception as e:  # noqa: BLE001 — record and keep going
            return i, c, None, e

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for fut in concurrent.futures.as_completed(
            ex.submit(_work, i, c) for i, c in enumerate(cases)
        ):
            i, c, r, e = fut.result()
            results[i] = (c, r, e)
    elapsed = time.time() - t0

    for c, r, e in results:
        q = c["q"]
        if e is not None:
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
    return {
        "n_cases": len(cases),
        "scores": scores,
        "failures": failures,
        "elapsed_s": elapsed,
        "per_case_s": elapsed / len(cases) if cases else 0.0,
    }


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
    ap.add_argument(
        "--workers",
        type=int,
        default=int(os.getenv("EVAL_WORKERS", "1")),
        # NOTE: this stack is single-GPU compute-bound (prompt prefill), so concurrency
        # makes it SLOWER (GPU thrash). 1 is fastest here; raise only if the LLM backend
        # genuinely has spare parallel capacity.
        help="concurrent queries (default 1; >1 is slower on a single GPU)",
    )
    ap.add_argument(
        "--response-type",
        default=None,
        help="LightRAG response_type, e.g. 'Single Paragraph' (shorter = faster generation)",
    )
    # Proven defaults (2026-06-14): cap the context to ~12k tokens. This cuts the dominant
    # prompt-prefill cost (~2.7x faster) while still keeping all 5 reranked chunks in the
    # references, so retrieval@5 stays a fair measurement. Mirrors the server-side .env.
    ap.add_argument(
        "--max-total-tokens",
        type=int,
        default=12000,
        help="cap total context tokens (shrinks prompt prefill, the dominant cost)",
    )
    ap.add_argument("--max-entity-tokens", type=int, default=1500)
    ap.add_argument("--max-relation-tokens", type=int, default=1500)
    ap.add_argument(
        "--query-top-k",
        type=int,
        default=None,
        help="entities/relations retrieved (QueryParam.top_k); lower = smaller context",
    )
    args = ap.parse_args()

    client = LightRAGClient(
        args.base,
        args.mode,
        args.top_k,
        response_type=args.response_type,
        max_total_tokens=args.max_total_tokens,
        max_entity_tokens=args.max_entity_tokens,
        max_relation_tokens=args.max_relation_tokens,
        query_top_k=args.query_top_k,
    )
    res = run(client, pathlib.Path(args.dataset), workers=args.workers)
    print(
        f"\nEVAL — {res['n_cases']} cases  "
        f"(mode={args.mode}, top_k={args.top_k}, workers={args.workers})\n"
        + f"wall={res['elapsed_s']:.0f}s  avg={res['per_case_s']:.1f}s/case\n"
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
