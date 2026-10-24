"""Clean dist/, fetch the pinned bats release, and build sdist + wheel."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import fetch_bats

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> int:
    shutil.rmtree(DIST, ignore_errors=True)
    rc = fetch_bats.main([])
    if rc != 0:
        return rc
    uv = shutil.which("uv")
    if uv is None:
        print("uv not found on PATH", file=sys.stderr)
        return 2
    subprocess.run([uv, "build", "--out-dir", str(DIST)], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
