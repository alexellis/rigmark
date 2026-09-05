# Appliance metadata

Run `python3 configure.py` and answer the prompts. The generated
`metadata.json` is ignored by Git so local addresses or notes cannot be added
accidentally. The safe, relevant fields are embedded in each result.
These fields are operator-declared. RigMark records and fingerprints them but
cannot independently attest which hardware, weights, or competing traffic were
actually present.

| Field | What to enter |
|---|---|
| `hardware` | Exact accelerator model, memory, and count. |
| `topology` | TP/PP size and whether GPUs are local, switched, or directly connected. |
| `negotiated_link_speed` | Rate reported by the live link, not a product headline. Use `not applicable` for one GPU. |
| `model` | Published model ID or an unambiguous local checkpoint name. |
| `model_revision` | Immutable model commit/digest. For local weights, provide a manifest fingerprint. |
| `quantisation` | Weight and activation formats, for example FP8 or W4A4 NVFP4. |
| `kv_cache_dtype` | Actual KV format, including calibration if relevant. |
| `serving_engine` | Engine name plus exact version or commit. |
| `serving_image` | Immutable container digest, or `not applicable`. |
| `drafter` | Speculative method, draft depth, sampling method, or `none`. |
| `context_limit` | Configured maximum context as an integer. |
| `scheduler` | Maximum sequences, batched tokens, and material scheduler flags. |
| `competing_traffic` | State `none` only after checking; otherwise disclose every co-tenant. |

Do not put API keys, passwords, private endpoint URLs, usernames, home
directories, or internal hostnames into metadata. The benchmark separately
refuses credentials embedded in `--base-url` and never writes that URL to the
result.

Add further public-safe fields when they materially affect performance. Useful
examples from published appliance recipes include the kernel version and IOMMU
mode, chat-template revision or hash, NCCL revision and environment, MoE
backend and tuning-table revision, CUDA-graph capture sizes, exact network
interface count, and container command-line flags. Unknown is more honest than
an inferred value.
