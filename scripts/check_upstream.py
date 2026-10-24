"""Decide whether the update workflow should bump, and to which version.

Usage: check_upstream.py [--tag TAG] [--rebuild] [--pyproject FILE]

Writes proceed/tag/version/reason to $GITHUB_OUTPUT when set.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import fetch_bats
from bump import next_rebuild, version_from_tag

LATEST_URL = "https://api.github.com/repos/bats-core/bats-core/releases/latest"
PYPI_URL = "https://{host}/pypi/bats-core/{version}/json"


@dataclass(frozen=True)
class Decision:
    proceed: bool
    tag: str
    version: str
    reason: str


def latest_tag() -> str:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(LATEST_URL, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.load(response)["tag_name"]


def pypi_url(version: str) -> str:
    # PYPI_HOST selects the index; the workflow sets it to test.pypi.org
    # while publishing is pointed at TestPyPI.
    host = os.environ.get("PYPI_HOST", "pypi.org")
    return PYPI_URL.format(host=host, version=version)


def pypi_has(version: str) -> bool:
    try:
        with urllib.request.urlopen(pypi_url(version)) as response:
            return response.status == 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def branch_exists(name: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", name],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def decide(
    pin: fetch_bats.Pin,
    latest: str,
    tag_override: str | None,
    rebuild: bool,
    pypi_has: Callable[[str], bool],
    branch_exists: Callable[[str], bool],
) -> Decision:
    target = tag_override or latest
    if rebuild:
        if target != pin.tag:
            return Decision(
                False, target, pin.version, "rebuild requires the current tag"
            )
        version = next_rebuild(pin.version)
    elif target != pin.tag:
        version = version_from_tag(target)
    else:
        version = pin.version
        if pypi_has(version):
            return Decision(False, target, version, "up to date")
    branch = f"bump/{version}"
    if branch_exists(branch):
        return Decision(False, target, version, f"{branch} exists, awaiting a human")
    return Decision(True, target, version, "bump due")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decide whether a bump is due.")
    parser.add_argument(
        "--tag", default="", help="upstream tag to target instead of latest"
    )
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--pyproject", type=Path, default=fetch_bats.DEFAULT_PYPROJECT)
    args = parser.parse_args(argv)

    pin = fetch_bats.read_pin(args.pyproject)
    decision = decide(
        pin, latest_tag(), args.tag or None, args.rebuild, pypi_has, branch_exists
    )

    print(
        f"proceed={str(decision.proceed).lower()} tag={decision.tag} "
        f"version={decision.version} reason={decision.reason}"
    )
    if not decision.proceed:
        # Surfaces the skip on the run summary without opening logs.
        print(f"::warning::not bumping: {decision.reason}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"proceed={str(decision.proceed).lower()}\n")
            f.write(f"tag={decision.tag}\n")
            f.write(f"version={decision.version}\n")
            f.write(f"reason={decision.reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
