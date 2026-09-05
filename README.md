# LLM appliance bench

A reproducible stress test for OpenAI-compatible LLM appliances. It compares
realistic code and prose decode, an explicitly labelled structured-output
ceiling, exact cold/warm prefill, and concurrent service behaviour.

It is deliberately model-agnostic: use it with Qwen, GLM, DeepSeek, vLLM,
SGLang, local GPU servers, or multi-node DGX Spark recipes. A different model or
serving stack is an appliance comparison; identical weights and software are
required before claiming a topology-only speed-up.

## Run the standard suite

Python 3.10 or newer is required; there are no third-party packages.

```bash
git clone https://github.com/alexellis/llm-appliance-bench
cd llm-appliance-bench
cp metadata.example.json metadata.json

python3 bench.py \
  --base-url http://SERVER:8000 \
  --model auto \
  --label my-appliance \
  --comparison-id weekend-sweep-1 \
  --metadata metadata.json \
  --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}'
```

Start by copying [`metadata.example.json`](metadata.example.json) and record the
hardware and complete serving recipe. Use the same comparison ID for every
appliance in one A/B sweep. This makes every generated prompt byte-for-byte
identical; use a new ID for the next sweep.

The default suite performs:

- five 512-token runs of code, prose, and structured JSON;
- three cold/immediate-warm pairs at 8,192, 32,768, and 65,536 tokens; and
- three rounds of code at concurrency 1, 2, and 4 with 256-token outputs.

Results are written to `results/LABEL-TIMESTAMP.json`. Neither the endpoint URL
nor API credentials are written to the result. Credentials are read from
`OPENAI_API_KEY` by default; use `--api-key-env NAME` to select another
environment variable. Visible generated output is retained for auditability;
reasoning text is not retained, although its size and hash are recorded.

For an engine without vLLM's `/tokenize` extension or token-ID completion
input, add `--skip-prefill`. To omit load testing, add `--skip-concurrency`.

## Compare two results

```bash
python3 compare.py results/recipe-a.json results/recipe-b.json
```

The comparison stops when the protocol, prompt corpus, thinking/request body,
run counts, output lengths, prefill depths/runs, or concurrency settings differ.
`--allow-mismatch` exists for exploratory comparisons and prints the mismatches.

## Fair-use checklist

- Run against a quiet endpoint and disclose any competing traffic.
- Pin and publish model, drafter, engine/image, and benchmark revisions.
- Publish the complete result JSON and command, not only a screenshot.
- Check the retained outputs; throughput alone is not a quality score.
- Headline code and prose medians with their ranges—not a best run.
- Label structured output as a speculative-decoding ceiling.
- Report cold and warm prefill separately.
- Verify the negotiated fabric rate rather than copying a product headline.

The exact measurement definitions and claim boundaries are in
[`PROTOCOL.md`](PROTOCOL.md).

## Development

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile bench.py compare.py
```

## Licence

MIT
