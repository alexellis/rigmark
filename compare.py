#!/usr/bin/env python3
"""Compare two llm-appliance-bench result files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def nested(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = value[key]
    return value


def comparable(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    paths = (
        ("protocol", "version"),
        ("protocol", "prompts_sha256"),
        ("run", "comparison_id"),
        ("settings", "runs"),
        ("settings", "decode_tokens"),
        ("settings", "temperature"),
        ("settings", "top_p"),
        ("settings", "extra_body"),
        ("settings", "prefill_depths"),
        ("settings", "prefill_runs"),
        ("settings", "concurrency"),
        ("settings", "concurrency_runs"),
        ("settings", "concurrency_tokens"),
        ("settings", "concurrency_workload"),
    )
    return [
        ".".join(path)
        for path in paths
        if nested(left, *path) != nested(right, *path)
    ]


def summary(
    result: dict[str, Any], path: tuple[str, ...]
) -> dict[str, float] | None:
    try:
        candidate = nested(result, *path)
        return {
            key: float(candidate[key])
            for key in ("median", "minimum", "maximum")
        }
    except (KeyError, TypeError, ValueError):
        return None


def format_summary(
    numbers: dict[str, float] | None, precision: int = 1
) -> str:
    if numbers is None:
        return "—"
    return (
        f"{numbers['median']:,.{precision}f} "
        f"[{numbers['minimum']:,.{precision}f}–"
        f"{numbers['maximum']:,.{precision}f}]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--allow-mismatch", action="store_true")
    args = parser.parse_args()

    left = json.loads(args.left.read_text())
    right = json.loads(args.right.read_text())
    mismatches = comparable(left, right)
    if mismatches and not args.allow_mismatch:
        parser.error(
            "results use different protocols/settings: " + ", ".join(mismatches)
        )

    left_label = left["run"]["label"]
    right_label = right["run"]["label"]
    metrics: list[tuple[str, tuple[str, ...]]] = []
    for workload in ("code", "prose", "structured"):
        metrics.extend((
            (
                f"{workload.title()} decode, tok/s",
                ("decode", workload, "decode_tokens_per_second"),
            ),
            (
                f"{workload.title()} TTFT, seconds ↓",
                ("decode", workload, "ttft_seconds"),
            ),
        ))
    for depth in left.get("settings", {}).get("prefill_depths", []):
        metrics.extend((
            (
                f"Cold prefill {depth:,}, tok/s",
                ("prefill", str(depth), "cold", "effective_prefill_tokens_per_second"),
            ),
            (
                f"Warm replay {depth:,}, tok/s",
                ("prefill", str(depth), "warm_replay", "effective_prefill_tokens_per_second"),
            ),
            (
                f"Cold prefill {depth:,} TTFT, seconds ↓",
                ("prefill", str(depth), "cold", "ttft_seconds"),
            ),
        ))
    for level in left.get("settings", {}).get("concurrency", []):
        metrics.extend((
            (
                f"C{level} short code-load end-to-end tok/s",
                ("concurrency", str(level), "aggregate_end_to_end_tokens_per_second"),
            ),
            (
                f"C{level} per-stream TTFT, seconds ↓",
                ("concurrency", str(level), "per_stream_ttft_seconds"),
            ),
        ))

    print(f"| Measurement | {left_label} | {right_label} | Right/left |")
    print("|---|---:|---:|---:|")
    for label, path in metrics:
        lhs = summary(left, path)
        rhs = summary(right, path)
        precision = 3 if "seconds" in label else 1
        ratio = (
            None
            if lhs is None or rhs is None or lhs["median"] == 0
            else rhs["median"] / lhs["median"]
        )
        ratio_text = "—" if ratio is None else f"{ratio:.2f}×"
        print(
            f"| {label} | {format_summary(lhs, precision)} | "
            f"{format_summary(rhs, precision)} | {ratio_text} |"
        )

    print("\n| Completion gate | " + left_label + " | " + right_label + " |")
    print("|---|---:|---:|")
    for workload in ("code", "prose", "structured"):
        left_gate = nested(left, "decode", workload, "completion_gate")
        right_gate = nested(right, "decode", workload, "completion_gate")
        print(
            f"| {workload.title()} | "
            f"{left_gate['passed']}/{left_gate['total']} | "
            f"{right_gate['passed']}/{right_gate['total']} |"
        )

    if left["run"].get("model") != right["run"].get("model"):
        print("\nWarning: model IDs differ; this is an appliance comparison, not a topology-only comparison.")
    if mismatches:
        print("\nWarning: comparison forced despite mismatches: " + ", ".join(mismatches))


if __name__ == "__main__":
    main()
