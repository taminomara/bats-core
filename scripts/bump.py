"""Rewrite the bats pin in pyproject.toml for a new upstream tag or a rebuild.

Usage: bump.py TAG [--rebuild] [--sha256 HEX] [--pyproject FILE]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import fetch_bats

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class InvalidTag(ValueError):
    pass


def version_from_tag(tag: str) -> str:
    if not TAG_RE.match(tag):
        raise InvalidTag(f"{tag!r} is not a release tag of the form vX.Y.Z")
    return tag[1:]


def next_rebuild(version: str) -> str:
    parts = version.split(".")
    if len(parts) == 3:
        return f"{version}.1"
    return ".".join([*parts[:3], str(int(parts[3]) + 1)])


def tarball_sha256(tag: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return fetch_bats.sha256_of(fetch_bats.fetch_tarball(tag, Path(tmp)))


def _replace_line(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf'^{key} = "[^"]*"$', re.MULTILINE)
    if len(pattern.findall(text)) != 1:
        raise ValueError(f"expected exactly one top-level `{key} = ...` line")
    return pattern.sub(f'{key} = "{value}"', text)


def rewrite_pin(text: str, version: str, tag: str, sha256: str) -> str:
    text = _replace_line(text, "version", version)
    text = _replace_line(text, "tag", tag)
    return _replace_line(text, "sha256", sha256)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rewrite the bats pin.")
    parser.add_argument("tag", help="upstream release tag, e.g. v1.14.0")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="keep the tag and bump the packaging component of the version",
    )
    parser.add_argument("--sha256", help="tarball sha256; downloaded when omitted")
    parser.add_argument("--pyproject", type=Path, default=fetch_bats.DEFAULT_PYPROJECT)
    args = parser.parse_args(argv)

    pin = fetch_bats.read_pin(args.pyproject)
    if args.rebuild:
        if args.tag != pin.tag:
            print(f"--rebuild requires the current tag {pin.tag}", file=sys.stderr)
            return 2
        version = next_rebuild(pin.version)
    else:
        version = version_from_tag(args.tag)
    sha256 = args.sha256 or tarball_sha256(args.tag)

    text = args.pyproject.read_text()
    args.pyproject.write_text(rewrite_pin(text, version, args.tag, sha256))

    print(version)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"version={version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
