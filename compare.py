#!/usr/bin/env python3
"""Compare two llm-appliance-bench result files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

from receipt import validate_result


CARD_WIDTH = 104
MISSING = object()


def depth_label(depth: int) -> str:
    if depth >= 1_024 and depth % 1_024 == 0:
        return f"{depth // 1_024}K"
    return f"{depth:,} TOKENS"


def nested(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = value[key]
    return value


def comparable_value(value: dict[str, Any], path: tuple[str, ...]) -> Any:
    try:
        return nested(value, *path)
    except (KeyError, TypeError):
        return MISSING


def comparable(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    paths = (
        ("protocol", "version"),
        ("protocol", "prompts_sha256"),
        ("protocol", "repository_revision"),
        ("protocol", "repository_dirty"),
        ("run", "comparison_id"),
        ("settings", "runs"),
        ("settings", "decode_tokens"),
        ("settings", "temperature"),
        ("settings", "top_p"),
        ("settings", "seed"),
        ("settings", "extra_body"),
        ("settings", "prefill_depths"),
        ("settings", "prefill_runs"),
        ("settings", "concurrency"),
        ("settings", "concurrency_runs"),
        ("settings", "concurrency_tokens"),
        ("settings", "concurrency_workload"),
    )
    mismatches = [f"left receipt: {error}" for error in validate_result(left)]
    mismatches.extend(f"right receipt: {error}" for error in validate_result(right))
    for path in paths:
        left_value = comparable_value(left, path)
        right_value = comparable_value(right, path)
        if (
            left_value is MISSING
            or right_value is MISSING
            or left_value != right_value
        ):
            mismatches.append(".".join(path))
    if (
        comparable_value(left, ("protocol", "repository_dirty")) is True
        and comparable_value(right, ("protocol", "repository_dirty")) is True
    ):
        path = ("protocol", "repository_worktree_sha256")
        left_value = comparable_value(left, path)
        right_value = comparable_value(right, path)
        if (
            left_value is MISSING
            or right_value is MISSING
            or left_value != right_value
        ):
            mismatches.append(".".join(path))
    path = ("protocol", "repository_source_sha256")
    left_value = comparable_value(left, path)
    right_value = comparable_value(right, path)
    if not (left_value is MISSING and right_value is MISSING) and (
        left_value is MISSING
        or right_value is MISSING
        or left_value != right_value
    ):
        mismatches.append(".".join(path))
    return mismatches


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
        if (
            len(path) == 3
            and path[0] == "decode"
            and path[2] in ("time_to_last_output_seconds", "wall_seconds")
        ):
            try:
                rows = nested(result, "decode", path[1], "runs")
                if path[2] == "time_to_last_output_seconds":
                    values = [
                        float(
                            row.get(
                                "time_to_last_output_seconds",
                                row["ttft_seconds"] + row["decode_seconds"],
                            )
                        )
                        for row in rows
                    ]
                else:
                    values = [float(row["wall_seconds"]) for row in rows]
                return {
                    "median": statistics.median(values),
                    "minimum": min(values),
                    "maximum": max(values),
                }
            except (KeyError, TypeError, ValueError):
                pass
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


def card_line(value: object = "") -> str:
    text = str(value)
    if len(text) > CARD_WIDTH - 4:
        text = text[: CARD_WIDTH - 5] + "…"
    return "║ " + text.ljust(CARD_WIDTH - 4) + " ║"


def card_rule(left: str, middle: str, right: str) -> str:
    return left + middle * (CARD_WIDTH - 2) + right


def completion_count(result: dict[str, Any]) -> tuple[int, int]:
    gates = [
        result["decode"][workload]["completion_gate"]
        for workload in ("code", "prose", "structured")
    ]
    return sum(gate["passed"] for gate in gates), sum(gate["total"] for gate in gates)


def benchmark_identity(result: dict[str, Any]) -> str:
    protocol = result.get("protocol", {})
    revision = str(protocol.get("repository_revision", "unknown"))[:12]
    dirty = protocol.get("repository_dirty")
    state = "clean" if dirty is False else "dirty" if dirty is True else "unknown"
    identity = f"git:{revision} {state}"
    if dirty is True:
        worktree = str(protocol.get("repository_worktree_sha256", "unknown"))[:12]
        identity += f" worktree:{worktree}"
    return identity


def card_metric(
    label: str,
    left: dict[str, Any],
    right: dict[str, Any],
    path: tuple[str, ...],
) -> str:
    lhs = summary(left, path)
    rhs = summary(right, path)
    if lhs is None or rhs is None:
        return f"{label:<24} {'N/A':>18}  {'N/A':>18}  {'—':>12}"
    ratio = rhs["median"] / lhs["median"] if lhs["median"] else 0
    return (
        f"{label:<24} {lhs['median']:>14,.1f}  "
        f"{rhs['median']:>18,.1f}  {ratio:>11.2f}×"
    )


def render_card(
    left: dict[str, Any],
    right: dict[str, Any],
    left_hash: str,
    right_hash: str,
) -> str:
    errors = validate_result(left) + validate_result(right)
    if errors:
        raise ValueError("invalid receipt: " + "; ".join(errors))
    left_label = str(left["run"]["label"])
    right_label = str(right["run"]["label"])
    left_gate = completion_count(left)
    right_gate = completion_count(right)
    depths = set(left.get("settings", {}).get("prefill_depths", []))
    depth = max(depths) if depths else None
    levels = set(left.get("settings", {}).get("concurrency", []))
    level = max(levels) if levels else None
    lines = [
        card_rule("╔", "═", "╗"),
        card_line("R I G M A R K  //  MATCHED REQUEST A/B  //  REAL OUTPUT. RECEIPTS INCLUDED."),
        card_line("SAME PROTOCOL • PROMPTS • REQUEST BODY • GENERATION LIMITS"),
        card_line("TOK/S RATIOS REQUIRE MATCHING SERVER-SIDE TOKEN DEFINITIONS"),
        card_rule("╠", "═", "╣"),
        card_line(f"LEFT   {left_label}"),
        card_line(f"RIGHT  {right_label}"),
        card_line(f"BENCH  left {benchmark_identity(left)}"),
        card_line(f"       right {benchmark_identity(right)}"),
        card_rule("╠", "═", "╣"),
        card_line(f"{'METRIC':<24} {'LEFT':>14}  {'RIGHT':>18}  {'RIGHT/LEFT':>12}"),
        card_line(card_metric(
            "CODE DECODE EST.", left, right,
            ("decode", "code", "decode_tokens_per_second"),
        )),
        card_line(card_metric(
            "CODE LAST OUTPUT, SEC ↓", left, right,
            ("decode", "code", "time_to_last_output_seconds"),
        )),
        card_line(card_metric(
            "PROSE DECODE EST.", left, right,
            ("decode", "prose", "decode_tokens_per_second"),
        )),
        card_line(card_metric(
            "PROSE LAST OUTPUT, SEC ↓", left, right,
            ("decode", "prose", "time_to_last_output_seconds"),
        )),
        card_line(card_metric(
            "STRUCTURED CEILING", left, right,
            ("decode", "structured", "decode_tokens_per_second"),
        )),
    ]
    if depth is not None:
        label = depth_label(depth)
        lines.extend((
            card_line(card_metric(
                f"{label} COLD PREFILL", left, right,
                ("prefill", str(depth), "cold",
                 "effective_prefill_tokens_per_second"),
            )),
            card_line(card_metric(
                f"{label} IMMEDIATE REPLAY", left, right,
                ("prefill", str(depth), "warm_replay",
                 "effective_prefill_tokens_per_second"),
            )),
        ))
    if level is not None:
        workload = str(
            left.get("settings", {}).get("concurrency_workload", "unknown")
        ).upper()
        lines.append(card_line(card_metric(
            f"C{level} CAPPED {workload} LOAD",
            left,
            right,
            ("concurrency", str(level), "aggregate_end_to_end_tokens_per_second"),
        )))
    lines.extend((
        card_rule("╠", "═", "╣"),
        card_line(
            f"BASIC GATES  left {left_gate[0]}/{left_gate[1]}  •  "
            f"right {right_gate[0]}/{right_gate[1]}"
        ),
        card_line(f"RECEIPTS  {left_hash[:16]}…  •  {right_hash[:16]}…"),
        card_line("SCREENSHOT → POST TO X • LINK BOTH JSON RECEIPTS • #RigMark"),
        card_line("github.com/alexellis/rigmark"),
        card_rule("╚", "═", "╝"),
    ))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--allow-mismatch", action="store_true")
    parser.add_argument("--card", action="store_true", help="print a shareable matched A/B card")
    args = parser.parse_args()

    left = json.loads(args.left.read_text())
    right = json.loads(args.right.read_text())
    receipt_errors = [
        *(f"left: {error}" for error in validate_result(left)),
        *(f"right: {error}" for error in validate_result(right)),
    ]
    if receipt_errors:
        parser.error("invalid receipt: " + "; ".join(receipt_errors))
    mismatches = comparable(left, right)
    if mismatches and not args.allow_mismatch:
        parser.error(
            "results use different protocols/settings: " + ", ".join(mismatches)
        )

    if args.card:
        if mismatches:
            parser.error("a share card requires matched results; remove --allow-mismatch")
        left_hash = hashlib.sha256(args.left.read_bytes()).hexdigest()
        right_hash = hashlib.sha256(args.right.read_bytes()).hexdigest()
        card = render_card(left, right, left_hash, right_hash)
        if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
            from report import colourise

            card = colourise(card)
        print(card)
        return

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
            (
                f"{workload.title()} last output, seconds ↓",
                ("decode", workload, "time_to_last_output_seconds"),
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

    print("\n| Basic output gate | " + left_label + " | " + right_label + " |")
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
        print(
            "\nWarning: model IDs differ; this is an appliance comparison, "
            "not a topology-only comparison."
        )
    if mismatches:
        print("\nWarning: comparison forced despite mismatches: " + ", ".join(mismatches))
    print("\nBenchmark identity:")
    print(f"- {left_label}: {benchmark_identity(left)}")
    print(f"- {right_label}: {benchmark_identity(right)}")


if __name__ == "__main__":
    main()
