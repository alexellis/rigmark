#!/usr/bin/env python3
"""Interactively create public-safe appliance metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = (
    ("hardware", "Exact accelerator model, memory, and count"),
    ("topology", "TP/PP size and physical or network topology"),
    ("negotiated_link_speed", "Measured live link rate, or not applicable"),
    ("model", "Published model ID or local checkpoint name"),
    ("model_revision", "Immutable model commit, digest, or local fingerprint"),
    ("quantisation", "Weight and activation formats"),
    ("kv_cache_dtype", "Actual KV cache format"),
    ("serving_engine", "Engine name and exact version or commit"),
    ("serving_image", "Immutable image digest, or not applicable"),
    ("drafter", "Speculative method, depth, sampling, or none"),
    ("context_limit", "Configured maximum context in tokens"),
    ("scheduler", "Max sequences, batched tokens, and material flags"),
    ("competing_traffic", "None after checking, or every co-tenant"),
)


def positive_integer(value: str) -> int:
    """Parse a positive integer, giving the caller a useful validation error."""
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError("enter a whole number, for example 262144") from error
    if parsed < 1:
        raise ValueError("enter a number greater than zero")
    return parsed


def prompt_metadata() -> dict[str, object]:
    print("LLM appliance metadata")
    print("Do not enter credentials, private URLs, usernames, or home paths.\n")
    result: dict[str, object] = {}
    for key, help_text in FIELDS:
        while True:
            value = input(f"{key}\n  {help_text}\n> ").strip()
            if value:
                break
            print("  A value is required.")
        if key == "context_limit":
            while True:
                try:
                    result[key] = positive_integer(value)
                    break
                except ValueError as error:
                    print(f"  {error}.")
                    value = input("> ").strip()
        else:
            result[key] = value
        print()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("metadata.json"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        parser.error(f"{args.output} already exists; use --force to replace it")
    metadata = prompt_metadata()
    args.output.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Wrote {args.output}. Review it, then run bench.py.")


if __name__ == "__main__":
    main()
