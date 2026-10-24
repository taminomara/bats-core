"""Clean dist/, fetch the pinned bats release, and build sdist + wheel.

With BATS_CORE_PREBUILT set and exactly one wheel already in dist/, nothing
is fetched or built: CI builds once and hands the same wheel to every test
job.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import fetch_bats

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> int:
    if os.environ.get("BATS_CORE_PREBUILT"):
        wheels = sorted(DIST.glob("*.whl")) if DIST.is_dir() else []
        if len(wheels) == 1:
            print(f"Using prebuilt {wheels[0].name}")
            return 0
        if wheels:
            print(
                f"BATS_CORE_PREBUILT is set but {DIST} must hold exactly one wheel, "
                f"found {len(wheels)}",
                file=sys.stderr,
            )
            return 2
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
