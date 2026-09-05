# RigMark

![RigMark — benchmarks local AI how coding agents actually use it](docs/images/rigmark-hero.png)

**RigMark benchmarks local AI how coding agents actually use it.**

Most AI benchmarks reduce a serving stack to one flattering number. RigMark is
a reproducible stress test for the whole OpenAI-compatible appliance:
agent-shaped code and prose, an explicitly labelled structured-output ceiling,
exact cache-busting/immediate-replay prefill, and concurrent request behaviour.
It is a serving benchmark, not a claim that three prompts reproduce a complete
multi-turn coding session.

It is deliberately model-agnostic: use it with Qwen, GLM, DeepSeek, vLLM,
SGLang, local GPU servers, or multi-node DGX Spark recipes. A different model or
serving stack is an appliance comparison; identical weights and software are
required before claiming a topology-only speed-up.

## One screenshot, one receipt

```text
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│  R I G M A R K   //   AGENT WORKLOAD RECEIPT                                             │
│  BENCHMARKS LOCAL AI HOW CODING AGENTS ACTUALLY USE IT                                   │
│  ●  15/15 BASIC OUTPUT GATES PASSED                                                      │
├─ SYSTEM ─────────────────────────────────────────────────────────────────────────────────┤
│  MODEL      Qwen3.8-27B-FP8-vllm                                                         │
│  APPLIANCE  1x NVIDIA RTX PRO 6000 Blackwell Workstation Edition, 96 GB                  │
│  RUN        reasoning=low  •  protocol=1.0.0                                             │
│  SOURCE     git:046e92cbe941  •  clean                                                   │
├─ REAL OUTPUT ────────────────────────────────────────────────────────────────────────────┤
│  WORKLOAD       DECODE EST.      LAST OUTPUT          RANGE          BASIC GATE          │
│  CODE             129.5 tok/s      25.2s last    124.0–130.4    ✓ 5/5                    │
│  PROSE             84.2 tok/s      19.9s last     81.9–100.1    ✓ 5/5                    │
│  STRUCTURED*      136.0 tok/s       7.9s last    135.0–136.1    ✓ 5/5                    │
│  * predictable-output ceiling; not a proxy for agent speed                               │
├─ CONTEXT ────────────────────────────────────────────────────────────────────────────────┤
│  64K PREFILL   cold 5,808 tok/s  •  immediate replay 85,248 tok/s                        │
├─ CAPPED CONCURRENT GENERATION ───────────────────────────────────────────────────────────┤
│  SHORT CODE • END-TO-END • 256-TOKEN CAP PER AGENT                                       │
│  AGGREGATE   C1 108.7  •  C2 206.0  •  C4 385.4 tok/s                                    │
│  C4 OUTPUT STATE   normal stop 0/12  •  visible 2/12  •  reasoning may be included       │
├─ RECEIPT ────────────────────────────────────────────────────────────────────────────────┤
│  JSON       sha256:604ea2c48107a69f…                                                     │
│  SHARE THE CARD • LINK THE JSON RECEIPT • #RIGMARK                                       │
│  github.com/alexellis/rigmark                                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
```

This card is rendered from a published protocol 1.0 receipt. The current runner
emits protocol 1.1 receipts with stricter stream and timing evidence.

The card is the shareable headline. It always shows the benchmark Git revision
and whether that worktree was clean or dirty. GitHub source archives embed the
originating commit too, so downloading a tarball does not lose the benchmark
revision. The content-hashed
[result JSON](results/reference/qwen38-27b-fp8-rtxpro6000-low.json) is the
receipt: complete outputs, ranges, TTFT, settings, and appliance metadata.
The checksum identifies those exact bytes; it is not a signature or independent
attestation. A linked Git commit or release supplies the public anchor.

## Run the standard suite

Python 3.10 or newer is required; there are no third-party packages.

```bash
git clone https://github.com/alexellis/rigmark
cd rigmark
./rigmark configure

./rigmark run \
  --base-url http://SERVER:8000 \
  --model auto \
  --label my-appliance \
  --comparison-id weekend-sweep-1 \
  --metadata metadata.json
```

The configurator explains every metadata field and writes the ignored local
`metadata.json`. See [`METADATA.md`](METADATA.md) if an agent is filling it in
for you. The benchmark refuses unchanged placeholders or missing required
fields. Use the same comparison ID for every appliance in one A/B sweep. This
makes every generated prompt byte-for-byte identical; use a new ID for the next
sweep. If the model supports graded effort or a thinking toggle, set it
explicitly with `--extra-body` and use the identical value throughout the
sweep; model defaults are not assumed equivalent.

