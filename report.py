#!/usr/bin/env python3
"""Render an auditable terminal card from an appliance benchmark result."""

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


WIDTH = 92


def depth_label(depth: int) -> str:
    if depth >= 1_024 and depth % 1_024 == 0:
        return f"{depth // 1_024}K"
    return f"{depth:,} TOKENS"


def clipped(value: object, width: int) -> str:
    text = str(value)
    return text if len(text) <= width else text[: width - 1] + "…"


def line(value: object = "") -> str:
    return "│  " + clipped(value, WIDTH - 4).ljust(WIDTH - 4) + "│"


def rule(left: str, middle: str, right: str) -> str:
    return left + middle * (WIDTH - 2) + right


def section(title: str) -> str:
    prefix = f"├─ {title} "
    return prefix + "─" * (WIDTH - len(prefix) - 1) + "┤"


def metric(result: dict[str, Any], workload: str) -> str:
    data = result["decode"][workload]
    speed = data["decode_tokens_per_second"]
    gate = data["completion_gate"]
    mark = "✓" if gate["passed"] == gate["total"] else "✗"
    label = "STRUCTURED*" if workload == "structured" else workload.upper()
    last_output = data.get("time_to_last_output_seconds")
    if not isinstance(last_output, dict):
        values = [
            float(row["ttft_seconds"]) + float(row["decode_seconds"])
            for row in data["runs"]
        ]
        last_output = {"median": statistics.median(values)}
    return (
        f"{label:<14} {speed['median']:>7.1f} tok/s"
        f"   {last_output['median']:>7.1f}s last"
        f"   {speed['minimum']:>6.1f}–{speed['maximum']:<6.1f}"
        f"   {mark} {gate['passed']}/{gate['total']}"
    )


def benchmark_identity(result: dict[str, Any]) -> str:
    protocol = result.get("protocol", {})
    revision = str(protocol.get("repository_revision", "unknown"))
    dirty = protocol.get("repository_dirty")
    state = "clean" if dirty is False else "dirty" if dirty is True else "state unknown"
    value = f"SOURCE     git:{revision[:12]}  •  {state}"
    if dirty is True:
        fingerprint = str(protocol.get("repository_worktree_sha256", "unknown"))
        value += f"  •  worktree:{fingerprint[:12]}"
    return value


def render(result: dict[str, Any], fingerprint: str) -> str:
    errors = validate_result(result)
    if errors:
        raise ValueError("invalid receipt: " + "; ".join(errors))
    run = result["run"]
    settings = result["settings"]
    appliance = run["appliance"]
    gates = [
        result["decode"][name]["completion_gate"]
        for name in ("code", "prose", "structured")
    ]
    passed = sum(gate["passed"] for gate in gates)
    total = sum(gate["total"] for gate in gates)
    complete = passed == total
    effort = (
        settings.get("extra_body", {})
        .get("chat_template_kwargs", {})
        .get("reasoning_effort", "unspecified")
    )
    lines = [
        rule("╭", "─", "╮"),
        line("R I G M A R K   //   AGENT WORKLOAD RECEIPT"),
        line("BENCHMARKS LOCAL AI HOW CODING AGENTS ACTUALLY USE IT"),
        line(
            f"●  {passed}/{total} BASIC OUTPUT GATES PASSED"
            if complete else
            f"▲  {passed}/{total} BASIC OUTPUT GATES PASSED — DO NOT HEADLINE"
        ),
        section("SYSTEM"),
        line(f"MODEL      {run['model']}"),
        line(f"APPLIANCE  {appliance.get('hardware', 'unspecified')}"),
        line(f"RUN        reasoning={effort}  •  protocol={result['protocol']['version']}"),
        line(benchmark_identity(result)),
        section("REAL OUTPUT"),
        line("WORKLOAD       DECODE EST.      LAST OUTPUT          RANGE          BASIC GATE"),
        line(metric(result, "code")),
        line(metric(result, "prose")),
        line(metric(result, "structured")),
        line("* predictable-output ceiling; not a proxy for agent speed"),
    ]
    depths = settings.get("prefill_depths", [])
    if depths:
        depth = max(depths)
        data = result["prefill"][str(depth)]
        cold = data["cold"]["effective_prefill_tokens_per_second"]["median"]
        warm = data["warm_replay"]["effective_prefill_tokens_per_second"]["median"]
        lines.extend((
            section("CONTEXT"),
            line(
                f"{depth_label(depth)} PREFILL   cold {cold:,.0f} tok/s"
                f"  •  immediate replay {warm:,.0f} tok/s"
            ),
        ))
    levels = settings.get("concurrency", [])
    if levels:
        values = []
        for level_value in levels:
            median = result["concurrency"][str(level_value)][
                "aggregate_end_to_end_tokens_per_second"
            ]["median"]
            values.append(f"C{level_value} {median:.1f}")
        largest = result["concurrency"][str(max(levels))]
        streams = [
            stream
            for current_round in largest["rounds"]
            for stream in current_round["streams"]
        ]
        normal = sum(stream.get("finish_reason") == "stop" for stream in streams)
        visible = sum(bool(stream.get("output", "").strip()) for stream in streams)
        workload = str(settings.get("concurrency_workload", "unknown")).upper()
        lines.extend((
            section("CAPPED CONCURRENT GENERATION"),
            line(
                f"SHORT {workload} • END-TO-END • "
                f"{settings['concurrency_tokens']}-TOKEN CAP PER AGENT"
            ),
            line("AGGREGATE   " + "  •  ".join(values) + " tok/s"),
            line(
                f"C{max(levels)} OUTPUT STATE   normal stop {normal}/{len(streams)}"
                f"  •  visible {visible}/{len(streams)}  •  reasoning may be included"
            ),
        ))
    lines.extend((
        section("RECEIPT"),
        line(f"JSON       sha256:{fingerprint[:16]}…"),
        line("SHARE THE CARD • LINK THE JSON RECEIPT • #RIGMARK"),
        line("github.com/alexellis/rigmark"),
        rule("╰", "─", "╯"),
    ))
    return "\n".join(lines)


def colourise(card: str) -> str:
    cyan = "\033[96m"
    gold = "\033[93m"
    white = "\033[97m"
    dim = "\033[90m"
    green = "\033[92m"
    reset = "\033[0m"
    output = []
    for current in card.splitlines():
        colour = dim if current.startswith(("├", "╭", "╰")) else white
        if "R I G M A R K" in current or "REAL OUTPUT" in current:
            colour = gold
        elif "●" in current or "✓" in current:
            colour = green
        elif "RECEIPT" in current or "github.com" in current:
            colour = cyan
        output.append(colour + current + reset)
    return "\n".join(output)


def print_report(result: dict[str, Any], path: Path, colour: bool | None = None) -> None:
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    card = render(result, fingerprint)
    enabled = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    print(colourise(card) if (enabled if colour is None else colour) else card)


def save_report(result: dict[str, Any], result_path: Path) -> Path:
    """Write the stable, plain-text card beside its JSON receipt."""
    fingerprint = hashlib.sha256(result_path.read_bytes()).hexdigest()
    output = result_path.with_suffix(".card.txt")
    output.write_text(render(result, fingerprint) + "\n")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--no-colour", action="store_true")
    parser.add_argument("--save", action="store_true", help="write RESULT.card.txt")
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    if args.save:
        output = save_report(result, args.result)
        print(f"card: {output}", file=sys.stderr)
    print_report(result, args.result, colour=False if args.no_colour else None)


if __name__ == "__main__":
    main()
