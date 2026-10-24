"""bats_core — Bash Automated Testing System (bats-core), packaged for pip"""

from __future__ import annotations

__all__: list[str] = []

try:
    from ._version import *  # noqa: F403
except ImportError:
    raise ImportError(
        "can't find bats_core/_version.py; "
        "if you're using development build, "
        "make sure the package is installed properly"
    )
