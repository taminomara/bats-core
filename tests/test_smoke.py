"""Smoke tests against the installed `bats` console script."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import bats_core
from hatch_build import base_version

DATA = Path(__file__).parent / "data"
EXPECTED_VERSION = f"Bats {base_version(bats_core.__version__)}"


def run_bats(
    *args: str | Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("bats")
    assert exe is not None, "bats console script is not on PATH"
    return subprocess.run(
        [exe, *map(str, args)], capture_output=True, text=True, check=False, env=env
    )


def test_version():
    assert run_bats("--version").stdout.strip() == EXPECTED_VERSION


def test_python_m_version():
    result = subprocess.run(
        [sys.executable, "-m", "bats_core", "--version"],
        capture_output=True,
        text=True,
        check=False,
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


@pytest.mark.skipif(
    sys.platform != "darwin", reason="/bin/bash 3.2 ships only on macOS"
)
def test_runs_under_system_bash_3(tmp_path):
    # GitHub's macOS runners put Homebrew bash 5 first on PATH; shim `bash` to
    # /bin/bash so every `#!/usr/bin/env bash` in the bundle resolves to 3.2.
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "bash").symlink_to("/bin/bash")
    env = {**os.environ, "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"}

    bash_version = subprocess.run(
        ["bash", "-c", 'printf %s "$BASH_VERSION"'],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout
    assert bash_version.startswith("3."), bash_version

    version = run_bats("--version", env=env)
    assert version.stdout.strip() == EXPECTED_VERSION
    result = run_bats("--formatter", "tap", DATA / "with helper.bats", env=env)
    assert result.returncode == 0
    assert "ok 1 helper" in result.stdout


def test_install_path_with_space(tmp_path):
    wheels = sorted((Path(__file__).parents[1] / "dist").glob("*.whl"))
    if len(wheels) != 1:
        pytest.skip("needs exactly one wheel in dist/ (run `poe build`)")
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")
    venv = tmp_path / "dir with space" / "venv"
    subprocess.run([uv, "venv", "-q", str(venv)], check=True)
    subprocess.run(
        [uv, "pip", "install", "-q", "--python", str(venv), str(wheels[0])], check=True
    )
    bats = venv / "bin" / "bats"

    version = subprocess.run(
        [str(bats), "--version"], capture_output=True, text=True, check=False
    )
    assert version.stdout.strip() == EXPECTED_VERSION
    result = subprocess.run(
        [str(bats), "--formatter", "tap", str(DATA / "passing.bats")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["1..1", "ok 1 addition"]
