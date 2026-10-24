from __future__ import annotations

import difflib
from pathlib import Path

import pytest

import bump
from fetch_bats import Pin, read_pin

COMMIT = "d" * 40
NEW_COMMIT = "a" * 40

PYPROJECT = """\
[project]
name = "bats-core"
version = "1.14.0"
description = "Bash Automated Testing System (bats-core), packaged for pip"

[tool.bats-core]
tag = "v1.14.0"
commit = "{commit}"
sha256 = "{sha}"

[tool.other]
    version = "indented, must not match"
""".format(commit=COMMIT, sha="c" * 64)


@pytest.fixture
def pyproject(tmp_path: Path) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT)
    return path


def fake_github(responses: dict[str, dict]):
    def github_get(path: str) -> dict:
        return responses[path]

    return github_get


def test_version_from_tag():
    assert bump.version_from_tag("v1.14.0") == "1.14.0"


@pytest.mark.parametrize("tag", ["v1.15.0-RC1", "1.14.0", "v1.14", "v1.14.0.1"])
def test_version_from_tag_rejects_prerelease(tag):
    with pytest.raises(bump.InvalidTag):
        bump.version_from_tag(tag)


@pytest.mark.parametrize(
    ("current", "nxt"),
    [("1.14.0", "1.14.0.1"), ("1.14.0.1", "1.14.0.2"), ("1.14.0.9", "1.14.0.10")],
)
def test_next_rebuild(current, nxt):
    assert bump.next_rebuild(current) == nxt


def test_resolve_tag_lightweight(monkeypatch):
    monkeypatch.setattr(
        bump,
        "github_get",
        fake_github(
            {"/git/ref/tags/v1.13.0": {"object": {"type": "commit", "sha": NEW_COMMIT}}}
        ),
    )

    assert bump.resolve_tag("v1.13.0") == bump.TagInfo(NEW_COMMIT, False, None)


def test_resolve_tag_annotated_signed_valid(monkeypatch):
    monkeypatch.setattr(
        bump,
        "github_get",
        fake_github(
            {
                "/git/ref/tags/v1.14.0": {"object": {"type": "tag", "sha": "7" * 40}},
                "/git/tags/" + "7" * 40: {
                    "object": {"type": "commit", "sha": NEW_COMMIT},
                    "verification": {
                        "verified": True,
                        "reason": "valid",
                        "signature": "-----BEGIN PGP SIGNATURE-----",
                    },
                },
            }
        ),
    )

    assert bump.resolve_tag("v1.14.0") == bump.TagInfo(NEW_COMMIT, True, True)


def test_resolve_tag_annotated_unsigned(monkeypatch):
    monkeypatch.setattr(
        bump,
        "github_get",
        fake_github(
            {
                "/git/ref/tags/v1.14.0": {"object": {"type": "tag", "sha": "7" * 40}},
                "/git/tags/" + "7" * 40: {
                    "object": {"type": "commit", "sha": NEW_COMMIT},
                    "verification": {
                        "verified": False,
                        "reason": "unsigned",
                        "signature": None,
                    },
                },
            }
        ),
    )

    assert bump.resolve_tag("v1.14.0") == bump.TagInfo(NEW_COMMIT, False, None)


def test_rewrite_pin_touches_only_four_lines():
    new = bump.rewrite_pin(PYPROJECT, "1.15.0", "v1.15.0", NEW_COMMIT, "e" * 64)

    changed = [
        line
        for line in difflib.unified_diff(PYPROJECT.splitlines(), new.splitlines(), n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]
    assert sorted(changed) == sorted(
        [
            '-version = "1.14.0"',
            '+version = "1.15.0"',
            '-tag = "v1.14.0"',
            '+tag = "v1.15.0"',
            f'-commit = "{COMMIT}"',
            f'+commit = "{NEW_COMMIT}"',
            f'-sha256 = "{"c" * 64}"',
            f'+sha256 = "{"e" * 64}"',
        ]
    )


def test_rewrite_pin_refuses_ambiguous():
    text = PYPROJECT + '\n[tool.dup]\nversion = "9.9.9"\n'

    with pytest.raises(ValueError, match="version"):
        bump.rewrite_pin(text, "1.15.0", "v1.15.0", NEW_COMMIT, "e" * 64)


def test_main_new_tag(pyproject, monkeypatch, capsys):
    monkeypatch.setattr(
        bump, "resolve_tag", lambda tag: bump.TagInfo(NEW_COMMIT, True, True)
    )
    monkeypatch.setattr(bump, "tarball_sha256", lambda commit: "a" * 64)

    rc = bump.main(["v1.15.0", "--pyproject", str(pyproject)])

    assert rc == 0
    assert read_pin(pyproject) == Pin("1.15.0", "v1.15.0", NEW_COMMIT, "a" * 64)
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1] == "1.15.0"
    assert "::warning::" not in out


