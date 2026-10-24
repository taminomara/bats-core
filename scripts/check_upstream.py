"""Decide whether the update workflow should bump, and to which version.

Usage: check_upstream.py [--tag TAG] [--rebuild] [--cooldown-days N]
                         [--pyproject FILE]

Writes proceed/tag/version/reason to $GITHUB_OUTPUT when set.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_bats
from bump import github_get, next_rebuild, version_from_tag

PYPI_URL = "https://{host}/pypi/bats-core/{version}/json"
DEFAULT_COOLDOWN_DAYS = 3


@dataclass(frozen=True)
class Release:
    tag: str
    published_at: datetime


@dataclass(frozen=True)
class Decision:
    proceed: bool
    tag: str
    version: str
    reason: str


def parse_published_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_release() -> Release:
    # The "latest" endpoint already excludes prereleases and drafts.
    data = github_get("/releases/latest")
    return Release(data["tag_name"], parse_published_at(data["published_at"]))


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
    *,
    published_at: datetime | None = None,
    now: datetime | None = None,
    cooldown_days: int = 0,
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
        # The cooldown gives upstream time to notice and pull a bad release.
        # A human naming the tag explicitly has made that call already.
        if tag_override is None and published_at is not None and cooldown_days:
            age = (now or datetime.now(timezone.utc)) - published_at
            if age < timedelta(days=cooldown_days):
                return Decision(
                    False,
                    target,
                    version,
                    f"cooldown: {target} was released {age.days}d ago, "
                    f"waiting {cooldown_days}d",
                )
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
    parser.add_argument(
        "--cooldown-days",
        type=int,
        default=DEFAULT_COOLDOWN_DAYS,
        help="minimum age of a release before it is bumped to (0 disables)",
    )
    parser.add_argument("--pyproject", type=Path, default=fetch_bats.DEFAULT_PYPROJECT)
    args = parser.parse_args(argv)

    pin = fetch_bats.read_pin(args.pyproject)
    release = latest_release()
    decision = decide(
        pin,
        release.tag,
        args.tag or None,
        args.rebuild,
        pypi_has,
        branch_exists,
        published_at=release.published_at,
        cooldown_days=args.cooldown_days,
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
