# Benchmark protocol

The purpose of this protocol is reproducibility, not producing the largest
possible number.

## Comparability rules

Two runs are directly comparable only when all of these match:

- benchmark protocol version, prompt-corpus SHA256, and comparison ID;
- run counts, output limits, sampling fields, and extra request body;
- cold/warm prefill depths and run count;
- concurrency levels, rounds, workload, and output limit; and
- the server-side definition of a prompt and completion token.

For a topology-only claim, model weights, immutable model and drafter
revisions, serving engine/image, quantisation, KV dtype, context limit,
speculative configuration, and scheduler must also match. If they do not, call
it an appliance or recipe comparison.

## Decode

The fixed corpus contains code, prose, and structured workloads. Nonces are
deterministically derived from the protocol version, comparison ID, workload,
and run number. Two appliances in a sweep therefore receive byte-identical
prompts, while a new comparison ID prevents accidental cache reuse in a later
sweep. Temperature is zero, `top_p` is one, and the seed is fixed.
Model-specific fields such as thinking mode are supplied through
`--extra-body`, recorded verbatim, and must match. They cannot override the
fixed benchmark fields.

Decode rate is `(completion_tokens - 1) / (last_token_time - first_token_time)`.
It deliberately excludes prefill. Server-reported token usage is mandatory.
The report publishes the median, minimum, maximum, and p90 of every workload;
the best run is never the headline.

Completion tokens and decode timing cover the complete streamed generation,
including reasoning where a server exposes it separately from visible output.
The result records visible and reasoning character counts independently, and
the completion gate prevents a reasoning-only stream from being called a
completed code or prose answer.

Structured JSON is an explicitly labelled speculative-decoding ceiling. It is
not a proxy for prose, coding, or agent responsiveness. Its output is checked
against the requested array and every result records whether validation passed.
Visible outputs are retained so that code, prose, truncation, and looping can
be audited. Reasoning text is represented only by its character count and hash.
Code and prose pass the completion gate only when they emit a non-empty visible
answer without a length stop. This is not a correctness score, but prevents
reasoning-only or truncated streams from masquerading as completed work.

## Prefill

The prefill test uses the server's `/tokenize` endpoint to create exact token-ID
prompts, then sends those IDs to `/v1/completions`. Each pair has its own
deterministic nonce, which defeats the prefix cache for the cold request. The
identical token list is immediately replayed for the warm measurement. The
default suite reports the median and range of three pairs at each depth.

Effective prefill rate is `prompt_tokens / time_to_first_token`. It includes
fixed request and scheduling overhead, so shallow and deep prompt depths should
both be published.

The decode suite works with OpenAI-compatible chat servers. Exact cold/warm
prefill additionally requires vLLM-compatible `/tokenize` and token-ID
completion input; use `--skip-prefill` when an engine lacks these extensions.

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