def test_main_refuses_unverified_signature(pyproject, monkeypatch, capsys):
    monkeypatch.setattr(
        bump, "resolve_tag", lambda tag: bump.TagInfo(NEW_COMMIT, True, False)
    )
    monkeypatch.setattr(bump, "tarball_sha256", lambda commit: "a" * 64)

    rc = bump.main(["v1.15.0", "--pyproject", str(pyproject)])

    assert rc == 3
    assert "signature" in capsys.readouterr().err
    assert read_pin(pyproject) == Pin("1.14.0", "v1.14.0", COMMIT, "c" * 64)


def test_main_warns_on_unsigned_tag(pyproject, monkeypatch, capsys):
    monkeypatch.setattr(
        bump, "resolve_tag", lambda tag: bump.TagInfo(NEW_COMMIT, False, None)
    )
    monkeypatch.setattr(bump, "tarball_sha256", lambda commit: "a" * 64)

    rc = bump.main(["v1.15.0", "--pyproject", str(pyproject)])

    assert rc == 0
    assert "::warning::" in capsys.readouterr().out
    assert read_pin(pyproject).commit == NEW_COMMIT


def test_main_commit_override_skips_resolve(pyproject, monkeypatch):
    def boom(tag):
        raise AssertionError("must not call GitHub")

    monkeypatch.setattr(bump, "resolve_tag", boom)

    rc = bump.main(
        [
            "v1.15.0",
            "--commit",
            NEW_COMMIT,
            "--sha256",
            "a" * 64,
            "--pyproject",
            str(pyproject),
        ]
    )

    assert rc == 0
    assert read_pin(pyproject) == Pin("1.15.0", "v1.15.0", NEW_COMMIT, "a" * 64)


def test_main_rebuild_keeps_tag_and_commit(pyproject, monkeypatch):
    def boom(tag):
        raise AssertionError("rebuild must not resolve the tag")

    monkeypatch.setattr(bump, "resolve_tag", boom)

    rc = bump.main(
        ["v1.14.0", "--rebuild", "--sha256", "b" * 64, "--pyproject", str(pyproject)]
    )

    assert rc == 0
    assert read_pin(pyproject) == Pin("1.14.0.1", "v1.14.0", COMMIT, "b" * 64)


def test_main_rebuild_requires_current_tag(pyproject, capsys):
    rc = bump.main(
        ["v1.15.0", "--rebuild", "--sha256", "b" * 64, "--pyproject", str(pyproject)]
    )

    assert rc == 2
    assert "v1.14.0" in capsys.readouterr().err
    assert read_pin(pyproject) == Pin("1.14.0", "v1.14.0", COMMIT, "c" * 64)


def test_main_writes_github_output(pyproject, tmp_path, monkeypatch):
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    bump.main(
        [
            "v1.15.0",
            "--commit",
            NEW_COMMIT,
            "--sha256",
            "a" * 64,
            "--pyproject",
            str(pyproject),
        ]
    )

    assert output.read_text() == "version=1.15.0\n"


def test_main_same_tag_without_rebuild_keeps_the_pin(tmp_path, monkeypatch, capsys):
    # The scheduled retry path after an unpublished rebuild: detect proceeds
    # with the four-part pin version; bump must not reset it to the tag.
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        PYPROJECT.replace('version = "1.14.0"', 'version = "1.14.0.1"')
    )

    def boom(*args):
        raise AssertionError("same-tag re-pin must not touch the network")

    monkeypatch.setattr(bump, "resolve_tag", boom)
    monkeypatch.setattr(bump, "tarball_sha256", boom)

    rc = bump.main(["v1.14.0", "--pyproject", str(pyproject)])

    assert rc == 0
    assert read_pin(pyproject) == Pin("1.14.0.1", "v1.14.0", COMMIT, "c" * 64)
    assert capsys.readouterr().out.strip() == "1.14.0.1"


def test_main_rebuild_keeps_recorded_sha(pyproject, monkeypatch):
    def boom(commit):
        raise AssertionError("a rebuild must reuse the recorded hash")

    monkeypatch.setattr(bump, "tarball_sha256", boom)
    monkeypatch.setattr(bump, "resolve_tag", boom)

    rc = bump.main(["v1.14.0", "--rebuild", "--pyproject", str(pyproject)])

    assert rc == 0
    assert read_pin(pyproject) == Pin("1.14.0.1", "v1.14.0", COMMIT, "c" * 64)


def test_main_same_tag_new_commit_hashes_the_new_archive(pyproject, monkeypatch):
    hashed: list[str] = []

    def tarball_sha256(commit: str) -> str:
        hashed.append(commit)
        return "a" * 64

    monkeypatch.setattr(bump, "tarball_sha256", tarball_sha256)

    rc = bump.main(["v1.14.0", "--commit", NEW_COMMIT, "--pyproject", str(pyproject)])

    assert rc == 0
    assert hashed == [NEW_COMMIT]
    assert read_pin(pyproject) == Pin("1.14.0", "v1.14.0", NEW_COMMIT, "a" * 64)
