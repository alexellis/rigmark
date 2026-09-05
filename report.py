#!/usr/bin/env python3
"""Render an auditable terminal card from an appliance benchmark result."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


WIDTH = 82


def clipped(value: object, width: int) -> str:
    text = str(value)
    return text if len(text) <= width else text[: width - 1] + "…"


def line(value: object = "") -> str:
    return "║ " + clipped(value, WIDTH - 4).ljust(WIDTH - 4) + " ║"


def rule(left: str, middle: str, right: str) -> str:
    return left + middle * (WIDTH - 2) + right


def metric(result: dict[str, Any], workload: str) -> str:
    data = result["decode"][workload]
    speed = data["decode_tokens_per_second"]
    gate = data["completion_gate"]
    mark = "PASS" if gate["passed"] == gate["total"] else "FAIL"
    return (
        f"{workload.upper():<10} {speed['median']:>6.1f} tok/s  "
        f"[{speed['minimum']:.1f}–{speed['maximum']:.1f}]  "
        f"{mark} {gate['passed']}/{gate['total']}"
    )


def render(result: dict[str, Any], fingerprint: str) -> str:
    run = result["run"]
    settings = result["settings"]
    appliance = run["appliance"]
    gates = [
        result["decode"][name]["completion_gate"]
        for name in ("code", "prose", "structured")
    ]
    verified = all(gate["passed"] == gate["total"] for gate in gates)
    effort = (
        settings.get("extra_body", {})
        .get("chat_template_kwargs", {})
        .get("reasoning_effort", "unspecified")
    )
    lines = [
        rule("╔", "═", "╗"),
        line("R I G M A R K  //  REAL OUTPUT. HONEST SPEED."),
        line("RESULT  //  " + ("VERIFIED" if verified else "INCOMPLETE — DO NOT HEADLINE")),
        line(),
        line(f"MODEL     {run['model']}"),
        line(f"HARDWARE  {appliance.get('hardware', 'unspecified')}"),
        line(f"MODE      reasoning={effort}  protocol={result['protocol']['version']}"),
        rule("╠", "═", "╣"),
        line("REAL OUTPUT  //  MEDIAN [RANGE]  //  COMPLETION GATE"),
        line(metric(result, "code")),
        line(metric(result, "prose")),
        line(metric(result, "structured")),
    ]
    depths = settings.get("prefill_depths", [])
    if depths:
        depth = max(depths)
        data = result["prefill"][str(depth)]
        cold = data["cold"]["effective_prefill_tokens_per_second"]["median"]
        warm = data["warm_replay"]["effective_prefill_tokens_per_second"]["median"]
        lines.extend((
            rule("╠", "═", "╣"),
            line(f"PREFILL   {depth // 1024}K cold {cold:,.0f} tok/s  //  replay {warm:,.0f} tok/s"),
        ))
    levels = settings.get("concurrency", [])
    if levels:
        values = []
        for level_value in levels:
            median = result["concurrency"][str(level_value)][
                "aggregate_end_to_end_tokens_per_second"
            ]["median"]
            values.append(f"C{level_value} {median:.1f}")
        lines.extend((
            rule("╠", "═", "╣"),
            line(
                "SHORT CODE LOAD  //  END-TO-END  //  "
                f"{settings['concurrency_tokens']}-TOKEN CAP"
            ),
            line("AGGREGATE   " + "  |  ".join(values) + " tok/s"),
        ))
    lines.extend((
        rule("╠", "═", "╣"),
        line(f"RECEIPT   sha256:{fingerprint[:16]}…"),
        line("SCREENSHOT → POST TO X • LINK THE JSON RECEIPT • #RigMark"),
        line("github.com/alexellis/rigmark"),
        rule("╚", "═", "╝"),
    ))
    return "\n".join(lines)


def colourise(card: str) -> str:
    cyan = "\033[96m"
    gold = "\033[93m"
    green = "\033[92m"
    reset = "\033[0m"
    output = []
    for current in card.splitlines():
        colour = gold if "REAL OUTPUT" in current else cyan
        if "VERIFIED RUN" in current or "PASS" in current:
            colour = green
        output.append(colour + current + reset)
    return "\n".join(output)


def print_report(result: dict[str, Any], path: Path, colour: bool | None = None) -> None:
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    card = render(result, fingerprint)
    enabled = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    print(colourise(card) if (enabled if colour is None else colour) else card)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--no-colour", action="store_true")
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    print_report(result, args.result, colour=False if args.no_colour else None)


if __name__ == "__main__":
    main()