The default suite performs:

- five runs of code, prose, and structured JSON with a 4,096-token ceiling;
- three cold/immediate-warm pairs at 8,192, 32,768, and 65,536 tokens; and
- three rounds of code at concurrency 1, 2, and 4 with 256-token outputs.

The concurrency phase is deliberately a capped generation-capacity test. It
reports normal-stop and visible-output counts and must not be described as
completed multi-agent coding work; reasoning models may spend the entire cap on
reasoning.

Results are written to `results/LABEL-TIMESTAMP.json`. Neither the endpoint URL
nor API credentials are written to the result. Credentials are read from
`OPENAI_API_KEY` by default; use `--api-key-env NAME` to select another
environment variable. Visible generated output is retained for auditability;
reasoning text is not retained, although its size and hash are recorded.
Every decode workload has a basic output gate. Code and prose must emit a
visible answer and finish normally; structured JSON must additionally match
every requested value. This is not a code-correctness score. Throughput from a
failed gate remains diagnostic but must not be cited as a successful workload
result. RigMark also reports time to the last generated output, because tok/s
alone can conceal how long a verbose or reasoning-heavy answer takes.

At the end, the runner prints a terminal result card designed to be
screenshotted and saves a stable `RESULT.card.txt` beside the JSON. Reprint or
regenerate it at any time with:

```bash
./rigmark report --save results/YOUR-RESULT.json
```

Share the card with the complete JSON—the card is the headline, and the JSON
is the receipt.

The code answer deliberately includes an implementation and its own test suite.
Replay those model-supplied tests in a locked-down Docker container with:

```bash
docker pull golang:1.25
./rigmark audit-code results/YOUR-RESULT.json
```

Generated code is untrusted. The command disables networking, drops
capabilities, makes the container root filesystem and source mount read-only,
and applies CPU, memory, and process limits. A disposable VM remains the
stronger isolation boundary. Passing model-written tests is useful evidence of
self-consistency, not proof of correctness.

## Challenge a recipe

Run the standard suite unchanged against a quiet endpoint and publish its card
and JSON receipt. That is the whole challenge: agent-shaped code and prose,
structured output labelled as a ceiling, cache-busting and immediate-replay
prefill, and concurrent service load under one disclosed protocol. A recipe may
optimise anything on the server side; RigMark keeps the client-side work and
claim boundaries fixed.

There is deliberately no universal `thinking=off` profile. Some templates
implement that switch, some ignore it, and others expose different controls.
Publish such a run as a separately labelled, model-specific ceiling and compare
it only with receipts carrying the identical request body.

For an engine without vLLM's `/tokenize` extension or token-ID completion
input, add `--skip-prefill`. To omit load testing, add `--skip-concurrency`.

## Compare two results

```bash
./rigmark compare results/recipe-a.json results/recipe-b.json
```

For a matched, screenshot-ready A/B card:

```bash
./rigmark compare --card results/recipe-a.json results/recipe-b.json
```

The comparison validates raw rows against reported summaries and gates, then
stops when the benchmark revision, protocol, prompt corpus, seed,
thinking/request body, run counts, output lengths, prefill depths/runs, or
concurrency settings differ. `--allow-mismatch` exists for exploratory
comparisons and prints the mismatches. A matched card means the client requests
match; token/s ratios still require matching server-side token definitions.

## Fair-use checklist

- Run against a quiet endpoint and disclose any competing traffic.
- Pin and publish model, drafter, engine/image, and benchmark revisions.
- Publish the complete result JSON and command, not only a screenshot.
- Check the retained outputs and code-test audit; throughput alone is not a
  quality score.
- Headline code and prose medians with their ranges—not a best run.
- Label structured output as a speculative-decoding ceiling.
- Report cache-busting and immediate-replay prefill separately.
- Verify the negotiated fabric rate rather than copying a product headline.

The exact measurement definitions and claim boundaries are in
[`PROTOCOL.md`](PROTOCOL.md).

## Published reference runs

Reference results include their complete generated outputs and appliance
metadata, not just headline numbers. See [`RESULTS.md`](RESULTS.md) for the
current table and exact commands.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile audit_code.py bench.py compare.py configure.py receipt.py report.py rigmark
```

## Licence

MIT
