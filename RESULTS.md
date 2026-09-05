# Published reference runs

These are appliance speed measurements, not model-quality rankings. All three
results within each table use the same clean RigMark revision, comparison ID,
prompts, low-effort request body, 4,096-token completion limit, and run counts.
Every code, prose, and structured output passed its completion gate: **15/15
per appliance**.

## Matched GLM TP2 → TP4 sweep

This pair used clean RigMark revision `d8353e93b274` and comparison ID
`2026-09-05-glm-tp2-tp4-rigmark-v1`. RigMark's strict comparison accepts the
receipts without `--allow-mismatch`.

| Measurement | GLM-5.3 TP2 | GLM-5.3 TP4 | TP4 / TP2 |
|---|---:|---:|---:|
| Completed code decode | 42.6 | **75.2** | **1.77×** |
| Completed prose decode | 22.2 | **29.8** | **1.34×** |
| Valid structured ceiling | 54.6 | **109.6** | **2.01×** |
| Cold 64K prefill | 1,905 | **2,276** | **1.19×** |
| Warm 64K replay | 11,464 | **40,859** | **3.56×** |
| C1 short code-load, end-to-end | 31.2 | **50.8** | **1.63×** |
| C2 short code-load, end-to-end | 42.8 | **75.2** | **1.76×** |
| C4 short code-load, end-to-end | 61.1 | **119.3** | **1.95×** |

TP2 used two directly connected DGX Sparks, Libert NVFP4, and adaptive
DFlash2. TP4 used four DGX Sparks in a switchless RoCE ring, Red Hat NVFP4,
BF16 KV, static DFlash2 `k=7`, and the released NCCL v0.1.0 patch. This is an
appliance comparison—not a topology-only claim.

- [TP2 result JSON](results/reference/glm53-libert-nvfp4-tp2-adaptive-low.json)
- [TP2 share card](results/reference/glm53-libert-nvfp4-tp2-adaptive-low.card.txt)
- [TP4 result JSON](results/reference/glm53-redhat-nvfp4-tp4-static-k7-low.json)
- [TP4 share card](results/reference/glm53-redhat-nvfp4-tp4-static-k7-low.card.txt)

## Matched standard sweep

| Measurement | GLM-5.3 TP2 | DeepSeek V4 Flash TP2 | Qwen3.8 27B TP1 |
|---|---:|---:|---:|
| Completed code decode | **44.0** | **72.9** | **129.5** |
| Completed prose decode | **18.9** | **48.1** | **84.2** |
| Valid structured ceiling | **64.9** | **85.2** | **136.0** |
| Cold 64K prefill | **1,922** | **1,628** | **5,808** |
| Warm 64K replay | **11,363** | **172,715** | **85,248** |
| C1 short code-load, end-to-end | **31.6** | **51.2** | **108.7** |
| C2 short code-load, end-to-end | **42.0** | **82.9** | **206.0** |
| C4 short code-load, end-to-end | **66.1** | **127.4** | **385.4** |

Rates are tokens/second. Decode excludes prefill; load throughput includes the
whole request and uses a 256-token cap. Structured output is deliberately
labelled as a speculative-decoding ceiling, not an everyday agent speed. The
model families and hardware differ, so this is an appliance comparison—not a
topology-only claim.

### GLM-5.3-Flash, Libert NVFP4, TP2

Two DGX Sparks connected directly over 200 Gb/s RoCE, FP8 E4M3 KV, native
`flashinfer_cutlass`, and DFlash2 at `k=7`.

| Workload | Median | Five-run range |
|---|---:|---:|
| Code | 44.0 tok/s | 31.6–47.7 |
| Prose | 18.9 tok/s | 17.8–19.3 |
| Structured | 64.9 tok/s | 63.9–66.8 |

The wide code range includes cold-start warm-up in the first two samples; the
median remains representative of the later steady runs. An earlier published
22.9 tok/s “prose” result used a 512-token limit for a roughly 700-word memo and
therefore measured only its faster opening portion. This replacement lets the
answer finish and retains it for inspection.

- [Result JSON](results/reference/glm53-libert-nvfp4-tp2-low.json)
- [Share card](results/reference/glm53-libert-nvfp4-tp2-low.card.txt)

### DeepSeek-V4-Flash-0731, NVFP4, TP2

Two DGX Sparks connected directly over 200 Gb/s RoCE, native NVFP4 MLA KV,
DFlash2 probabilistic drafting at five tokens, and a one-million-token served
context.

| Workload | Median | Five-run range |
|---|---:|---:|
| Code | 72.9 tok/s | 69.7–74.1 |
| Prose | 48.1 tok/s | 43.9–55.5 |
| Structured | 85.2 tok/s | 84.3–85.9 |

- [Result JSON](results/reference/ds4f-0731-nvfp4-tp2-low.json)
- [Share card](results/reference/ds4f-0731-nvfp4-tp2-low.card.txt)

### Qwen3.8-27B FP8, TP1

One RTX PRO 6000 Blackwell Workstation Edition with 96 GB, FP8 E4M3 KV, MTP3,
and a co-resident reserved Gemma service disclosed in the receipt.

| Workload | Median | Five-run range |
|---|---:|---:|
| Code | 129.5 tok/s | 124.0–130.4 |
| Prose | 84.2 tok/s | 81.9–100.1 |
| Structured | 136.0 tok/s | 135.0–136.1 |

- [Result JSON](results/reference/qwen38-27b-fp8-rtxpro6000-low.json)
- [Share card](results/reference/qwen38-27b-fp8-rtxpro6000-low.card.txt)

## Reproduce the sweep

Use one comparison ID on every appliance and its own public-safe metadata file:

```bash
./rigmark run \
  --base-url http://SERVER:PORT \
  --model auto \
  --label APPLIANCE-NAME \
  --comparison-id 2026-09-05-rigmark-standard-v2 \
  --metadata metadata.json \
  --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}'
```

The result JSON contains the clean benchmark revision, appliance metadata,
every raw run, visible generated answers, hashes, TTFTs, prefill samples, and
concurrency tails. Endpoint addresses and credentials are deliberately absent.
