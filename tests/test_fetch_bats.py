from __future__ import annotations

import hashlib
import io
import shutil
import tarfile
from pathlib import Path

import pytest

import fetch_bats

# The top-level directory deliberately differs from the upstream
# "bats-core-<version>" so extraction cannot rely on that name.
TOP = "bats-core-xyz"

RUNTIME_FILES = {
    "bin/bats": ("#!/usr/bin/env bash\n", 0o755),
    "libexec/bats-core/bats": ("export BATS_VERSION='1.14.0'\n", 0o755),
    "lib/bats-core/common.bash": ("bats_common() { :; }\n", 0o644),
    "LICENSE.md": ("MIT\n", 0o644),
}
EXTRA_FILES = {
    "README.md": ("readme\n", 0o644),
    "test/foo.bats": ("@test x { true; }\n", 0o644),
    "docs/x.md": ("docs\n", 0o644),
    "man/bats.1": ("man\n", 0o644),
}


def _add_file(tar: tarfile.TarFile, name: str, content: str, mode: int) -> None:
    data = content.encode()
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))


def make_tarball(path: Path, files: dict[str, tuple[str, int]], top: str = TOP) -> str:
    with tarfile.open(path, "w:gz") as tar:
        for name, (content, mode) in files.items():
            _add_file(tar, f"{top}/{name}", content, mode)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fake_tarball(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "fixture.tar.gz"
    digest = make_tarball(path, {**RUNTIME_FILES, **EXTRA_FILES})
    return path, digest


def write_pyproject(path: Path, version: str, tag: str, sha256: str) -> Path:
    path.write_text(
        "[project]\n"
        'name = "bats-core"\n'
        f'version = "{version}"\n'
        "\n"
        "[tool.bats-core]\n"
        f'tag = "{tag}"\n'
        f'sha256 = "{sha256}"\n'
    )
    return path


def patch_download(monkeypatch: pytest.MonkeyPatch, source: Path) -> list[str]:
    urls: list[str] = []

    def fake_download(url: str, dest: Path) -> None:
        urls.append(url)
        shutil.copy(source, dest)

    monkeypatch.setattr(fetch_bats, "download", fake_download)
    return urls


def test_read_pin(tmp_path):
    pyproject = write_pyproject(
        tmp_path / "pyproject.toml", "1.14.0.1", "v1.14.0", "ab" * 32
    )

    assert fetch_bats.read_pin(pyproject) == fetch_bats.Pin(
        "1.14.0.1", "v1.14.0", "ab" * 32
    )


def test_extract_runtime_keeps_only_runtime_paths(fake_tarball, tmp_path):
    tarball, _ = fake_tarball
    dest = tmp_path / "out"

    fetch_bats.extract_runtime(tarball, dest)

    for name in RUNTIME_FILES:
        assert (dest / name).is_file(), name
    for name in EXTRA_FILES:
        assert not (dest / name).exists(), name
    assert (dest / "bin" / "bats").stat().st_mode & 0o111


def test_extract_runtime_replaces_previous_contents(fake_tarball, tmp_path):
    tarball, _ = fake_tarball
    dest = tmp_path / "out"
    stale = dest / "bin" / "stale"
    stale.parent.mkdir(parents=True)
    stale.write_text("old\n")

    fetch_bats.extract_runtime(tarball, dest)

    assert not stale.exists()
    assert (dest / "bin" / "bats").is_file()


@pytest.mark.parametrize(
    "name", [f"{TOP}/../evil", "/abs/evil", f"{TOP}/bin/../../evil"]
)
def test_extract_runtime_rejects_traversal(name, tmp_path):
    tarball = tmp_path / "evil.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        _add_file(tar, f"{TOP}/bin/bats", "#!/bin/sh\n", 0o755)
        _add_file(tar, name, "evil\n", 0o644)

    with pytest.raises(fetch_bats.UnsafeMember):
        fetch_bats.extract_runtime(tarball, tmp_path / "out")


def test_extract_runtime_rejects_symlinks(tmp_path):
    tarball = tmp_path / "link.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        _add_file(tar, f"{TOP}/bin/bats", "#!/bin/sh\n", 0o755)
        link = tarfile.TarInfo(f"{TOP}/bin/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)

    with pytest.raises(fetch_bats.UnsafeMember):
        fetch_bats.extract_runtime(tarball, tmp_path / "out")


def test_main_hash_mismatch_writes_nothing(fake_tarball, tmp_path, monkeypatch, capsys):
    tarball, digest = fake_tarball
    patch_download(monkeypatch, tarball)
    pyproject = write_pyproject(
        tmp_path / "pyproject.toml", "1.14.0", "v1.14.0", "0" * 64
    )
    dest = tmp_path / "dest"

    rc = fetch_bats.main(["--pyproject", str(pyproject), "--dest", str(dest)])

    assert rc == 1
    assert not dest.exists()
    err = capsys.readouterr().err
    assert "0" * 64 in err
    assert digest in err


def test_main_happy_path(fake_tarball, tmp_path, monkeypatch, capsys):
    tarball, digest = fake_tarball
    urls = patch_download(monkeypatch, tarball)
    pyproject = write_pyproject(
        tmp_path / "pyproject.toml", "1.14.0", "v1.14.0", digest
    )
    dest = tmp_path / "dest"

    rc = fetch_bats.main(["--pyproject", str(pyproject), "--dest", str(dest)])

    assert rc == 0
    assert (dest / "bin" / "bats").is_file()
    assert urls == [
        "https://github.com/bats-core/bats-core/archive/refs/tags/v1.14.0.tar.gz"
    ]
    assert "v1.14.0" in capsys.readouterr().out


def test_main_print_sha256(fake_tarball, tmp_path, monkeypatch, capsys):
    tarball, digest = fake_tarball
    urls = patch_download(monkeypatch, tarball)
    pyproject = write_pyproject(
        tmp_path / "pyproject.toml", "1.14.0", "v1.14.0", "0" * 64
    )
    dest = tmp_path / "dest"

    rc = fetch_bats.main(
        [
            "--pyproject",
            str(pyproject),
            "--dest",
            str(dest),
            "--tag",
            "v9.9.9",
            "--print-sha256",
        ]
    )

    assert rc == 0
    assert capsys.readouterr().out.strip() == digest
    assert urls == [
        "https://github.com/bats-core/bats-core/archive/refs/tags/v9.9.9.tar.gz"
    ]
    assert not dest.exists()
