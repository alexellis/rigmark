# Published reference runs

These are appliance speed measurements, not model-quality rankings. The older
September sweeps below use a 4,096-token completion limit; the October
comparison uses protocol 1.3's 8,192-token default. Compare results only within
their own matched sweep. A basic output gate means visible output and a normal
finish, not semantic correctness.

## GLM-5.3-Flash TP4: RiNGSiDE and TensorFold, 14 October 2026

Our four-Spark RiNGSiDE run and the [TensorFold EXL3 run shared by
@krunkosaurus](https://gist.github.com/krunkosaurus/d308ea4f658dc65736bc773f5630f3ae)
used the same clean RigMark commit (`612eff1a8239`), protocol 1.3 prompts,
comparison ID, `reasoning_effort=low` request body, 8,192-token decode cap,
and default run counts. `rigmark compare --card` accepted them without
`--allow-mismatch`. These are matched **client requests**, not matched weights,
engines, quantisation, or speculative decoders.

| Measurement | RiNGSiDE NVFP4 | TensorFold EXL3 |
|---|---:|---:|
| Prose decode estimate | 62.1 tok/s | **70.2 tok/s** |
| Prose time to last output ↓ | 16.7 s | **14.3 s** |
| Code decode estimate | 108.6 tok/s | **125.4 tok/s** |
| Code time to last output ↓ | 18.6 s | **16.9 s** |
| Structured ceiling | 156.3 tok/s | **177.2 tok/s** |
| 64K cold prefill | **5,144 tok/s** | 2,615 tok/s |
| 64K cold time to first token ↓ | **12.74 s** | 25.06 s |
| C4 capped code throughput | 159.1 tok/s | **176.9 tok/s** |

TensorFold is about 13% faster on prose decode, 15% on code decode, and 11% on
the capped C4 load. RiNGSiDE is about 1.97× faster on 64K cold prefill. Token
rates assume comparable server-side token accounting; time to last output and
cold time to first token provide complementary wall-clock measures.

All nine cold prefill samples in each receipt requested exactly 8K, 32K, or
64K tokens and reported zero cached tokens. RiNGSiDE used cache salt on an
already-running, idle service; its 54 completed requests accounted for the
entire increase in the server's request counter during our run. TensorFold's
salt did not isolate its cache, so its author restarted all four ranks before
the run. Both passed 15/15 basic output gates. At C4, neither receipt had a
normal stop in its 12 capped streams; C4 measures short-load capacity, not
completed agent tasks. These gates do not establish quality parity between the
two quantisations.

The [RiNGSiDE JSON receipt](results/reference/glm53-ringside-nvfp4-tp4-low-p13.json),
[full ASCII card](results/reference/glm53-ringside-nvfp4-tp4-low-p13.card.txt),
and [matched comparison card](results/reference/glm53-ringside-vs-tensorfold-exl3-p13.card.txt)
are available here. The [public-safe serving metadata](examples/serving-records/alexellis-glm53-ringside-nvfp4-tp4.json)
records the appliance used for this run. The public JSON differs from the raw result only by
replacing a private LAN address in `run.appliance.client` with a generic
description; no sample, setting, or other metadata was changed. The original
raw result is retained privately.

Reproduce the client request against a quiet RiNGSiDE TP4 endpoint using
RigMark commit `612eff1a8239`:

```bash
./rigmark run \
  --base-url http://HEAD:8888 \
  --model nvidia/GLM-5.3-Flash-NVFP4 \
  --label glm53-ringside-tp4-low-p13 \
  --comparison-id 2026-09-05-glm-tp2-tp4-rigmark-v1 \
  --metadata examples/serving-records/alexellis-glm53-ringside-nvfp4-tp4.json \
  --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}'
```

## Matched GLM TP2 → TP4 sweep

This pair used clean RigMark revision `d8353e93b274` and comparison ID
`2026-09-05-glm-tp2-tp4-rigmark-v1`. RigMark's strict comparison accepts the
receipts without `--allow-mismatch`.

| Measurement | GLM-5.3 TP2 | GLM-5.3 TP4 | TP4 / TP2 |
|---|---:|---:|---:|
| Code decode estimate | 42.6 | **75.2** | **1.77×** |
| Code time to last output, seconds ↓ | 50.1 | **28.1** | **0.56×** |
| Prose decode estimate | 22.2 | **29.8** | **1.34×** |
| Prose time to last output, seconds ↓ | 45.4 | **36.7** | **0.81×** |
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
| Code decode estimate | **44.0** | **72.9** | **129.5** |
| Code time to last output, seconds ↓ | **46.4** | **35.8** | **25.2** |
| Prose decode estimate | **18.9** | **48.1** | **84.2** |
| Prose time to last output, seconds ↓ | **55.7** | **68.3** | **19.9** |
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

## Qwen3.8 Flash Next NVFP4, TP2

This standalone protocol 1.1 run used NVIDIA's clean NVFP4 checkpoint across
two directly connected DGX Sparks. The serving stack used TP2 with expert
parallelism, integrated MTP3 drafting, FP8 KV, and a one-million-token YaRN
window. RigMark reached the model through authenticated Toilgate; there was no
competing traffic at the start of the run.

| Measurement | Result |
|---|---:|
| Code decode estimate | **62.8 tok/s** |
| Code time to last output | **31.7 s** |
| Prose decode estimate | **40.0 tok/s** |
| Prose time to last output | **33.9 s** |
| Valid structured ceiling | **67.0 tok/s** |
| Cold 64K prefill | **2,757 tok/s** |
| Warm 64K replay | **21,923 tok/s** |
| C1 short code-load, end-to-end | **48.4 tok/s** |
| C2 short code-load, end-to-end | **84.4 tok/s** |
| C4 short code-load, end-to-end | **129.4 tok/s** |

The engine allocated 4,488,745 logical FP8 KV tokens, equivalent to 4.49
full-depth requests at the configured one-million-token limit. All 15 basic
output gates passed. This result has its own comparison ID and must not be
described as a matched comparison with the older protocol 1.0 table above.

- [Result JSON](results/reference/qwen38-flash-next-nvidia-nvfp4-tp2-low.json)
- [Share card](results/reference/qwen38-flash-next-nvidia-nvfp4-tp2-low.card.txt)
- [Serving record](examples/serving-records/alexellis-qwen38-flash-next-nvfp4-2x-dgx-spark.json)

Reproduce the run with:

```bash
./rigmark run \
  --base-url http://SERVER:PORT \
  --model qwen3.8-flash-next \
  --label qwen38-flash-next-nvidia-nvfp4-tp2-low \
  --comparison-id 2026-09-14-rigmark-standard \
  --metadata examples/serving-records/alexellis-qwen38-flash-next-nvfp4-2x-dgx-spark.json \
  --extra-body '{"reasoning_effort":"low"}'
```

Time to last output matters alongside decode rate. DeepSeek, for example,
decoded prose much faster than GLM but took longer to finish because it emitted
far more reasoning and output. Tokens/second alone does not describe that user
experience, and token definitions may differ between model families.

## Code self-test audit

The basic output gate does not claim that generated code is correct. As an
additional audit, the implementation and test blocks from each retained code
answer were replayed with `go test` in a networkless, read-only, resource-limited
container. All 15 answers compiled; **11/15 model-supplied test suites passed**.

| Appliance | Compiled | Model-supplied tests passed |
|---|---:|---:|
| GLM-5.3 TP2 | 5/5 | 4/5 |
| DeepSeek V4 Flash TP2 | 5/5 | 3/5 |
| Qwen3.8 27B TP1 | 5/5 | 4/5 |

The failures were GLM run 5, DeepSeek runs 4 and 5, and Qwen run 4. This does
not change their measured serving speed; it is a separate self-consistency
signal. Reproduce it from the unedited JSON receipts with:

```bash
docker pull golang@sha256:699337d620559a59b4a2bb298ad59611e535d2ee755a34cf2d2a98f37578dc80
./rigmark audit-code \
  results/reference/glm53-libert-nvfp4-tp2-low.json \
  results/reference/ds4f-0731-nvfp4-tp2-low.json \
  results/reference/qwen38-27b-fp8-rtxpro6000-low.json \
  --image golang@sha256:699337d620559a59b4a2bb298ad59611e535d2ee755a34cf2d2a98f37578dc80
```

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
DSpark MTP drafting at five tokens, and a one-million-token served context.

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
