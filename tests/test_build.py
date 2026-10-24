from __future__ import annotations

from pathlib import Path

import pytest

import build
import fetch_bats


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setattr(build, "DIST", dist)
    return dist


@pytest.fixture
def no_build(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make any attempt to fetch or build visible and fatal."""
    calls: list[str] = []

    def fail(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("fetch/build must not run")

    monkeypatch.setattr(fetch_bats, "main", fail)
    monkeypatch.setattr(build.subprocess, "run", fail)
    return calls


def test_prebuilt_wheel_skips_fetch_and_build(dist, no_build, monkeypatch, capsys):
    (dist / "bats_core-1.14.0-py3-none-any.whl").write_bytes(b"")
    monkeypatch.setenv("BATS_CORE_PREBUILT", "1")

    assert build.main() == 0

    assert no_build == []
    assert "bats_core-1.14.0-py3-none-any.whl" in capsys.readouterr().out


def test_prebuilt_without_wheel_builds(dist, monkeypatch):
    monkeypatch.setenv("BATS_CORE_PREBUILT", "1")
    monkeypatch.setattr(fetch_bats, "main", lambda argv: 0)
    ran: list[list[str]] = []
    monkeypatch.setattr(
        build.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or None
    )
    monkeypatch.setattr(build.shutil, "which", lambda name: "/usr/bin/uv")

    assert build.main() == 0

    assert ran
    assert ran[0][:2] == ["/usr/bin/uv", "build"]


def test_prebuilt_with_two_wheels_refuses(dist, no_build, monkeypatch, capsys):
    (dist / "a-1.whl").write_bytes(b"")
    (dist / "b-2.whl").write_bytes(b"")
    monkeypatch.setenv("BATS_CORE_PREBUILT", "1")

    assert build.main() == 2

    assert "exactly one wheel" in capsys.readouterr().err


def test_unset_env_always_rebuilds(dist, monkeypatch):
    (dist / "stale.whl").write_bytes(b"")
    monkeypatch.delenv("BATS_CORE_PREBUILT", raising=False)
    monkeypatch.setattr(fetch_bats, "main", lambda argv: 0)
    ran: list[list[str]] = []
    monkeypatch.setattr(
        build.subprocess, "run", lambda cmd, **kw: ran.append(cmd) or None
    )
    monkeypatch.setattr(build.shutil, "which", lambda name: "/usr/bin/uv")

    assert build.main() == 0

    assert not (dist / "stale.whl").exists()
    assert ran


def test_failed_fetch_stops_the_build(dist, no_build, monkeypatch):
    monkeypatch.delenv("BATS_CORE_PREBUILT", raising=False)
    monkeypatch.setattr(fetch_bats, "main", lambda argv: 1)

    assert build.main() == 1

    assert no_build == []


def test_missing_uv_is_reported(dist, monkeypatch, capsys):
    monkeypatch.delenv("BATS_CORE_PREBUILT", raising=False)
    monkeypatch.setattr(fetch_bats, "main", lambda argv: 0)
    monkeypatch.setattr(build.shutil, "which", lambda name: None)

    assert build.main() == 2

    assert "uv not found" in capsys.readouterr().err
