# Agent context — bats-core

This package bundles a pinned [bats-core](https://github.com/bats-core/bats-core)
release, fetched by `scripts/fetch_bats.py` at build time, and exposes its
`bats` executable as a console script. `project.version` in `pyproject.toml`
mirrors the bundled bats version; the pin (`tag`, `sha256`) lives in
`[tool.bats-core]` in the same file. The bundle under `src/bats_core/_bats/`
is gitignored and must never be committed.

`CONTRIBUTING.md` is the source of truth for the file layout, the release
workflow, backports, dependency updates and the one-time GitHub/PyPI setup.
`README.md` is the PyPI landing page and stays user-facing.

## Tooling

- Python **3.14** for development (pinned in `.python-version`). The project
  supports **3.10+** (`requires-python` in `pyproject.toml`); the
  tox matrix exercises every supported version from `3.10` to `3.14`.
- Dependencies managed by **`uv`**. Use `uv add` / `uv sync`, never
  `pip install`. Dev deps live in `[dependency-groups].dev`. `uv.lock` is
  committed and CI installs from it with `uv sync --frozen`, so any
  dependency change must land together with the regenerated lock.
- Test orchestration: **`tox`** (with `tox-uv`). Envs defined in `tox.toml`:
  per-Python test envs (`3.10` … `3.14`), `lint`, `type`, plus
  `coverage-clean` / `coverage-combine` helpers. The package env builds
  `dist/` via `scripts/build.py` and every Python env installs that wheel.
- Task wrapper: **`poe`** (poethepoet) — tasks in `poe_tasks.toml` mostly
  delegate to tox envs; `poe build` produces `dist/`.
- Lint/pre-commit: **`prek`** (a pre-commit-compatible runner — config in
  `.pre-commit-config.yaml`).

## Common commands

```sh
uv sync                 # dev environment
uv run poe build        # fetch pinned bats, build sdist + wheel
uv run poe lint         # or: uv run tox -e lint
uv run poe type         # or: uv run tox -e type
uv run poe test         # 3.14 with coverage
uv run poe test-all     # full matrix + lint + type
uv run poe test -- -k test_name -v   # pytest flags pass through
```

`pytest.toml` configures pytest (`--strict-markers`, `pythonpath` for
`scripts/` and the repo root); it takes precedence over any
`[tool.pytest.ini_options]` in `pyproject.toml`.

## Conventions worth knowing

- Nothing is tagged or published by hand; `.github/workflows/update.yml`
  does both. Never edit `project.version` or `[tool.bats-core]` directly,
  use `scripts/bump.py`.
- Don't bypass pre-commit hooks (`--no-verify`, etc.) — CI runs the same
  `prek` config, so anything you skip locally fails there.
- Every `subprocess.run` passes `check` explicitly; every assertion tests
  one thing (ruff's `PT`/`PLW` rules are enforced).
- SDD-related documents (superpowers, gsd, han) live in `docs/plans/feature-name/{spec|plan|...}.md`.
