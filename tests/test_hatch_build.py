from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

import hatch_build


def make_bundle(root: Path, bats_version: str | None) -> Path:
    bats_dir = root / "_bats"
    (bats_dir / "bin").mkdir(parents=True)
    (bats_dir / "bin" / "bats").write_text("#!/usr/bin/env bash\n")
    if bats_version is not None:
        (bats_dir / "libexec" / "bats-core").mkdir(parents=True)
        (bats_dir / "libexec" / "bats-core" / "bats").write_text(
            f"#!/usr/bin/env bash\nexport BATS_VERSION='{bats_version}'\n"
        )
    return bats_dir


@pytest.mark.parametrize(
    ("version", "base"),
    [("1.14.0", "1.14.0"), ("1.14.0.1", "1.14.0"), ("1.14.0.12", "1.14.0")],
)
def test_base_version(version, base):
    assert hatch_build.base_version(version) == base


def test_check_bundle_missing_exe(tmp_path):
    with pytest.raises(hatch_build.BundleError, match="poe build"):
        hatch_build.check_bundle(tmp_path / "_bats", "1.14.0")


def test_check_bundle_version_mismatch(tmp_path):
    bats_dir = make_bundle(tmp_path, "1.13.0")

    with pytest.raises(hatch_build.BundleError) as exc:
        hatch_build.check_bundle(bats_dir, "1.14.0")

    assert "1.13.0" in str(exc.value)
    assert "1.14.0" in str(exc.value)


def test_check_bundle_ok(tmp_path):
    bats_dir = make_bundle(tmp_path, "1.14.0")

    hatch_build.check_bundle(bats_dir, "1.14.0.1")


def test_bundled_version_reads_export_line(tmp_path):
    bats_dir = make_bundle(tmp_path, "1.14.0")

    assert hatch_build.bundled_version(bats_dir) == "1.14.0"


def test_bundled_version_missing_file(tmp_path):
    bats_dir = make_bundle(tmp_path, None)

    with pytest.raises(hatch_build.BundleError):
        hatch_build.bundled_version(bats_dir)


class FakeMetadata:
    def __init__(self, version: str) -> None:
        self.version = version


def make_hook(root: Path, version: str) -> hatch_build.BatsBuildHook:
    return hatch_build.BatsBuildHook(
        root=str(root),
        config={},
        build_config=cast("Any", None),
        metadata=cast("Any", FakeMetadata(version)),
        directory=str(root / "dist"),
        target_name="wheel",
    )


def test_hook_initialize_refuses_mismatched_bundle(tmp_path):
    make_bundle(tmp_path / "src" / "bats_core", "1.13.0")

    with pytest.raises(hatch_build.BundleError):
        make_hook(tmp_path, "1.14.0").initialize("standard", {})


def test_hook_initialize_accepts_matching_bundle_for_rebuild_version(tmp_path):
    make_bundle(tmp_path / "src" / "bats_core", "1.14.0")

    make_hook(tmp_path, "1.14.0.1").initialize("standard", {})


def test_hook_initialize_skips_editable_builds(tmp_path):
    make_hook(tmp_path, "1.14.0").initialize("editable", {})
