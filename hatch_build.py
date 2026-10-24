"""Hatchling build hook; the bundle check is added in a later task."""

from __future__ import annotations

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class BatsBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        pass
