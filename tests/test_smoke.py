"""Smoke tests against the installed `bats` console script."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import bats_core
from hatch_build import base_version

DATA = Path(__file__).parent / "data"
EXPECTED_VERSION = f"Bats {base_version(bats_core.__version__)}"


def run_bats(*args: str | Path) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("bats")
    assert exe is not None, "bats console script is not on PATH"
    return subprocess.run([exe, *map(str, args)], capture_output=True, text=True)


def test_version():
    assert run_bats("--version").stdout.strip() == EXPECTED_VERSION


def test_python_m_version():
    result = subprocess.run(
        [sys.executable, "-m", "bats_core", "--version"], capture_output=True, text=True
    )
    assert result.stdout.strip() == EXPECTED_VERSION


def test_passing_file_tap():
    result = run_bats("--formatter", "tap", DATA / "passing.bats")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["1..1", "ok 1 addition"]


def test_failing_file_tap():
    result = run_bats("--formatter", "tap", DATA / "failing.bats")
    assert result.returncode == 1
    assert "not ok 1 fails" in result.stdout


def test_junit_formatter():
    result = run_bats("--formatter", "junit", DATA / "passing.bats")
    assert result.returncode == 0
    assert "<testsuites" in result.stdout


def test_args_with_spaces_pass_through():
    result = run_bats("--formatter", "tap", DATA / "with helper.bats")
    assert result.returncode == 0
    assert "ok 1 helper" in result.stdout


def test_file_hooks_run():
    result = run_bats("--formatter", "tap", DATA / "file_hooks.bats")
    assert result.returncode == 0
    assert "setup_file ran" in result.stdout
    assert "teardown_file ran" in result.stdout
