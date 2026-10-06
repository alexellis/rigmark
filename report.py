#!/usr/bin/env python3
"""Render an auditable terminal card from an appliance benchmark result."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import textwrap
from pathlib import Path
from typing import Any

from receipt import validate_result


WIDTH = 74


def depth_label(depth: int) -> str:
    if depth >= 1_024 and depth % 1_024 == 0:
        return f"{depth // 1_024}K"
    return f"{depth:,} TOKENS"


def clipped(value: object, width: int) -> str:
    text = str(value)
    return text if len(text) <= width else text[: width - 1] + "…"


def line(value: object = "") -> str:
    return "│  " + clipped(value, WIDTH - 4).ljust(WIDTH - 4) + "│"


def wrapped_lines(value: object) -> list[str]:
    """Keep metadata and request settings readable without truncating them."""
    return [line(part) for part in textwrap.wrap(
        str(value), width=WIDTH - 4, subsequent_indent="  ",
        break_on_hyphens=False,
    )] or [line()]


def rule(left: str, middle: str, right: str) -> str:
    return left + middle * (WIDTH - 2) + right


def section(title: str) -> list[str]:
    prefix = f"├─ {title} "
    return [line(), prefix + "─" * (WIDTH - len(prefix) - 1) + "┤", line()]


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
    span = f"{speed['minimum']:.1f}–{speed['maximum']:.1f}"
    return (
        f"{label:<14}{speed['median']:>8.1f}{span:>18}"
        f"{last_output['median']:>11.1f}"
        f"{mark + ' ' + str(gate['passed']) + '/' + str(gate['total']):>10}"
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


def reasoning_effort(settings: dict[str, Any]) -> str:
    """Return the reasoning effort from either supported request dialect."""
    extra = settings.get("extra_body", {})
    if not isinstance(extra, dict):
        return "unspecified"
    effort = extra.get("reasoning_effort")
    if isinstance(effort, str) and effort:
        return effort
    template = extra.get("chat_template_kwargs", {})
    if not isinstance(template, dict):
        return "unspecified"
    effort = template.get("reasoning_effort")
    return effort if isinstance(effort, str) and effort else "unspecified"


SUITE_DEFAULTS = {
    "runs": 5, "decode_tokens": 8192, "temperature": 0.0, "top_p": 1.0,
    "seed": 20260905, "prefill_depths": [8192, 32768, 65536],
    "prefill_runs": 3, "concurrency": [1, 2, 4], "concurrency_runs": 3,
    "concurrency_tokens": 256, "concurrency_workload": "code",
}


def settings_lines(settings: dict[str, Any], protocol: str) -> list[str]:
    defaults = dict(SUITE_DEFAULTS)
    if protocol in ("1.0.0", "1.1.0", "1.2.0"):
        defaults["decode_tokens"] = 4096
    changed = {key: settings.get(key) for key, default in defaults.items()
               if settings.get(key) != default}
    lines = [line("SUITE: " + ("CUSTOM SETTINGS" if changed else "DEFAULT SETTINGS"))]
    for key, value in changed.items():
        if key == "prefill_depths" and value == []:
            flag = "--skip-prefill"
        elif key == "concurrency" and value == []:
            flag = "--skip-concurrency"
        else:
            flag = "--" + key.replace("_", "-") + "=" + (
                ",".join(map(str, value)) if isinstance(value, list) else str(value)
            )
        lines.extend(wrapped_lines("Changed: " + flag))
    lines.extend(wrapped_lines(
        "REQUEST: " + json.dumps(settings.get("extra_body", {}), sort_keys=True)
    ))
    lines.extend(wrapped_lines(
        f"Temperature {settings.get('temperature')} | top_p {settings.get('top_p')}"
        f" | seed {settings.get('seed')} | protocol {protocol}"
    ))
    depths = "/".join(depth_label(d) for d in settings.get("prefill_depths", [])) or "skipped"
    lines.extend(wrapped_lines(
        f"Decode: {settings['runs']} runs, {settings['decode_tokens']}-token cap"
        f" | Prefill: {depths}, {settings.get('prefill_runs')} pairs"
    ))
    levels = "/".join(f"C{c}" for c in settings.get("concurrency", [])) or "skipped"
    lines.extend(wrapped_lines(
        f"Concurrency: {levels}, {settings.get('concurrency_runs')} rounds, "
        f"{settings.get('concurrency_tokens')}-token cap; "
        f"workload {settings.get('concurrency_workload')}"
    ))
    if "prefill_cache_isolation" in settings:
        lines.extend(wrapped_lines("Cache isolation: " + str(settings["prefill_cache_isolation"])))
    other = {key: value for key, value in settings.items()
             if key not in {*SUITE_DEFAULTS, "extra_body", "prefill_cache_isolation"}}
    if other:
        lines.extend(wrapped_lines("Other settings: " + json.dumps(other, sort_keys=True)))
    return lines


def render(result: dict[str, Any], fingerprint: str) -> str:
    errors = validate_result(result)
    if errors:
        raise ValueError("invalid receipt: " + "; ".join(errors))
    run = result["run"]
    settings = result["settings"]
    appliance = run["appliance"]
    gates = [result["decode"][name]["completion_gate"]
             for name in ("code", "prose", "structured")]
    passed = sum(gate["passed"] for gate in gates)
    total = sum(gate["total"] for gate in gates)
    depths = settings.get("prefill_depths", [])
    levels = settings.get("concurrency", [])
    lines = [
        rule("╭", "─", "╮"),
        line(),
        line("R I G M A R K   //   AGENT WORKLOAD RECEIPT"),
        line("BENCHMARKS LOCAL AI HOW CODING AGENTS ACTUALLY USE IT"),
        line(f"●  {passed}/{total} BASIC OUTPUT GATES PASSED" if passed == total else
             f"▲  {passed}/{total} BASIC OUTPUT GATES PASSED — DO NOT HEADLINE"),
    ]
    if not depths or not levels:
        missing = ", ".join(name for name, enabled in
                            (("prefill", depths), ("concurrency", levels)) if not enabled)
        lines.extend(wrapped_lines("INCOMPLETE SUITE: " + missing + " not measured"))
    lines.extend(section("MODEL"))
    lines.extend(wrapped_lines(run["model"]))
    lines.extend([
        *section("SINGLE STREAM"),
        line(f"{'WORKLOAD':<14}{'tok/s':>8}{'Range tok/s':>18}{'Last (s)':>11}{'Checks':>10}"),
        *(line(metric(result, name)) for name in ("prose", "code", "structured")),
        line(),
        line("* Predictable JSON ceiling; not general agent performance."),
        line("Decode medians are estimates; rates include streamed reasoning."),
    ])
    lines.extend(section("PREFILL"))
    if depths:
        verified = all(
            row.get("cached_prompt_tokens") == 0
            for depth in depths for row in result["prefill"][str(depth)]["cold"]["runs"]
        )
        first = "Cold" if verified else "First"
        lines.append(line(f"{'DEPTH':<8}{first + ' tok/s':>14}{first + ' TTFT (s)':>19}{'Replay TTFT (s)':>19}"))
        for depth in depths:
            data = result["prefill"][str(depth)]
            cold = data["cold"]
            replay = data["warm_replay"]["ttft_seconds"]["median"]
            lines.append(line(
                f"{depth_label(depth):<8}"
                f"{cold['effective_prefill_tokens_per_second']['median']:>14,.0f}"
                f"{cold['ttft_seconds']['median']:>19.2f}{replay:>19.2f}"
            ))
        if not verified:
            lines.append(line("Cold cache UNVERIFIED: cache-hit usage unavailable."))
        lines.append(line("Medians; replay is an immediate repeat, not a proven hit."))
    else:
        lines.append(line("NOT MEASURED: prefill skipped (--skip-prefill)."))
    lines.extend(section("CAPPED CONCURRENT GENERATION"))
    if levels:
        values = [f"C{level} {result['concurrency'][str(level)]['aggregate_end_to_end_tokens_per_second']['median']:.1f}"
                  for level in levels]
        lines.extend(wrapped_lines("Aggregate tok/s: " + " | ".join(values)))
        streams = [stream for current in result["concurrency"][str(max(levels))]["rounds"]
                   for stream in current["streams"]]
        normal = sum(stream.get("finish_reason") == "stop" for stream in streams)
        visible = sum(bool(stream.get("output", "").strip()) for stream in streams)
        lines.extend(wrapped_lines(
            f"C{max(levels)}: {normal}/{len(streams)} normal stops; "
            f"{visible}/{len(streams)} with visible output."
        ))
        lines.append(line("Capped throughput includes reasoning; not completed agent tasks."))
    else:
        lines.append(line("NOT MEASURED: concurrency skipped (--skip-concurrency)."))
    lines.extend(section("APPLIANCE"))
    for label, key in (("Hardware", "hardware"), ("Topology", "topology"),
                       ("Checkpoint", "model"), ("Quantisation", "quantisation"),
                       ("KV cache", "kv_cache_dtype"), ("Engine", "serving_engine"),
                       ("Recipe", "recipe")):
        if appliance.get(key):
            value = str(appliance[key])
            revision_key = {"model": "model_revision", "recipe": "recipe_revision"}.get(key)
            if revision_key and appliance.get(revision_key):
                value += " @ " + str(appliance[revision_key])[:12]
            lines.extend(wrapped_lines(f"{label}: {value}"))
    lines.extend(section("SETTINGS"))
    lines.extend(settings_lines(settings, result["protocol"]["version"]))
    lines.extend(wrapped_lines("Comparison ID: " + str(run.get("comparison_id", "unknown"))))
    lines.extend(section("RECEIPT"))
    lines.extend(wrapped_lines(benchmark_identity(result)))
    lines.extend([
        line(f"JSON sha256:{fingerprint[:16]}…"),
        line("SHARE THE CARD • LINK THE JSON RECEIPT • #RIGMARK"),
        line("github.com/alexellis/rigmark"),
        line(),
        rule("╰", "─", "╯"),
    ])
    return "\n".join(lines)


def colourise(card: str) -> str:
    cyan, gold, white = "\033[96m", "\033[93m", "\033[97m"
    dim, green, reset = "\033[90m", "\033[92m", "\033[0m"
    output = []
    for current in card.splitlines():
        colour = dim if current.startswith(("├", "╭", "╰")) else white
        if "R I G M A R K" in current or "github.com" in current:
            colour = cyan
        elif any(word in current for word in ("INCOMPLETE", "UNVERIFIED", "NOT MEASURED", "CUSTOM", "DO NOT HEADLINE", "✗")):
            colour = gold
        elif "BASIC OUTPUT GATES PASSED" in current:
            colour = green
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
