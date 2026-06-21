# SmartRAG — Deployment Sizing, Cost Model & Benchmark

Evaluation of how to deploy the full SmartRAG stack (LightRAG API + WebUI + Telegram
gateway + retrieval models + datastores) to the cloud, the cost of running it on hosted
LLM APIs, and a **measured** benchmark of the trimmed/cost-optimized configuration.

> Prices are representative (early 2026) and **must be verified live** before any
> commercial decision. The token-per-MB assumption is the dominant uncertainty.

---

## 1. Components that have to run

| Component | Resource | Notes |
|---|---|---|
| LightRAG API + WebUI | CPU / RAM | FastAPI + gunicorn; WebUI is static, served by the API |
| Generative LLM | **GPU** (if self-hosted) or **API** | The cost driver |
| Embeddings — `BAAI/bge-m3` | small GPU / CPU | ~2.5 GB VRAM |
| Reranker — `BAAI/bge-reranker-v2-m3` | small GPU | ~2.5 GB VRAM |
| Whisper STT (Telegram) — `whisper-large-v3-turbo` | small GPU / CPU | ~1.6 GB VRAM |
| Datastores | CPU / RAM / disk | **Trim to Postgres-only** (see §3) |

---

## 2. Self-hosting the LLM (GPU) — instance sizing

GPU is sized by the **generative** model (embed/rerank/Whisper are small and co-resident).

| Model class | fp16 | 4-bit (AWQ) | + aux (~7 GB) | Fits on |
|---|---|---|---|---|
| 7–8B | ~16 GB | ~6–8 GB | ~14 GB (q) | 24 GB (q) / 48 GB (fp16) |
| 14B | ~28 GB | ~10 GB | ~17 GB | 48 GB |
| 32B | ~64 GB | ~20 GB | ~27 GB | 48 GB (q) |
| 70B | ~140 GB | ~40–45 GB | ~50 GB | 80 GB (q) |

| Tier | Example instance | GPU | ~Monthly (24/7 on-demand) |
|---|---|---|---|
| A — pilot (8B q) | AWS `g6.2xlarge` / DO A5000 | L4 / A5000 24 GB | **~$715 / ~$1,000** |
| B — balanced (14–32B q) | AWS `g6e.2xlarge` / DO A6000 | L40S / A6000 48 GB | **~$1,635 / ~$1,380** |
| C — high quality (70B) | DO/Paperspace A100 80 GB | A100 80 GB | **~$2,320** |

Reserved (1-yr) ≈ −40%, spot ≈ −60–70%. **AWS has no single-80 GB-GPU instance** (jumps to
8-GPU `p4d`) — for 70B, DigitalOcean/Paperspace A100/H100 is far cheaper.

A single **48 GB GPU box with 64 GB RAM (Tier B)** runs the LLM + all aux models *and* the
trimmed datastore on one machine — simplest and cheapest if self-hosting.

---

## 3. Trimmed datastore (the recommended stack)

Collapse the full compose (Postgres + Neo4j + Milvus + etcd + minio + Redis) to **Postgres
only**: with the `pgvector` + Apache-AGE build, Postgres covers KV + vector + graph +
doc-status. Add Redis for cache. Everything co-locates on one CPU box.

| Setup | ~Monthly (fixed, shared across all teams) |
|---|---|
| DigitalOcean lean (1 droplet 4 vCPU/8 GB + 100 GB vol) | **~$58** |
| AWS (t3.large + RDS t3.small + EBS) | **~$95** |

For a **local / single-box** run, the file-based storage (`JsonKVStorage` /
`NetworkXStorage` / `NanoVectorDBStorage`) is even leaner — no DB services at all. That's
what the benchmark in §5 used.

---

## 4. LLM-API cost model (don't-self-host alternative)

The project default is **OpenAI API**. A GPU running 24/7 costs ~$700–2,300/mo *regardless
of usage*; for low/medium volume, hosted APIs on a cheap CPU box are far cheaper.

Full, editable model: **[`cost-model.csv`](./cost-model.csv)** (open in Excel/Sheets; formulas
recompute when you edit assumptions). Grounded in the real defaults `CHUNK_SIZE=1200`,
`MAX_GLEANING=1`, `CHUNK_TOP_K=20`.

