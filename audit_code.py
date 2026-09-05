#!/usr/bin/env python3
"""Replay the Go tests emitted in RigMark code responses inside Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from receipt import validate_result


def code_blocks(output: str) -> tuple[str, str]:
    blocks = re.findall(r"```(?:go)?\s*\n(.*?)```", output, re.DOTALL)
    if len(blocks) != 2:
        raise ValueError(f"expected two fenced Go blocks, found {len(blocks)}")
    return blocks[0].strip() + "\n", blocks[1].strip() + "\n"


def docker_command(directory: Path, image: str, name: str) -> list[str]:
    return [
        "docker", "run", "--rm", "--name", name, "--pull", "never",
        "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt",
        "no-new-privileges", "--memory", "512m", "--cpus", "1",
        "--pids-limit", "128", "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,size=256m", "-e", "GO111MODULE=off",
        "-e", "GOCACHE=/tmp/gocache", "-v", f"{directory}:/src:ro",
        "-w", "/src", image, "go", "test", "-json", "-count=1",
        "-timeout=20s", "./...",
    ]


def audit(path: Path, image: str, timeout: float) -> tuple[int, int]:
    raw = path.read_bytes()
    result: dict[str, Any] = json.loads(raw)
    errors = validate_result(result)
    if errors:
        raise ValueError("invalid receipt: " + "; ".join(errors))
    runs = result["decode"]["code"]["runs"]
    passed = 0
    print(f"{path}: sha256:{hashlib.sha256(raw).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="rigmark-code-audit-") as root:
        for index, run in enumerate(runs, start=1):
            directory = Path(root) / str(index)
            directory.mkdir()
            try:
                implementation, tests = code_blocks(run["output"])
            except (KeyError, TypeError, ValueError) as error:
                print(f"  run {index}: INVALID ({error})", flush=True)
                continue
            (directory / "ratelimit.go").write_text(implementation)
            (directory / "ratelimit_test.go").write_text(tests)
            container = f"rigmark-audit-{uuid.uuid4().hex[:16]}"
            try:
                completed = subprocess.run(
                    docker_command(directory, image, container),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                print(f"  run {index}: ERROR ({error})", flush=True)
                continue
            finally:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            events = []
            for line in completed.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            tests_run = sum(
                event.get("Action") == "run" and bool(event.get("Test"))
                for event in events
            )
            if completed.returncode == 0:
                if tests_run:
                    passed += 1
                    print(f"  run {index}: PASS ({tests_run} tests)", flush=True)
                else:
                    print(f"  run {index}: INVALID (no tests ran)", flush=True)
            else:
                detail = [
                    str(event.get("Output", "")).strip()
                    for event in events
                    if event.get("Output")
                ]
                detail.extend(completed.stderr.strip().splitlines())
                summary = next(
                    (line for line in detail if line.startswith("--- FAIL:")),
                    detail[-1].strip() if detail else "go test failed",
                )
                kind = "TEST FAIL" if tests_run else "BUILD/INFRA FAIL"
                print(f"  run {index}: {kind} ({summary})", flush=True)
    print(
        f"  model-supplied test suites: {passed}/{len(runs)} passed",
        flush=True,
    )
    return passed, len(runs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--image", default="golang:1.25")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()

    try:
        subprocess.run(
            ["docker", "image", "inspect", args.image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        parser.error(
            f"Docker image {args.image!r} is not local; pull and inspect it first"
        )

    totals = [audit(path, args.image, args.timeout) for path in args.results]
    raise SystemExit(0 if all(passed == total for passed, total in totals) else 1)


if __name__ == "__main__":
    main()
