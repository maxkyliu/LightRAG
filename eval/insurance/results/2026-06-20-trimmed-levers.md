# Eval snapshot — 2026-06-20 (trimmed stack + cost levers, local LLM)

Trimmed file-based stack (JsonKV / NetworkX / NanoVectorDB — no Postgres/Neo4j/Milvus),
local LLM kept, with the cost-reduction levers applied. 48 cases, mix mode, `chunk_top_k=5`.

**Stack:** LightRAG (`docker-compose.final.yml`) · LLM = `NVIDIA-Nemotron-3-Nano-Omni`
(llama.cpp via llama-swap) · embed = `BAAI/bge-m3` · rerank = `BAAI/bge-reranker-v2-m3`
(both vLLM, local) · corpus = 7 AIA Traditional-Chinese insurance PDFs.

**Levers applied:**
- `MAX_GLEANING=0` — single extraction pass per chunk (was default 1 → ~2 passes). Ingestion lever.
- `MAX_TOTAL_TOKENS=12000`, `MAX_ENTITY_TOKENS=1500`, `MAX_RELATION_TOKENS=1500` — query context caps.

## Results vs. baseline

| dimension     | baseline 2026-06-14 (gemma-4-26B, gleaning=1) | **this run (Nemotron-Nano, gleaning=0)** |
|---------------|-----------------------------------------------|------------------------------------------|
| retrieval@5   | 100% (40/40)                                  | **98% (39/40)**                          |
| citation      | 100% (43/43)                                  | **98% (42/43)**                          |
| faithfulness  | 100% (43/43)                                  | **98% (42/43)**                          |
| answered      | 100% (43/43)                                  | **100% (43/43)**                         |
| refusal       | 100% (5/5)                                     | **80% (4/5) measured — 100% real**¹      |
| query speed   | 11.5 s/case (wall 554 s)                       | **10.3 s/case (wall 493 s)**             |
| ingestion     | not recorded                                  | **9,405 s (~2 h 37 m)**, 3,476 graph labels |

¹ The one refusal "miss" is a **harness marker gap, not a fabrication**: for "可以幫我訂一張去
東京的機票嗎？" (book me a flight) the model *did* refuse — "I'm sorry, but I don't have the
information…" — but that English phrasing isn't in `run_eval.py`'s `REFUSAL_MARKERS`
(which has "don't have **enough** information", not "don't have **the** information").
Genuine refusal behaviour = 5/5.

## Read

- **Accuracy held.** Swapping a 26B model for a ~tiny Nemotron-Nano **and** halving extraction
  passes (`gleaning=0`) costs only ~1–2 points vs. the gemma baseline, all on known-hard cases:
  - `「我們」` ("we/us") — ultra-generic term defined across many docs; canonical source not in
    top-5. Same hard case flagged in the baseline notes; not a lever regression.
  - English "definition of beneficiary" — answer omitted the Chinese term `受益人` (mixed-lang,
    small-model phrasing).
- **`gleaning=0` did not hurt the graph.** 3,476 labels vs. the baseline's 2,746 nodes; retrieval
  and citation stayed at 98–100%. For this corpus the second extraction pass was not buying recall.
- **Query speed slightly better** (10.3 vs 11.5 s/case) — smaller model, same context caps.
- **Ingestion is the cost/time sink**, not querying: ~2 h 37 m, dominated by one large brochure
  and low write concurrency (`MAX_ASYNC_LLM=2`, `MAX_PARALLEL_INSERT=2`) on a single small local
  model. This is exactly why ingestion (not queries) drives the API-cost model in `deploy/cost-model.csv`.

## Reproduce

```
# levers in .env: MAX_GLEANING=0, MAX_TOTAL_TOKENS=12000, MAX_ENTITY_TOKENS=1500, MAX_RELATION_TOKENS=1500
docker restart lightrag-lightrag-1
# ingest eval/insurance/corpus/*.pdf via POST /documents/upload, wait for 7 processed
LIGHTRAG_API_KEY=... python eval/insurance/run_eval.py --mode mix --top-k 5
```
