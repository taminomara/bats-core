from __future__ import annotations

import os
import subprocess
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path

import pytest

import check_upstream
from fetch_bats import Pin

PIN = Pin("1.14.0", "v1.14.0", "d" * 40, "x" * 64)
NOW = datetime(2026, 10, 24, 6, 17, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=30)


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


def test_decide_cooldown_blocks_fresh_release():
    d = check_upstream.decide(
        PIN,
        "v1.15.0",
        None,
        False,
        never,
        never,
        published_at=NOW - timedelta(days=1),
        now=NOW,
        cooldown_days=3,
    )

    assert not d.proceed
    assert "cooldown" in d.reason
    assert d.version == "1.15.0"


def test_decide_cooldown_passes_old_release():
    d = check_upstream.decide(
        PIN,
        "v1.15.0",
        None,
        False,
        never,
        never,
        published_at=NOW - timedelta(days=3, minutes=1),
        now=NOW,
        cooldown_days=3,
    )

    assert d.proceed


def test_decide_tag_override_skips_cooldown():
    d = check_upstream.decide(
        PIN,
        "v1.15.0",
        "v1.15.0",
        False,
        never,
        never,
        published_at=NOW,
        now=NOW,
        cooldown_days=3,
    )

    assert d.proceed


def test_decide_rebuild_ignores_cooldown():
    d = check_upstream.decide(
        PIN,
        "v1.14.0",
        None,
        True,
        always,
        never,
        published_at=NOW,
        now=NOW,
        cooldown_days=3,
    )

    assert d.proceed
    assert d.version == "1.14.0.1"


def test_parse_published_at():
    assert check_upstream.parse_published_at("2026-07-21T19:55:47Z") == datetime(
        2026, 7, 21, 19, 55, 47, tzinfo=timezone.utc
    )


@pytest.fixture
def pyproject(tmp_path: Path) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\nversion = "1.14.0"\n\n[tool.bats-core]\ntag = "v1.14.0"\n'
        f'commit = "{"d" * 40}"\nsha256 = "{"x" * 64}"\n'
    )
    return path


def test_main_writes_github_output(pyproject, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        check_upstream,
        "latest_release",
        lambda: check_upstream.Release("v1.15.0", OLD),
    )
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
    def boom() -> check_upstream.Release:
        raise urllib.error.HTTPError("url", 403, "rate limited", Message(), None)

    monkeypatch.setattr(check_upstream, "latest_release", boom)
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    with pytest.raises(urllib.error.HTTPError):
        check_upstream.main(["--pyproject", str(pyproject)])

    assert not output.exists() or "proceed=true" not in output.read_text()


def test_main_warns_when_not_proceeding(pyproject, monkeypatch, capsys):
    monkeypatch.setattr(
        check_upstream,
        "latest_release",
        lambda: check_upstream.Release("v1.15.0", OLD),
    )
    monkeypatch.setattr(check_upstream, "pypi_has", never)
    monkeypatch.setattr(check_upstream, "branch_exists", always)

    rc = check_upstream.main(["--pyproject", str(pyproject)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "bump/1.15.0" in out


def test_pypi_url():
    assert (
        check_upstream.pypi_url("1.14.0")
        == "https://pypi.org/pypi/bats-core/1.14.0/json"
    )


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(code: int):
    def urlopen(url):
        if code == 200:
            return FakeResponse()
        raise urllib.error.HTTPError(url, code, "error", Message(), None)

    return urlopen


def test_pypi_has_true_on_200(monkeypatch):
    monkeypatch.setattr(check_upstream.urllib.request, "urlopen", fake_urlopen(200))

    assert check_upstream.pypi_has("1.14.0") is True


def test_pypi_has_false_on_404(monkeypatch):
    monkeypatch.setattr(check_upstream.urllib.request, "urlopen", fake_urlopen(404))

    assert check_upstream.pypi_has("1.14.0") is False


def test_pypi_has_raises_on_other_errors(monkeypatch):
    monkeypatch.setattr(check_upstream.urllib.request, "urlopen", fake_urlopen(500))

    with pytest.raises(urllib.error.HTTPError):
        check_upstream.pypi_has("1.14.0")


def test_branch_exists_against_a_real_remote(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    clone = tmp_path / "clone"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=clone,
        env=env,
        check=True,
    )
    subprocess.run(
        ["git", "push", "-q", "origin", "HEAD:refs/heads/bump/1.15.0"],
        cwd=clone,
        check=True,
    )
    monkeypatch.chdir(clone)

    assert check_upstream.branch_exists("bump/1.15.0") is True
    assert check_upstream.branch_exists("bump/9.9.9") is False


def test_decide_refuses_downgrade_on_schedule():
    d = check_upstream.decide(
        PIN, "v1.11.2", None, False, never, never, published_at=OLD, now=NOW
    )

    assert not d.proceed
    assert "older" in d.reason


def test_decide_tag_override_allows_downgrade():
    d = check_upstream.decide(PIN, "v1.14.0", "v1.13.0", False, never, never)

    assert d.proceed
    assert d.version == "1.13.0"
