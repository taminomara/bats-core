"""Rewrite the bats pin in pyproject.toml for a new upstream tag or a rebuild.

Usage: bump.py TAG [--rebuild] [--commit SHA] [--sha256 HEX] [--pyproject FILE]

For a new tag the commit is resolved through the GitHub API. A tag that
carries a signature GitHub cannot verify is refused; an unsigned tag only
produces a workflow warning, since upstream has released both ways.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import fetch_bats

GITHUB_API = "https://api.github.com/repos/bats-core/bats-core"
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class InvalidTag(ValueError):
    pass


@dataclass(frozen=True)
class TagInfo:
    commit: str
    signed: bool
    verified: bool | None


def version_from_tag(tag: str) -> str:
    if not TAG_RE.match(tag):
        raise InvalidTag(f"{tag!r} is not a release tag of the form vX.Y.Z")
    return tag[1:]


def next_rebuild(version: str) -> str:
    parts = version.split(".")
    if len(parts) == 3:
        return f"{version}.1"
    return ".".join([*parts[:3], str(int(parts[3]) + 1)])


def github_get(path: str) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(GITHUB_API + path, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def resolve_tag(tag: str) -> TagInfo:
    ref = github_get(f"/git/ref/tags/{tag}")["object"]
    if ref["type"] == "commit":
        return TagInfo(ref["sha"], False, None)
    tag_object = github_get(f"/git/tags/{ref['sha']}")
    verification = tag_object.get("verification") or {}
    signed = bool(verification.get("signature"))
    return TagInfo(
        tag_object["object"]["sha"],
        signed,
        bool(verification.get("verified")) if signed else None,
    )


def tarball_sha256(commit: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return fetch_bats.sha256_of(fetch_bats.fetch_tarball(commit, Path(tmp)))


def _replace_line(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf'^{key} = "[^"]*"$', re.MULTILINE)
    if len(pattern.findall(text)) != 1:
        raise ValueError(f"expected exactly one top-level `{key} = ...` line")
    return pattern.sub(f'{key} = "{value}"', text)


def rewrite_pin(text: str, version: str, tag: str, commit: str, sha256: str) -> str:
    text = _replace_line(text, "version", version)
    text = _replace_line(text, "tag", tag)
    text = _replace_line(text, "commit", commit)
    return _replace_line(text, "sha256", sha256)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rewrite the bats pin.")
    parser.add_argument("tag", help="upstream release tag, e.g. v1.14.0")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="keep the tag and bump the packaging component of the version",
    )
    parser.add_argument(
        "--commit", help="tag's commit; resolved via GitHub when omitted"
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
        commit = pin.commit
    elif args.tag == pin.tag and not args.commit and not args.sha256:
        # Same tag, no rebuild: the retry and initial-publish path. Keep the
        # reviewed pin as is, including a four-part rebuild version.
        version, commit = pin.version, pin.commit
    else:
        version = version_from_tag(args.tag)
        if args.commit:
            commit = args.commit
        else:
            info = resolve_tag(args.tag)
            if info.signed and not info.verified:
                print(
                    f"{args.tag} carries a signature GitHub could not verify; refusing",
                    file=sys.stderr,
                )
                return 3
            if not info.signed:
                print(f"::warning::{args.tag} is not a signed tag")
            commit = info.commit
    # A rebuild and a same-tag re-pin reuse the recorded hash: the point of
    # the pin is that every build of a version sees identical bytes.
    if args.sha256:
        sha256 = args.sha256
    elif args.rebuild or (args.tag == pin.tag and not args.commit):
        sha256 = pin.sha256
    else:
        sha256 = tarball_sha256(commit)

    text = args.pyproject.read_text()
    args.pyproject.write_text(rewrite_pin(text, version, args.tag, commit, sha256))

    print(version)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"version={version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
