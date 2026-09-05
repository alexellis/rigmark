#!/usr/bin/env python3
"""Reproducible appliance benchmark for OpenAI-compatible LLM servers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent


def normalise_base_url(value: str) -> str:
    value = value.rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3]
    return value


def validate_base_url(value: str) -> str:
    value = normalise_base_url(value)
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("base URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("put credentials in the API-key environment variable, not the URL")
    return value


def safe_label(value: str) -> str:
    rendered = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    if not rendered:
        raise ValueError("label must contain a letter or number")
    return rendered


def nonce(comparison_id: str, *parts: object) -> str:
    source = ":".join((PROTOCOL_VERSION, comparison_id, *(str(part) for part in parts)))
    return hashlib.sha256(source.encode()).hexdigest()[:32]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a percentile of no values")
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


class Client:
    def __init__(self, base_url: str, api_key: str, timeout: float):
        self.base_url = validate_base_url(base_url)
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def json(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=self._headers(),
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def stream(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers=self._headers(),
        )
        started = time.monotonic()
        first = None
        last = None
        usage: dict[str, Any] = {}
        finish_reason = None
        measured_chunks: list[str] = []
        output_chunks: list[str] = []
        reasoning_chunks: list[str] = []

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                encoded = line[5:].strip()
                if encoded == "[DONE]":
                    break
                event = json.loads(encoded)
                if isinstance(event.get("usage"), dict):
                    usage = event["usage"]
                choices = event.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
                delta = choice.get("delta") or {}
                reasoning = "".join(
                    value
                    for key in ("reasoning", "reasoning_content")
                    if isinstance((value := delta.get(key)), str) and value
                )
                content = delta.get("content")
                if not isinstance(content, str):
                    content = ""
                if not content and isinstance(choice.get("text"), str):
                    content = choice["text"]
                measured = reasoning + content
                if measured:
                    now = time.monotonic()
                    first = first or now
                    last = now
                    measured_chunks.append(measured)
                    reasoning_chunks.append(reasoning)
                    output_chunks.append(content)

        finished = time.monotonic()
        if first is None or last is None:
            raise RuntimeError("stream emitted no measurable output")
        if "completion_tokens" not in usage or "prompt_tokens" not in usage:
            raise RuntimeError("server did not return final token usage")

        completion = int(usage["completion_tokens"])
        prompt = int(usage["prompt_tokens"])
        decode_window = max(last - first, 1e-9)
        rendered = "".join(measured_chunks)
        output = "".join(output_chunks)
        reasoning = "".join(reasoning_chunks)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "ttft_seconds": round(first - started, 6),
            "decode_seconds": round(decode_window, 6),
            "decode_tokens_per_second": round(max(completion - 1, 0) / decode_window, 3),
            "wall_seconds": round(finished - started, 6),
            "finish_reason": finish_reason,
            "output": output,
            "output_characters": len(output),
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "reasoning_characters": len(reasoning),
            "reasoning_sha256": hashlib.sha256(reasoning.encode()).hexdigest(),
            "stream_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
        }


def load_prompts(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def git_identity() -> dict[str, Any]:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=HERE, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=HERE,
            stderr=subprocess.DEVNULL,
        )
        identity: dict[str, Any] = {
            "repository_revision": revision,
            "repository_dirty": bool(status),
        }
        if status:
            diff = subprocess.check_output(
                ["git", "diff", "--binary", "HEAD"],
                cwd=HERE,
                stderr=subprocess.DEVNULL,
            )
            identity["repository_worktree_sha256"] = hashlib.sha256(
                status + b"\0" + diff
            ).hexdigest()
        return identity
    except (OSError, subprocess.CalledProcessError):
        return {
            "repository_revision": "unknown",
            "repository_dirty": None,
        }


def summarise(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row[key]) for row in rows]
    return {
        "median": round(statistics.median(values), 3),
        "minimum": round(min(values), 3),
        "maximum": round(max(values), 3),
        "p90": round(percentile(values, 0.9), 3),
    }


def build_chat_payload(
    model: str,
    system: str,
    prompt: str,
    max_tokens: int,
    seed: int,
    extra_body: dict[str, Any],
) -> dict[str, Any]:
    protected = {
        "model", "messages", "temperature", "top_p", "seed", "max_tokens",
        "stream", "stream_options",
    }
    conflicts = sorted(protected.intersection(extra_body))
    if conflicts:
        raise ValueError(
            "--extra-body cannot override fixed fields: " + ", ".join(conflicts)
        )
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": seed,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
    }
    payload.update(extra_body)
    return payload


def run_decode(
    client: Client,
    model: str,
    prompts: dict[str, Any],
    runs: int,
    max_tokens: int,
    seed: int,
    extra_body: dict[str, Any],
    comparison_id: str,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, prompt in prompts["workloads"].items():
        rows = []
        print(f"decode/{name}: {runs} runs", flush=True)
        for index in range(runs):
            request_nonce = nonce(comparison_id, "decode", name, index + 1)
            payload = build_chat_payload(
                model,
                prompts["system"],
                f"Request nonce: {request_nonce}\n\n{prompt}",
                max_tokens,
                seed,
                extra_body,
            )
            row = client.stream("/v1/chat/completions", payload)
            row["run"] = index + 1
            if name == "structured":
                row["completion_validation"] = validate_structured_output(
                    row["output"]
                )
            else:
                row["completion_validation"] = validate_visible_output(row)
            rows.append(row)
            print(
                f"  {index + 1}: {row['decode_tokens_per_second']:.1f} tok/s, "
                f"TTFT {row['ttft_seconds']:.3f}s, "
                f"{row['completion_tokens']} tokens",
                flush=True,
            )
        output[name] = {
            "runs": rows,
            "decode_tokens_per_second": summarise(rows, "decode_tokens_per_second"),
            "ttft_seconds": summarise(rows, "ttft_seconds"),
            "completion_gate": {
                "passed": sum(
                    1 for row in rows if row["completion_validation"]["valid"]
                ),
                "total": len(rows),
            },
        }
    return output


def validate_structured_output(output: str) -> dict[str, Any]:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as error:
        return {"valid": False, "error": f"invalid JSON: {error.msg}"}
    if not isinstance(value, list) or len(value) != 50:
        return {"valid": False, "error": "expected an array of 50 objects"}
    for index, item in enumerate(value, start=1):
        if item != {"index": index, "square": index * index}:
            return {"valid": False, "error": f"incorrect object at index {index}"}
    return {"valid": True}


def validate_visible_output(row: dict[str, Any]) -> dict[str, Any]:
    if not row.get("output", "").strip():
        return {"valid": False, "error": "no visible answer"}
    if row.get("finish_reason") == "length":
        return {"valid": False, "error": "answer hit the token limit"}
    return {"valid": True}


def exact_token_ids(
    client: Client,
    model: str,
    target: int,
    unit: str,
    request_nonce: str,
) -> list[int]:
    prefix_body = client.json(
        "/tokenize",
        {
            "model": model,
            "prompt": f"Unique cold-prefill nonce {request_nonce}.\n",
            "add_special_tokens": False,
        },
    )
    unit_body = client.json(
        "/tokenize",
        {"model": model, "prompt": unit, "add_special_tokens": False},
    )
    prefix_tokens = [int(token) for token in (prefix_body.get("tokens") or [])]
    unit_tokens = [int(token) for token in (unit_body.get("tokens") or [])]
    if not prefix_tokens or not unit_tokens:
        raise RuntimeError("tokenizer returned an empty prefix or prefill unit")
    tokens = prefix_tokens[:target]
    while len(tokens) < target:
        tokens.extend(unit_tokens[:target - len(tokens)])
    return tokens


def prefill_once(client: Client, model: str, tokens: list[int]) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": tokens,
        "add_special_tokens": False,
        "max_tokens": 8,
        "ignore_eos": True,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
    }
    row = client.stream("/v1/completions", payload)
    row["effective_prefill_tokens_per_second"] = round(
        row["prompt_tokens"] / max(row["ttft_seconds"], 1e-9), 3
    )
    return row


def run_prefill(
    client: Client,
    model: str,
    prompts: dict[str, Any],
    depths: list[int],
    runs: int,
    comparison_id: str,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for depth in depths:
        print(f"prefill/{depth}: {runs} cold/immediate-replay pairs", flush=True)
        cold_rows = []
        warm_rows = []
        for index in range(runs):
            tokens = exact_token_ids(
                client,
                model,
                depth,
                prompts["prefill_unit"],
                nonce(comparison_id, "prefill", depth, index + 1),
            )
            cold = prefill_once(client, model, tokens)
            warm = prefill_once(client, model, tokens)
            cold["run"] = index + 1
            warm["run"] = index + 1
            cold_rows.append(cold)
            warm_rows.append(warm)
            print(
                f"  {index + 1}: cold "
                f"{cold['effective_prefill_tokens_per_second']:.1f} tok/s "
                f"({cold['ttft_seconds']:.3f}s), warm "
                f"{warm['effective_prefill_tokens_per_second']:.1f} tok/s "
                f"({warm['ttft_seconds']:.3f}s)",
                flush=True,
            )
        output[str(depth)] = {
            "cold": {
                "runs": cold_rows,
                "effective_prefill_tokens_per_second": summarise(
                    cold_rows, "effective_prefill_tokens_per_second"
                ),
                "ttft_seconds": summarise(cold_rows, "ttft_seconds"),
            },
            "warm_replay": {
                "runs": warm_rows,
                "effective_prefill_tokens_per_second": summarise(
                    warm_rows, "effective_prefill_tokens_per_second"
                ),
                "ttft_seconds": summarise(warm_rows, "ttft_seconds"),
            },
        }
    return output


def run_concurrency(
    client: Client,
    model: str,
    prompts: dict[str, Any],
    levels: list[int],
    rounds: int,
    max_tokens: int,
    seed: int,
    extra_body: dict[str, Any],
    workload: str,
    comparison_id: str,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    prompt = prompts["workloads"][workload]
    for level in levels:
        print(f"concurrency/{level}: {rounds} rounds of {workload}", flush=True)
        round_rows = []
        all_streams = []
        for round_index in range(rounds):
            barrier = threading.Barrier(level)

            def invoke(stream_index: int) -> dict[str, Any]:
                request_nonce = nonce(
                    comparison_id,
                    "concurrency",
                    workload,
                    level,
                    round_index + 1,
                    stream_index + 1,
                )
                payload = build_chat_payload(
                    model,
                    prompts["system"],
                    f"Request nonce: {request_nonce}\n\n{prompt}",
                    max_tokens,
                    seed + stream_index,
                    extra_body,
                )
                barrier.wait()
                return client.stream("/v1/chat/completions", payload)

            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=level) as executor:
                streams = list(executor.map(invoke, range(level)))
            wall = time.monotonic() - started
            completion = sum(row["completion_tokens"] for row in streams)
            aggregate = completion / max(wall, 1e-9)
            round_row = {
                "round": round_index + 1,
                "wall_seconds": round(wall, 6),
                "completion_tokens": completion,
                "aggregate_end_to_end_tokens_per_second": round(aggregate, 3),
                "streams": streams,
            }
            round_rows.append(round_row)
            all_streams.extend(streams)
            print(
                f"  {round_index + 1}: aggregate {aggregate:.1f} tok/s, "
                f"median stream {statistics.median(row['decode_tokens_per_second'] for row in streams):.1f} tok/s",
                flush=True,
            )
        output[str(level)] = {
            "rounds": round_rows,
            "aggregate_end_to_end_tokens_per_second": summarise(
                round_rows, "aggregate_end_to_end_tokens_per_second"
            ),
            "per_stream_decode_tokens_per_second": summarise(
                all_streams, "decode_tokens_per_second"
            ),
            "per_stream_ttft_seconds": summarise(all_streams, "ttft_seconds"),
        }
    return output


def comma_ints(value: str) -> list[int]:
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result or any(item < 1 for item in result):
        raise argparse.ArgumentTypeError("expected positive comma-separated integers")
    return result


def write_result(result: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"result: {output}", flush=True)


def load_metadata(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not value:
        raise ValueError("metadata must be a non-empty JSON object")
    required = {
        "hardware", "topology", "model", "model_revision", "quantisation",
        "kv_cache_dtype", "serving_engine", "context_limit",
        "competing_traffic",
    }
    missing = sorted(required.difference(value))
    if missing:
        raise ValueError("metadata is missing required fields: " + ", ".join(missing))

    def contains_placeholder(item: Any) -> bool:
        if isinstance(item, str):
            return "CHANGE ME" in item.upper()
        if isinstance(item, dict):
            return any(contains_placeholder(child) for child in item.values())
        if isinstance(item, list):
            return any(contains_placeholder(child) for child in item)
        return False

    if contains_placeholder(value):
        raise ValueError(
            "metadata still contains CHANGE ME placeholders; run configure.py"
        )
    context_limit = value["context_limit"]
    if isinstance(context_limit, bool) or not isinstance(context_limit, int):
        raise ValueError("metadata context_limit must be a whole number")
    if context_limit < 1:
        raise ValueError("metadata context_limit must be greater than zero")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--model", default="auto")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--decode-tokens", type=int, default=4096)
    parser.add_argument("--prefill-depths", type=comma_ints, default=comma_ints("8192,32768,65536"))
    parser.add_argument("--prefill-runs", type=int, default=3)
    parser.add_argument("--concurrency", type=comma_ints, default=comma_ints("1,2,4"))
    parser.add_argument("--concurrency-runs", type=int, default=3)
    parser.add_argument("--concurrency-tokens", type=int, default=256)
    parser.add_argument("--concurrency-workload", choices=("code", "prose"), default="code")
    parser.add_argument("--extra-body", default="{}", help="JSON merged into every chat request")
    parser.add_argument("--skip-prefill", action="store_true")
    parser.add_argument("--skip-concurrency", action="store_true")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260905)
    args = parser.parse_args()

    if args.runs < 1 or args.prefill_runs < 1 or args.concurrency_runs < 1:
        parser.error("run counts must be positive")
    try:
        base_url = validate_base_url(args.base_url)
        filename_label = safe_label(args.label)
        metadata = load_metadata(args.metadata)
        extra_body = json.loads(args.extra_body)
    except (json.JSONDecodeError, OSError, ValueError) as error:
        parser.error(str(error))
    if not isinstance(extra_body, dict):
        parser.error("--extra-body must be a JSON object")

    api_key = os.environ.get(args.api_key_env, "")
    client = Client(base_url, api_key, args.timeout)
    prompts, prompts_sha256 = load_prompts(HERE / "prompts.json")
    model = args.model
    if model == "auto":
        models = client.json("/v1/models").get("data") or []
        if len(models) != 1:
            parser.error("--model auto requires the endpoint to advertise exactly one model")
        model = str(models[0]["id"])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path("results") / f"{filename_label}-{timestamp}.json"
    repository = git_identity()
    result: dict[str, Any] = {
        "schema": 1,
        "protocol": {
            "version": PROTOCOL_VERSION,
            **repository,
            "prompts_version": prompts["version"],
            "prompts_sha256": prompts_sha256,
        },
        "run": {
            "label": args.label,
            "comparison_id": args.comparison_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "appliance": metadata,
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "settings": {
            "runs": args.runs,
            "decode_tokens": args.decode_tokens,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": args.seed,
            "extra_body": extra_body,
            "prefill_depths": [] if args.skip_prefill else args.prefill_depths,
            "prefill_runs": args.prefill_runs,
            "concurrency": [] if args.skip_concurrency else args.concurrency,
            "concurrency_runs": args.concurrency_runs,
            "concurrency_tokens": args.concurrency_tokens,
            "concurrency_workload": args.concurrency_workload,
        },
    }

    try:
        result["decode"] = run_decode(
            client,
            model,
            prompts,
            args.runs,
            args.decode_tokens,
            args.seed,
            extra_body,
            args.comparison_id,
        )
        if not args.skip_prefill:
            result["prefill"] = run_prefill(
                client,
                model,
                prompts,
                args.prefill_depths,
                args.prefill_runs,
                args.comparison_id,
            )
        if not args.skip_concurrency:
            result["concurrency"] = run_concurrency(
                client,
                model,
                prompts,
                args.concurrency,
                args.concurrency_runs,
                args.concurrency_tokens,
                args.seed,
                extra_body,
                args.concurrency_workload,
                args.comparison_id,
            )
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as error:
        result["error"] = str(error)
        write_result(result, output)
        raise

    result["run"]["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_result(result, output)
    try:
        from report import print_report

        print()
        print_report(result, output)
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f"warning: could not render terminal report: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
