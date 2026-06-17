# Eval snapshot — 2026-06-14 (rerank fixed + context-budget tuned)

LightRAG, gemma-4-26B-A4B-it (llama-swap), BGE-M3 embed, **BGE-reranker-v2-m3 rerank (now working)**, mix mode, 48 cases.

| dimension     | before (broken rerank) | **after (this run)** |
|---------------|------------------------|----------------------|
| retrieval@5   | 95% (38/40)            | **100% (40/40)**     |
| citation      | 72% (31/43)            | **100% (43/43)**     |
| faithfulness  | 100% (43/43)           | **100% (43/43)**     |
| answered      | 100% (43/43)           | **100% (43/43)**     |
| refusal       | 100% (5/5)             | **100% (5/5)**       |
| speed         | ~31 s/case             | **11.5 s/case** (~2.7× faster) |

Run: `--mode mix --top-k 5 --workers 1 --max-total-tokens 12000 --max-entity-tokens 1500 --max-relation-tokens 1500`
Wall = 554 s.

## What changed and why it mattered

Two fixes were applied after profiling a single query's retrieval pipeline:

### 1. Reranking was silently broken (the citation killer)
`.env` had `RERANK_MODEL=BAAI` (truncated) and `VLLM_RERANK_MODEL=BAAI/bge-m3` (the
*embedding* model, not a reranker). Every query sent `model=BAAI` → the rerank server
returned `404 "model BAAI does not exist"` → tenacity retried with exponential backoff
(~8 s wasted) → fell back to **unreranked** chunks. So chunks were ordered by raw vector
similarity and the exact defining chunk often fell outside the top-5 — hence citation 72%.

Fix: `RERANK_MODEL=BAAI/bge-reranker-v2-m3` and `VLLM_RERANK_MODEL=BAAI/bge-reranker-v2-m3`,
then recreate the `vllm-rerank` + `lightrag` containers. Logs now show
`Successfully reranked: 5 chunks from ~180 original chunks` on every query. The cross-encoder
pulls the defining chunk into the top-5 → **retrieval 95→100%, citation 72→100%**.

### 2. Generation was dominated by an oversized context prefill
Default `mix` built a **~34k-token** prompt (49 entities + 160 relations + 5 chunks);
prefilling it was ~70% of the ~31 s/query (generation), with output length a minor factor.
Capping the context (`max_total_tokens=12000`, entity/relation budgets `1500` each) shrank
the prompt to ~12k tokens and cut per-query time to ~11.5 s **without** dropping any of the
5 reranked chunks from the references (so retrieval@5 stays a fair, comparable measurement).

## Per-query pipeline timing (profiled before the fixes)
| stage | time | note |
|---|---|---|
| keyword extraction (LLM) | ~1 s | fine |
| query embedding (BGE-M3) | ~0.001 s | negligible |
| vector search + graph context | ~0.1 s | fine |
| rerank | ~8 s | **was 100% wasted retry backoff (404); now ~real, fast** |
| answer generation (prefill + decode) | ~17–23 s | dominated by context prefill → cut via budget |

## Notes
- **Concurrency does NOT help here** — the bottleneck is single-GPU compute (prompt prefill).
  Running 4 eval queries in parallel was *slower* (GPU thrash); the harness supports
  `--workers` but `1` is best on this hardware. The real speed lever is context size.
- Budget too low starves the references: `max_total_tokens=6000` returned only 1–3 chunks
  and dropped retrieval to 55% — a measurement artifact, not a quality loss. 12000 keeps 5.
- `.env` rerank changes are not committed (`.env` is gitignored; holds API keys).

## Reproduce
```
python eval/insurance/run_eval.py --mode mix --top-k 5 --workers 1 \
  --max-total-tokens 12000 --max-entity-tokens 1500 --max-relation-tokens 1500
```