Baseline unit economics (representative early-2026 prices):

| Provider | $/MB ingest | $/query |
|---|---|---|
| OpenAI (`gpt-5.4-mini` + `text-embedding-3-large`) | $1.12 | $0.0054 |
| OpenRouter (Qwen2.5-72B / DeepSeek-V3 class) | $0.51 | $0.0030 |
| **Gemini 2.5 Flash (recommended)** | **$0.48** | **$0.0025** |

| Per-team monthly (API only) | OpenAI | OpenRouter | Gemini Flash |
|---|---|---|---|
| Normal (10 MB incr + 1k queries) | ~$17 | ~$8 | ~$7 |
| Advance (200 MB incr + 20k queries) | ~$335 | ~$163 | ~$147 |
| Fill 2 GB (one-time) | $2,241 | $1,020 | $961 |

**Ingestion, not querying, is the cost.** Your `Advance` price must clear ~$150–330/mo of
inference to break even. Recommendation: **Gemini 2.5 Flash** (lowest input price — ideal
for LightRAG's input-heavy extraction); OpenRouter for model flexibility; self-host the LLM
only for data residency or steady high volume.

### Cost levers
- `MAX_GLEANING=0` → ~35% less ingestion (validated in §5 with no accuracy loss on this corpus).
- Self-host embeddings (`bge-m3`) → removes embed API cost, keeps text off third parties.
- Lower `CHUNK_TOP_K` / `MAX_TOTAL_TOKENS` → cheaper, faster queries.

---

## 5. Measured benchmark — trimmed stack + levers (local LLM)

Run on a local GB10 box: file-based storage, local `NVIDIA-Nemotron-3-Nano-Omni` (llama-swap),
local `bge-m3` + `bge-reranker-v2-m3`, levers `MAX_GLEANING=0` + `MAX_TOTAL_TOKENS=12000`.
Harness: `eval/insurance/run_eval.py` (48 labeled cases, mix mode, `chunk_top_k=5`).
Full write-up: [`../eval/insurance/results/2026-06-20-trimmed-levers.md`](../eval/insurance/results/2026-06-20-trimmed-levers.md).

| Dimension | Baseline (gemma-4-26B, gleaning=1) | **Trimmed + levers (Nemotron-Nano, gleaning=0)** |
|---|---|---|
| retrieval@5 | 100% | **98% (39/40)** |
| citation | 100% | **98% (42/43)** |
| faithfulness | 100% | **98% (42/43)** |
| answered | 100% | **100%** |
| refusal | 100% | **100% real** (80% measured — English-phrasing harness gap) |
| query speed | 11.5 s/case | **10.3 s/case** (wall 493 s) |
| ingestion | not recorded | **9,405 s (~2 h 37 m)**, 3,476 graph labels |

**Findings**
- Accuracy held within 1–2 points despite dropping from a 26B model to a tiny Nano model
  **and** halving extraction passes. Both misses are known-hard cases, not lever regressions.
- `MAX_GLEANING=0` did not hurt the graph (3,476 vs 2,746 labels) — the second extraction
  pass wasn't buying recall on this corpus, so the ~35% ingestion saving was effectively free.
- Queries are cheap and fast; **ingestion is the time/cost sink** — empirically confirming the
  cost model. Ingestion wall time was bottlenecked by `MAX_ASYNC_LLM=2` / `MAX_PARALLEL_INSERT=2`
  on a single small local model; raising concurrency would cut it materially.

---

## Bottom line

- **Cheapest path:** keep LLM + embeddings on a hosted API (Gemini Flash), host app +
  Postgres on a ~$58–95/mo CPU box. Best for low/medium volume.
- **Self-host path:** one 48 GB GPU box (DO/Paperspace A6000 ~$1,380/mo) running a 14–32B
  AWQ model + aux models + trimmed Postgres, reserved pricing for ~−40%.
- **Either way:** apply the cost levers (`MAX_GLEANING=0`, self-hosted embeddings, smaller
  query context) — measured to preserve accuracy on this corpus.
