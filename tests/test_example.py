"""Smoke test so the matrix has at least one test to collect on fresh
checkout. Delete once you've added your own tests."""

from __future__ import annotations

import bats_core


def test_module_imports():
    assert bats_core.__version__
