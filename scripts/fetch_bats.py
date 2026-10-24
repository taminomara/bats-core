"""Download the pinned bats-core release and unpack its runtime tree.

Usage: fetch_bats.py [--tag TAG] [--sha256 HEX] [--print-sha256]
                     [--dest DIR] [--pyproject FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # ty: ignore[unresolved-import]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYPROJECT = ROOT / "pyproject.toml"
DEFAULT_DEST = ROOT / "src" / "bats_core" / "_bats"

TARBALL_URL = "https://github.com/bats-core/bats-core/archive/refs/tags/{tag}.tar.gz"
RUNTIME_PATHS = ("bin/", "libexec/bats-core/", "lib/bats-core/", "LICENSE.md")


@dataclass(frozen=True)
class Pin:
    version: str
    tag: str
    sha256: str


class HashMismatch(Exception):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"sha256 mismatch: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


class UnsafeMember(Exception):
    pass


def read_pin(pyproject: Path) -> Pin:
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    pin = data["tool"]["bats-core"]
    return Pin(data["project"]["version"], pin["tag"], pin["sha256"])


def download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_tarball(tag: str, dest_dir: Path) -> Path:
    path = dest_dir / f"{tag}.tar.gz"
    download(TARBALL_URL.format(tag=tag), path)
    return path


def _relative_name(member: tarfile.TarInfo, top: str) -> PurePosixPath:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise UnsafeMember(member.name)
    if not path.parts or path.parts[0] != top:
        raise UnsafeMember(member.name)
    return PurePosixPath(*path.parts[1:])


def extract_runtime(tarball: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    with tarfile.open(tarball, "r:gz") as tar:
        members = tar.getmembers()
        top = PurePosixPath(members[0].name).parts[0]
        for member in members:
            rel = _relative_name(member, top)
            if not str(rel).startswith(RUNTIME_PATHS):
                continue
            # Upstream test fixtures contain symlinks; only extracted members
            # must be plain files or directories.
            if not member.isdir() and not member.isfile():
                raise UnsafeMember(member.name)
            target = dest / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            assert source is not None
            with source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            target.chmod(member.mode & 0o777)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the pinned bats-core release.")
    parser.add_argument("--tag", help="override the pinned tag")
    parser.add_argument("--sha256", help="override the pinned sha256")
    parser.add_argument(
        "--print-sha256",
        action="store_true",
        help="download, print the tarball sha256 and exit without extracting",
    )
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    args = parser.parse_args(argv)

    pin = read_pin(args.pyproject)
    tag = args.tag or pin.tag
    expected = args.sha256 or pin.sha256

    with tempfile.TemporaryDirectory() as tmp:
        tarball = fetch_tarball(tag, Path(tmp))
        actual = sha256_of(tarball)
        if args.print_sha256:
            print(actual)
            return 0
        if actual != expected:
            print(HashMismatch(expected, actual), file=sys.stderr)
            return 1
        extract_runtime(tarball, args.dest)

    print(f"Fetched bats {tag} into {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
