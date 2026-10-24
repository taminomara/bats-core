"""Console entry point: hand control to the bundled ``bin/bats``."""

from __future__ import annotations

import os
import stat
import sys

from bats_core import BATS_EXE


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not BATS_EXE.is_file():
        print(f"bats: bundled executable not found at {BATS_EXE}", file=sys.stderr)
        return 127
    mode = BATS_EXE.stat().st_mode
    if not mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        BATS_EXE.chmod(mode | 0o755)
    os.execv(str(BATS_EXE), [str(BATS_EXE), *args])
    return 0


if __name__ == "__main__":
    sys.exit(main())
