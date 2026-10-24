from __future__ import annotations

import urllib.error
from email.message import Message
from pathlib import Path

import pytest

import check_upstream
from fetch_bats import Pin

PIN = Pin("1.14.0", "v1.14.0", "x" * 64)


def never(_: str) -> bool:
    return False


def always(_: str) -> bool:
    return True


def test_decide_new_release():
    d = check_upstream.decide(PIN, "v1.15.0", None, False, never, never)

    assert d.proceed
    assert (d.tag, d.version) == ("v1.15.0", "1.15.0")


def test_decide_up_to_date():
    d = check_upstream.decide(PIN, "v1.14.0", None, False, always, never)

    assert not d.proceed
    assert d.reason == "up to date"


def test_decide_initial_publish():
    d = check_upstream.decide(PIN, "v1.14.0", None, False, never, never)

    assert d.proceed
    assert (d.tag, d.version) == ("v1.14.0", "1.14.0")


def test_decide_rebuild():
    d = check_upstream.decide(PIN, "v1.14.0", None, True, always, never)

    assert d.proceed
    assert (d.tag, d.version) == ("v1.14.0", "1.14.0.1")


def test_decide_rebuild_wrong_tag():
    d = check_upstream.decide(PIN, "v1.15.0", None, True, never, never)

    assert not d.proceed
    assert "rebuild" in d.reason


def test_decide_tag_override_wins():
    d = check_upstream.decide(PIN, "v1.15.0", "v1.14.1", False, never, never)

    assert d.proceed
    assert (d.tag, d.version) == ("v1.14.1", "1.14.1")


def test_decide_branch_exists_blocks():
    d = check_upstream.decide(
        PIN, "v1.15.0", None, False, never, lambda name: name == "bump/1.15.0"
    )

    assert not d.proceed
    assert "bump/1.15.0" in d.reason


@pytest.fixture
def pyproject(tmp_path: Path) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\nversion = "1.14.0"\n\n[tool.bats-core]\ntag = "v1.14.0"\n'
        f'sha256 = "{"x" * 64}"\n'
    )
    return path


def test_main_writes_github_output(pyproject, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check_upstream, "latest_tag", lambda: "v1.15.0")
    monkeypatch.setattr(check_upstream, "pypi_has", never)
    monkeypatch.setattr(check_upstream, "branch_exists", never)
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    rc = check_upstream.main(["--pyproject", str(pyproject)])

    assert rc == 0
    lines = output.read_text().splitlines()
    assert "proceed=true" in lines
    assert "tag=v1.15.0" in lines
    assert "version=1.15.0" in lines
    assert "v1.15.0" in capsys.readouterr().out


def test_main_propagates_api_error(pyproject, tmp_path, monkeypatch):
    def boom() -> str:
        raise urllib.error.HTTPError("url", 403, "rate limited", Message(), None)

    monkeypatch.setattr(check_upstream, "latest_tag", boom)
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    with pytest.raises(urllib.error.HTTPError):
        check_upstream.main(["--pyproject", str(pyproject)])

    assert not output.exists() or "proceed=true" not in output.read_text()


def test_main_warns_when_not_proceeding(pyproject, monkeypatch, capsys):
    monkeypatch.setattr(check_upstream, "latest_tag", lambda: "v1.15.0")
    monkeypatch.setattr(check_upstream, "pypi_has", never)
    monkeypatch.setattr(check_upstream, "branch_exists", always)

    rc = check_upstream.main(["--pyproject", str(pyproject)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "bump/1.15.0" in out
