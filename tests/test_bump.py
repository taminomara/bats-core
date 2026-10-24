from __future__ import annotations

import difflib
from pathlib import Path

import pytest

import bump
from fetch_bats import Pin, read_pin

PYPROJECT = """\
[project]
name = "bats-core"
version = "1.14.0"
description = "Bash Automated Testing System (bats-core), packaged for pip"

[tool.bats-core]
tag = "v1.14.0"
sha256 = "{sha}"

[tool.other]
    version = "indented, must not match"
""".format(sha="c" * 64)


@pytest.fixture
def pyproject(tmp_path: Path) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT)
    return path


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


def test_rewrite_pin_touches_only_three_lines():
    new = bump.rewrite_pin(PYPROJECT, "1.15.0", "v1.15.0", "d" * 64)

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
            f'-sha256 = "{"c" * 64}"',
            f'+sha256 = "{"d" * 64}"',
        ]
    )


def test_rewrite_pin_refuses_ambiguous():
    text = PYPROJECT + '\n[tool.dup]\nversion = "9.9.9"\n'

    with pytest.raises(ValueError, match="version"):
        bump.rewrite_pin(text, "1.15.0", "v1.15.0", "d" * 64)


def test_main_new_tag(pyproject, monkeypatch, capsys):
    monkeypatch.setattr(bump, "tarball_sha256", lambda tag: "a" * 64)

    rc = bump.main(["v1.15.0", "--pyproject", str(pyproject)])

    assert rc == 0
    assert read_pin(pyproject) == Pin("1.15.0", "v1.15.0", "a" * 64)
    assert capsys.readouterr().out.strip() == "1.15.0"


def test_main_rebuild_keeps_tag(pyproject):
    rc = bump.main(
        ["v1.14.0", "--rebuild", "--sha256", "b" * 64, "--pyproject", str(pyproject)]
    )

    assert rc == 0
    assert read_pin(pyproject) == Pin("1.14.0.1", "v1.14.0", "b" * 64)


def test_main_rebuild_requires_current_tag(pyproject, capsys):
    rc = bump.main(
        ["v1.15.0", "--rebuild", "--sha256", "b" * 64, "--pyproject", str(pyproject)]
    )

    assert rc == 2
    assert "v1.14.0" in capsys.readouterr().err
    assert read_pin(pyproject) == Pin("1.14.0", "v1.14.0", "c" * 64)


def test_main_writes_github_output(pyproject, tmp_path, monkeypatch):
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    bump.main(["v1.15.0", "--sha256", "a" * 64, "--pyproject", str(pyproject)])

    assert output.read_text() == "version=1.15.0\n"
