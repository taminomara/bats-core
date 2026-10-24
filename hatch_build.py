"""Hatchling build hook: refuse to build without a matching bats bundle."""

from __future__ import annotations

import re
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

VERSION_RE = re.compile(r"^export BATS_VERSION='([^']+)'", re.MULTILINE)


class BundleError(Exception):
    pass


def base_version(package_version: str) -> str:
    return ".".join(package_version.split(".")[:3])


def bundled_version(bats_dir: Path) -> str:
    launcher = bats_dir / "libexec" / "bats-core" / "bats"
    if not launcher.is_file():
        raise BundleError(f"{launcher} is missing; run `uv run poe build`")
    match = VERSION_RE.search(launcher.read_text())
    if match is None:
        raise BundleError(f"no BATS_VERSION line in {launcher}")
    return match.group(1)


def check_bundle(bats_dir: Path, package_version: str) -> None:
    if not (bats_dir / "bin" / "bats").is_file():
        raise BundleError(
            f"{bats_dir / 'bin' / 'bats'} is missing; run `uv run poe build` "
            "to fetch the pinned bats release before building"
        )
    bundled = bundled_version(bats_dir)
    expected = base_version(package_version)
    if bundled != expected:
        raise BundleError(
            f"bundled bats is {bundled} but project.version is {package_version} "
            f"(expects {expected}); run `uv run poe build` to re-fetch"
        )


class BatsBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return
        bats_dir = Path(self.root) / "src" / "bats_core" / "_bats"
        check_bundle(bats_dir, self.metadata.version)
