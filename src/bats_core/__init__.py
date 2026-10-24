"""bats-core (Bash Automated Testing System), packaged for pip.

The upstream runtime tree lives under ``_bats/`` next to this file and is
fetched at build time by ``scripts/fetch_bats.py``.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

__all__ = ["BATS_EXE", "BATS_ROOT", "__version__"]

BATS_ROOT = Path(__file__).resolve().parent / "_bats"
BATS_EXE = BATS_ROOT / "bin" / "bats"
__version__ = importlib.metadata.version("bats-core")
