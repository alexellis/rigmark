# Benchmark protocol

Current protocol version: **1.2.0**.

The purpose of this protocol is reproducibility, not producing the largest
possible number.

## Comparability rules

Two runs are directly comparable only when all of these match:

- benchmark protocol version, prompt-corpus SHA256, and comparison ID;
- run counts, output limits, sampling fields, and extra request body;
- cache-busting/immediate-replay prefill depths and run count;
- concurrency levels, rounds, workload, and output limit; and
- the server-side definition of a prompt and completion token.

For a topology-only claim, model weights, immutable model and drafter
revisions, serving engine/image, quantisation, KV dtype, context limit,
speculative configuration, and scheduler must also match. If they do not, call
it an appliance or recipe comparison.

## Decode

The fixed corpus contains code, prose, and structured workloads. Nonces are
deterministically derived from the nonce version, comparison ID, workload,
and run number. Protocol 1.2 retains the 1.1 nonce version to preserve those
model inputs. Two appliances in a sweep therefore receive byte-identical
prompts. Changing the comparison ID changes the inputs; it is not necessary to
change it to isolate prefill caches. Temperature is zero, `top_p` is one, and
the seed is fixed. These settings do not guarantee deterministic model output.
Each run number still has its own nonce, so the five requests are distinct.
Model-specific fields such as thinking mode are supplied through
`--extra-body`, recorded verbatim, and must match. They cannot override the
fixed benchmark fields.

No universal "thinking off" profile is defined because model templates do not
implement that control consistently. A no-thinking run is a model-specific
ceiling and must use a separate comparison ID and label. It is comparable only
with a receipt carrying the identical extra request body.

The chunk-timed decode estimate is `(completion_tokens - 1) /
(last_output_event_time - first_output_event_time)`. It deliberately excludes
prefill. Server-reported token usage is mandatory. An SSE event can contain
more than one token, so this is an estimate unless the server emits one token
per event. RigMark records the number of measured events and refuses to report
a decode rate when a completion is buffered into one measurable event. The
report publishes the median, minimum, maximum, and p90 of every workload; the
best run is never the headline.

Protocol 1.2 also records `pooled_decode_tokens_per_second` in each decode
workload's JSON: `sum(max(completion_tokens - 1, 0)) / sum(decode_seconds)`.
This pools the same token numerators and timing windows as the per-run
estimates. It is a time-weighted aggregate rate, while the median describes the
middle request rate; neither replaces the other. Longer answers have more
weight in the pooled rate. A zero total decode window yields zero when no
sample has more than one completion token. The share card retains the median
and min/max range.

Ranges describe observed variation, not confidence intervals. There is no
excluded warm-up phase, and five samples do not establish the significance of
a small tuning gain. Changing answer lengths, reasoning, speculative draft
acceptance, and competing traffic can affect the observed rate. Retain the
outputs and timings, and repeat whole suites under controlled conditions when
assessing small differences.

Completion tokens and decode timing cover the complete streamed generation,
including reasoning where a server exposes it separately from visible output.
The result records visible and reasoning character counts independently. The
basic output gate rejects a reasoning-only stream; it is not a correctness
claim.

Structured JSON is an explicitly labelled speculative-decoding ceiling. It is
not a proxy for prose, coding, or agent responsiveness. Its output is checked
against the requested array and every result records whether validation passed.
Visible outputs are retained so that code, prose, truncation, and looping can
be audited. Reasoning text is represented only by its character count and hash.
Code and prose pass the basic output gate only when they emit a non-empty
visible answer and report a normal `stop`. New receipts also require the SSE
`[DONE]` marker. Structured output must meet those conditions and match every
requested value. This is not a correctness score. It rejects obvious
reasoning-only, truncated, filtered, tool-call, or prematurely ended responses.

Time to last output runs from request start through the last visible or
reasoning output. Response wall time additionally includes usage and HTTP/SSE
tail handling. Both are retained; the former is the user-facing end-to-end
latency shown beside decode rate.

## Prefill

The prefill test uses the server's `/tokenize` endpoint to create exact token-ID
prompts, then sends those IDs to `/v1/completions`. Each pair has its own
deterministic nonce. Protocol 1.2 additionally generates a fresh random
256-bit `cache_salt` per pair, sharing it only with that pair's immediate
replay. This prevents reusing a comparison ID from silently warming the next
sweep's cold request, without changing its prompt tokens. The receipt records
`settings.prefill_cache_isolation = "random-salt-per-pair"` and the salt's
SHA256 in both rows, not the salt itself.

Rows retain the server's `prompt_tokens_details.cached_tokens` as
`cached_prompt_tokens`; null means the server did not report it. A known cache
hit on the first request fails the run instead of producing a cold result.
Missing cache usage remains explicitly unverified: the card labels the column
"First" rather than "Cold" and prints a warning. Legacy receipts without this
evidence also render as unverified. A zero count verifies only what the server
reports; it is not independent instrumentation of the cache.

“Cold” means an uncached prompt, not a cold model or cold kernels. "Immediate
replay" describes request order and does not guarantee a cache hit. Its reported
cache usage is retained too. The JSON retains medians and ranges of three pairs
at each depth; the card shows throughput and TTFT for every requested depth.

Effective prefill rate is `prompt_tokens / time_to_first_token`. It includes
fixed request and scheduling overhead, so shallow and deep prompt depths should
both be published. RigMark refuses a sample unless the server-reported prompt
token count exactly equals the requested token-ID depth, and refuses a depth
that cannot fit its eight generated tokens inside the declared context limit.

The decode suite works with OpenAI-compatible chat servers. Exact
cache-busting/immediate-replay prefill additionally requires vLLM-compatible
`/tokenize`, token-ID completion input, and acceptance of `cache_salt`. A server
that rejects the field fails explicitly; RigMark does not silently retry with
unsalted requests. A server that ignores it cannot be trusted to isolate the
cache, so inspect reported cache usage. Use `--skip-prefill` when an engine
lacks these extensions; the card marks the suite incomplete.

## Concurrency

All requests in a round wait on a barrier before opening their HTTP streams.
Each receives a unique nonce. Reports include aggregate end-to-end throughput,
per-stream decode, and per-stream TTFT. Aggregate throughput includes prefill
and scheduling delay and therefore describes service capacity rather than the
decode kernel alone.

## Publishing a result

Publish the unedited JSON file and the exact command. Also disclose hardware,
topology, negotiated link speed, model and drafter revisions, serving image or
commit, quantisation, KV configuration, context limit, speculative depth, and
whether any other traffic shared the endpoint.

The JSON receipt and every share card record the benchmark repository commit
and whether its worktree was dirty when the run began. Source archives embed
the originating Git commit in `.git_archival.txt`, so the same revision is
recorded when the `.git` directory is unavailable. Dirty runs are retained,
not rejected. They include a fingerprint over tracked changes, untracked paths,
and untracked file contents, but a clean committed revision remains preferable
for a reproducible public reference.

The receipt SHA256 is a fingerprint of the published JSON bytes, not a digital
signature or independent attestation. Comparison and reporting recompute
summaries and basic gates from the raw rows before producing a card.


The 74-column card keeps the identity header, basic output gates, decode
medians/ranges, all prefill depths, and capped concurrency results above wrapped
appliance details and settings. It marks omitted phases as incomplete and
prints each changed suite flag, the complete extra request body, and comparison
ID. "DEFAULT SETTINGS" describes the suite parameters, not a universal model
reasoning profile: the separately printed request body remains part of the
comparison. Hardware and request settings wrap rather than being truncated.
