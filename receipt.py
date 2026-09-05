"""Validate the internal consistency of a RigMark JSON receipt."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from typing import Any


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def nested(value: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(value, dict):
            raise KeyError(key)
        value = value[key]
    return value


def summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * 0.9)
    return {
        "median": round(statistics.median(values), 3),
        "minimum": round(min(values), 3),
        "maximum": round(max(values), 3),
        "p90": round(ordered[index], 3),
    }


def check_summary(
    errors: list[str],
    owner: dict[str, Any],
    name: str,
    rows: list[dict[str, Any]],
    field: str,
    path: str,
    required: bool = True,
) -> None:
    if name not in owner:
        if required:
            errors.append(f"{path}.{name} is missing")
        return
    try:
        raw_values = [row[field] for row in rows]
        if not all(is_number(value) and value >= 0 for value in raw_values):
            raise ValueError
        expected = summary([float(value) for value in raw_values])
        actual = owner[name]
        for key, value in expected.items():
            if (
                not is_number(actual[key])
                or not math.isclose(float(actual[key]), value, abs_tol=0.0005)
            ):
                errors.append(f"{path}.{name}.{key} does not match raw runs")
    except (KeyError, TypeError, ValueError):
        errors.append(f"{path}.{name} is malformed")


def normal_stream_end(row: dict[str, Any]) -> bool:
    if row.get("finish_reason") != "stop":
        return False
    if "stream_done_marker" in row and row["stream_done_marker"] is not True:
        return False
    return True


def output_valid(workload: str, row: dict[str, Any]) -> bool:
    output = row.get("output")
    if not isinstance(output, str) or not output.strip() or not normal_stream_end(row):
        return False
    if workload != "structured":
        return True
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return False
    return (
        isinstance(value, list)
        and len(value) == 50
        and all(
            isinstance(item, dict)
            and set(item) == {"index", "square"}
            and type(item["index"]) is int
            and type(item["square"]) is int
            and item["index"] == index
            and item["square"] == index * index
            for index, item in enumerate(value, start=1)
        )
    )


def check_stream_row(
    errors: list[str],
    row: Any,
    path: str,
    require_v11: bool = False,
) -> None:
    if not isinstance(row, dict):
        errors.append(f"{path} is not an object")
        return
    if require_v11:
        for field in (
            "measured_sse_events",
            "response_tail_seconds",
            "stream_done_marker",
            "time_to_first_visible_seconds",
            "time_to_last_output_seconds",
        ):
            if field not in row:
                errors.append(f"{path}.{field} is required by protocol 1.1.0")
    for field in ("prompt_tokens", "completion_tokens"):
        if not is_int(row.get(field)) or row[field] < 0:
            errors.append(f"{path}.{field} must be a non-negative integer")
    for field in (
        "ttft_seconds", "decode_seconds", "decode_tokens_per_second",
        "wall_seconds",
    ):
        if not is_number(row.get(field)) or row[field] < 0:
            errors.append(f"{path}.{field} must be a non-negative number")
    for field in (
        "time_to_first_visible_seconds", "time_to_last_output_seconds",
        "response_tail_seconds",
    ):
        if (
            field in row
            and row[field] is not None
            and (not is_number(row[field]) or row[field] < 0)
        ):
            errors.append(f"{path}.{field} must be a non-negative number or null")
    completion = row.get("completion_tokens")
    window = row.get("decode_seconds")
    rate = row.get("decode_tokens_per_second")
    if is_int(completion) and is_number(window) and is_number(rate):
        if completion > 1 and window <= 0:
            errors.append(f"{path}.decode_seconds is not measurable")
        else:
            expected_rate = (
                0.0 if completion <= 1 else round((completion - 1) / window, 3)
            )
            if not math.isclose(
                float(rate), expected_rate, rel_tol=0.002, abs_tol=0.01
            ):
                errors.append(
                    f"{path}.decode_tokens_per_second does not match tokens/time"
                )
    if "measured_sse_events" in row:
        events = row["measured_sse_events"]
        if not is_int(events) or events < 1:
            errors.append(f"{path}.measured_sse_events must be a positive integer")
        elif is_int(completion) and completion > 1 and events < 2:
            errors.append(f"{path}.decode rate has an unmeasurable SSE window")
    if (
        "stream_done_marker" in row
        and not isinstance(row["stream_done_marker"], bool)
    ):
        errors.append(f"{path}.stream_done_marker must be a boolean")
    elif require_v11 and row.get("stream_done_marker") is not True:
        errors.append(f"{path}.stream_done_marker must be true")
    ttft = row.get("ttft_seconds")
    if is_number(ttft) and is_number(window):
        expected_last = float(ttft) + float(window)
        first_visible = row.get("time_to_first_visible_seconds")
        if is_number(first_visible) and not (
            float(ttft) <= float(first_visible) <= expected_last + 0.000003
        ):
            errors.append(
                f"{path}.time_to_first_visible_seconds is outside the output window"
            )
        if (
            "time_to_last_output_seconds" in row
            and is_number(row["time_to_last_output_seconds"])
            and not math.isclose(
                float(row["time_to_last_output_seconds"]),
                expected_last,
                abs_tol=0.000003,
            )
        ):
            errors.append(
                f"{path}.time_to_last_output_seconds does not match TTFT+decode"
            )
        wall = row.get("wall_seconds")
        if is_number(wall) and wall + 0.000003 < expected_last:
            errors.append(f"{path}.wall_seconds ends before the last output")
        if (
            "response_tail_seconds" in row
            and is_number(wall)
            and is_number(row["response_tail_seconds"])
            and not math.isclose(
                float(row["response_tail_seconds"]),
                max(float(wall) - expected_last, 0),
                abs_tol=0.000004,
            )
        ):
            errors.append(f"{path}.response_tail_seconds does not match wall time")
    output = row.get("output")
    if not isinstance(output, str):
        errors.append(f"{path}.output must be a string")
    else:
        if row.get("output_characters") != len(output):
            errors.append(f"{path}.output_characters does not match output")
        digest = hashlib.sha256(output.encode()).hexdigest()
        if row.get("output_sha256") != digest:
            errors.append(f"{path}.output_sha256 does not match output")


def validate_result(result: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["receipt is not an object"]
    if result.get("schema") != 1:
        errors.append("schema must be 1")
    if "error" in result:
        errors.append("receipt records an incomplete run error")
    protocol = result.get("protocol")
    version = protocol.get("version") if isinstance(protocol, dict) else None
    if version not in ("1.0.0", "1.1.0"):
        errors.append(f"unsupported protocol version: {version!r}")
    require_v11 = version == "1.1.0"
    if require_v11 and not isinstance(
        protocol.get("repository_source_sha256"), str
    ):
        errors.append("protocol.repository_source_sha256 is required")
    elif require_v11 and not re.fullmatch(
        r"[0-9a-f]{64}", protocol["repository_source_sha256"]
    ):
        errors.append("protocol.repository_source_sha256 is malformed")
    try:
        settings = nested(result, "settings")
        decode = nested(result, "decode")
    except KeyError as error:
        return errors + [f"missing {error.args[0]}"]

    if not isinstance(settings, dict) or not isinstance(decode, dict):
        return errors + ["settings and decode must be objects"]

    runs_count = settings.get("runs")
    if not is_int(runs_count) or runs_count < 1:
        errors.append("settings.runs must be a positive integer")
        runs_count = 0
    for workload in ("code", "prose", "structured"):
        path = f"decode.{workload}"
        value = decode.get(workload) if isinstance(decode, dict) else None
        rows = value.get("runs") if isinstance(value, dict) else None
        if not isinstance(rows, list):
            errors.append(f"{path}.runs is missing")
            continue
        if len(rows) != runs_count:
            errors.append(f"{path}.runs has {len(rows)} rows, expected {runs_count}")
        for index, row in enumerate(rows, start=1):
            check_stream_row(
                errors, row, f"{path}.runs[{index}]", require_v11
            )
        check_summary(
            errors,
            value,
            "decode_tokens_per_second",
            rows,
            "decode_tokens_per_second",
            path,
        )
        check_summary(errors, value, "ttft_seconds", rows, "ttft_seconds", path)
        check_summary(
            errors, value, "wall_seconds", rows, "wall_seconds", path,
            required=False,
        )
        check_summary(
            errors, value, "time_to_last_output_seconds", rows,
            "time_to_last_output_seconds", path, required=require_v11,
        )
        valid = sum(
            output_valid(workload, row)
            for row in rows
            if isinstance(row, dict)
        )
        gate = value.get("completion_gate")
        if (
            not isinstance(gate, dict)
            or gate.get("passed") != valid
            or gate.get("total") != len(rows)
        ):
            errors.append(f"{path}.completion_gate does not match raw outputs")

    depths = settings.get("prefill_depths", [])
    prefill = result.get("prefill", {})
    if not isinstance(depths, list) or not isinstance(prefill, dict):
        errors.append("prefill settings or results are malformed")
        depths = []
    prefill_runs = settings.get("prefill_runs")
    if depths and (not is_int(prefill_runs) or prefill_runs < 1):
        errors.append("settings.prefill_runs must be a positive integer")
    for depth in depths:
        path = f"prefill.{depth}"
        value = prefill.get(str(depth))
        if not is_int(depth) or not isinstance(value, dict):
            errors.append(f"{path} is missing or malformed")
            continue
        for phase in ("cold", "warm_replay"):
            phase_path = f"{path}.{phase}"
            owner = value.get(phase)
            rows = owner.get("runs") if isinstance(owner, dict) else None
            if not isinstance(rows, list):
                errors.append(f"{phase_path}.runs is missing")
                continue
            if len(rows) != prefill_runs:
                errors.append(f"{phase_path}.runs has the wrong length")
            for index, row in enumerate(rows, start=1):
                row_path = f"{phase_path}.runs[{index}]"
                check_stream_row(errors, row, row_path, require_v11)
                if isinstance(row, dict):
                    if row.get("prompt_tokens") != depth:
                        errors.append(f"{row_path}.prompt_tokens does not match depth")
                    if (
                        "requested_prompt_tokens" in row
                        and row["requested_prompt_tokens"] != depth
                    ):
                        errors.append(
                            f"{row_path}.requested_prompt_tokens does not match depth"
                        )
                    if require_v11 and "requested_prompt_tokens" not in row:
                        errors.append(
                            f"{row_path}.requested_prompt_tokens is required"
                        )
                    ttft = row.get("ttft_seconds")
                    prefill_rate = row.get(
                        "effective_prefill_tokens_per_second"
                    )
                    if not is_number(ttft) or ttft <= 0:
                        errors.append(f"{row_path}.ttft_seconds must be positive")
                    elif not is_number(prefill_rate) or prefill_rate < 0:
                        errors.append(
                            f"{row_path}.effective_prefill_tokens_per_second "
                            "must be a non-negative number"
                        )
                    else:
                        expected_rate = round(depth / row["ttft_seconds"], 3)
                        if not math.isclose(
                            prefill_rate,
                            expected_rate,
                            rel_tol=0.002,
                            abs_tol=0.01,
                        ):
                            errors.append(
                                f"{row_path}.effective_prefill_tokens_per_second "
                                "does not match depth/TTFT"
                            )
            check_summary(errors, owner, "effective_prefill_tokens_per_second", rows,
                          "effective_prefill_tokens_per_second", phase_path)
            check_summary(errors, owner, "ttft_seconds", rows, "ttft_seconds", phase_path)

    levels = settings.get("concurrency", [])
    concurrency = result.get("concurrency", {})
    rounds_expected = settings.get("concurrency_runs")
    if levels and (not is_int(rounds_expected) or rounds_expected < 1):
        errors.append("settings.concurrency_runs must be a positive integer")
    if not isinstance(levels, list) or not isinstance(concurrency, dict):
        errors.append("concurrency settings or results are malformed")
        levels = []
    for level in levels:
        path = f"concurrency.{level}"
        value = concurrency.get(str(level))
        rounds = value.get("rounds") if isinstance(value, dict) else None
        if not is_int(level) or not isinstance(rounds, list):
            errors.append(f"{path}.rounds is missing or malformed")
            continue
        if len(rounds) != rounds_expected:
            errors.append(f"{path}.rounds has the wrong length")
        streams: list[dict[str, Any]] = []
        for index, row in enumerate(rounds, start=1):
            current = row.get("streams") if isinstance(row, dict) else None
            if not isinstance(current, list) or len(current) != level:
                errors.append(f"{path}.rounds[{index}].streams has the wrong length")
                continue
            for stream_index, stream in enumerate(current, start=1):
                check_stream_row(
                    errors, stream,
                    f"{path}.rounds[{index}].streams[{stream_index}]",
                    require_v11,
                )
            streams.extend(current)
            if isinstance(row, dict):
                completion = row.get("completion_tokens")
                wall = row.get("wall_seconds")
                aggregate = row.get("aggregate_end_to_end_tokens_per_second")
                stream_total = sum(
                    stream.get("completion_tokens", 0)
                    for stream in current
                    if isinstance(stream, dict)
                    and is_int(stream.get("completion_tokens"))
                )
                if completion != stream_total:
                    errors.append(
                        f"{path}.rounds[{index}].completion_tokens does not match streams"
                    )
                if not is_number(wall) or wall <= 0:
                    errors.append(
                        f"{path}.rounds[{index}].wall_seconds must be positive"
                    )
                elif current:
                    stream_walls = [
                        stream.get("wall_seconds")
                        for stream in current
                        if isinstance(stream, dict)
                    ]
                    if all(is_number(value) for value in stream_walls) and (
                        wall + 0.000003 < max(stream_walls)
                    ):
                        errors.append(
                            f"{path}.rounds[{index}].wall_seconds is shorter "
                            "than a member stream"
                        )
                if not is_number(aggregate) or aggregate < 0:
                    errors.append(
                        f"{path}.rounds[{index}].aggregate rate is malformed"
                    )
                if (
                    is_int(completion)
                    and is_number(wall)
                    and wall > 0
                    and is_number(aggregate)
                    and not math.isclose(
                        aggregate,
                        round(completion / wall, 3),
                        rel_tol=0.002,
                        abs_tol=0.01,
                    )
                ):
                    errors.append(
                        f"{path}.rounds[{index}].aggregate rate does not match tokens/time"
                    )
        check_summary(errors, value, "aggregate_end_to_end_tokens_per_second", rounds,
                      "aggregate_end_to_end_tokens_per_second", path)
        check_summary(errors, value, "per_stream_decode_tokens_per_second", streams,
                      "decode_tokens_per_second", path)
        check_summary(errors, value, "per_stream_ttft_seconds", streams,
                      "ttft_seconds", path)
    return errors
