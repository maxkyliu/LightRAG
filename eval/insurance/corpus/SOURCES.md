# Public Traditional-Chinese HK Insurance Corpus — Verified Sources (T5 gate)

T5 corpus-verification gate: **PASS** (2026-06-10).
Verified: AIA term-life provisions PDF extracts clean Traditional Chinese via `pdftotext`
(machine-readable text, NOT scanned). Structure: bilingual defined-terms glossary, numbered
clauses, benefit tables. Stamped 樣 (public sample). OCR not required for these PDFs.

## Source repositories (public, Traditional Chinese, machine-readable)
- VHIS certified plans (govt repository, many insurers, standardized): https://www.vhis.gov.hk/
- AIA policy provisions (條款及細則): https://www.aia.com.hk/ (zh-hk/pdf/provisions, zh-hk/pdf/products)
- HKFI guides & best practices: https://www.hkfi.org.hk/
- FWD product pages: https://www.fwd.com.hk/zh/

## Verified specimen (used for the gate)
- AIA 摯誠定期壽險計劃 provisions (16pp, text):
  https://www.aia.com.hk/content/dam/hk-ecom/zh-hk/pdf/provisions/wisdom-term-contract-chinese.pdf
- AIA 2-in-1 product summary (產品資料概要, has 詞彙表 glossary):
  https://www.aia.com.hk/content/dam/hk-wise/pdf/products/individuals/zh-hk/aia-2in1-protection-linked-plan-regular-premium/AIA2in1ProtectionLinkedPlanRegularPremium_HK_tc.pdf.coredownload.inline.pdf

## Notes for ingestion
- Text PDFs → pdftotext / LlamaIndex PDFReader. Reserve OCR only for any scanned doc.
- Bilingual term pairs (受保人/Insured) aid cross-language retrieval — preserve in chunks.
- Benefit tables need table-aware extraction (do not let chunking shred them) — eval case T4.
