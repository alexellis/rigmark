#!/usr/bin/env python3
"""Check a RigMark checkout against the newest published GitHub release."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


API = "https://api.github.com/repos/alexellis/rigmark"
RELEASES = "https://github.com/alexellis/rigmark/releases"


def github_json(path: str) -> Any:
    request = urllib.request.Request(
        API + path,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "RigMark-release-check"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.load(response)


def check_release(revision: str, dirty: bool | None) -> dict[str, Any]:
    """Return a best-effort comparison; never interrupt a benchmark on network failure."""
    result: dict[str, Any] = {"status": "unavailable", "revision": revision,
                              "dirty": dirty, "release_url": RELEASES}
    try:
        releases = github_json("/releases?per_page=10")
        if not isinstance(releases, list):
            raise ValueError("unexpected release response")
        published = [item for item in releases
                     if item.get("published_at") and not item.get("draft")]
        if not published:
            raise ValueError("no published releases found")
        latest = max(published, key=lambda item: item["published_at"])
        tag = latest["tag_name"]
        result.update(tag=tag, prerelease=bool(latest.get("prerelease")),
                      release_url=latest.get("html_url", RELEASES))
        if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
            result["status"] = "unknown-revision"
            return result
        comparison = github_json(
            "/compare/" + urllib.parse.quote(tag, safe="") + "..." + revision
        )
        status = comparison.get("status")
        if status not in ("identical", "ahead", "behind", "diverged"):
            raise ValueError("unexpected comparison response")
        result.update(status=status, ahead_by=comparison.get("ahead_by", 0),
                      behind_by=comparison.get("behind_by", 0))
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        result["status"] = "unavailable"
    return result


def format_check(result: dict[str, Any]) -> str:
    tag = result.get("tag", "the newest published release")
    if result.get("prerelease"):
        tag += " (pre-release)"
    revision = str(result.get("revision", "unknown"))[:12]
    status = result["status"]
    if status == "identical":
        message = f"RigMark {revision} matches {tag}."
    elif status == "ahead":
        message = (f"RigMark {revision} is {result['ahead_by']} commit(s) "
                   f"ahead of {tag}; this is an unreleased checkout.")
    elif status == "behind":
        message = (f"WARNING: RigMark {revision} is {result['behind_by']} commit(s) "
                   f"behind {tag}. Update before benchmarking or sharing.")
    elif status == "diverged":
        message = (f"WARNING: RigMark {revision} diverges from {tag}; "
                   "verify the checkout before sharing.")
    else:
        message = ("RigMark release status could not be verified; check the newest "
                   "published release before sharing.")
    if result.get("dirty"):
        message += " Local changes are present and recorded in the receipt."
    return message + "\n" + str(result["release_url"])


def main() -> None:
    from bench import git_identity

    identity = git_identity()
    result = check_release(identity["repository_revision"],
                           identity["repository_dirty"])
    print(format_check(result))
    if result["status"] in ("behind", "diverged"):
        raise SystemExit(1)
    if result["status"] not in ("identical", "ahead"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
