from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

import bats_core.__main__


@pytest.fixture
def fake_exe(tmp_path: Path) -> Path:
    exe = tmp_path / "bin" / "bats"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    return exe


@pytest.fixture
def execv_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(os, "execv", lambda path, argv: calls.append((path, argv)))
    return calls


def test_main_execs_bundled_bats(monkeypatch, fake_exe, execv_calls):
    monkeypatch.setattr(bats_core.__main__, "BATS_EXE", fake_exe)

    assert bats_core.__main__.main(["--version"]) == 0

    assert execv_calls == [(str(fake_exe), [str(fake_exe), "--version"])]


def test_main_restores_exec_bit(monkeypatch, fake_exe, execv_calls):
    fake_exe.chmod(0o644)
    monkeypatch.setattr(bats_core.__main__, "BATS_EXE", fake_exe)

    assert bats_core.__main__.main([]) == 0

    assert fake_exe.stat().st_mode & stat.S_IXUSR
    assert len(execv_calls) == 1


def test_main_missing_bundle_exits_127(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(bats_core.__main__, "BATS_EXE", tmp_path / "missing" / "bats")

    assert bats_core.__main__.main([]) == 127

    assert "missing/bats" in capsys.readouterr().err
