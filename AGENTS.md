# Agent context — bats-core

This package bundles a pinned [bats-core](https://github.com/bats-core/bats-core)
release, fetched by `scripts/fetch_bats.py` at build time, and exposes its
`bats` executable as a console script. `project.version` in `pyproject.toml`
mirrors the bundled bats version; the pin (`tag`, `sha256`) lives in
`[tool.bats-core]` in the same file.

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
  `coverage-clean` / `coverage-combine` helpers.
- Task wrapper: **`poe`** (poethepoet) — recommended convenience layer, in
  `[dependency-groups].dev`, so `uv run poe …` after a sync. Tasks in
  `poe_tasks.toml` mostly delegate to tox envs.
- Lint/pre-commit: **`prek`** (a pre-commit-compatible runner — config in
  `.pre-commit-config.yaml`).

## Common commands

```sh
# Install / sync the dev environment
uv sync

# Lint (ruff + standard hygiene hooks)
uv run poe lint     # or: uv run tox -e lint

# Type check (ty)
uv run poe type     # or: uv run tox -e type

# Tests on Python 3.14 with combined coverage
uv run poe test     # or: uv run tox -e 3.14,coverage-combine

# Full Python matrix + lint + type + coverage combine
uv run poe test-all # or: uv run tox p

# Pass pytest flags through to the underlying pytest invocation
uv run poe test -- -k test_name -v
uv run poe test-all -- -x --lf
```

Anything after `--` in a poe `test` / `test-all` invocation is forwarded
to pytest via tox's `posargs` substitution.

`pytest.toml` configures pytest (`--strict-markers`); it takes precedence
over any `[tool.pytest.ini_options]` in `pyproject.toml`.

## Layout

- `src/bats_core/__main__.py` — the `bats` console script; execs the bundled
  `_bats/bin/bats`.
- `scripts/fetch_bats.py` — downloads the pinned tarball, verifies SHA-256,
  unpacks the runtime tree into `src/bats_core/_bats/`.
- `scripts/build.py` — cleans `dist/`, fetches, runs `uv build`. The only way
  `dist/` is produced (poe `build`, the tox package env, CI).
- `scripts/bump.py` — rewrites `version`, `tag` and `sha256` in
  `pyproject.toml` for a new upstream tag or a packaging rebuild.
- `scripts/check_upstream.py` — the update workflow's detect step; decides
  whether a bump is due and writes the decision to `$GITHUB_OUTPUT`.
- `hatch_build.py` — hatchling hook that refuses to build without a bundle
  matching `project.version`.
- `tests/test_smoke.py` runs against the installed wheel; the other tests are
  offline and import the scripts directly (`pytest.toml` adds `scripts/` to
  `pythonpath`).

## Releases

Automated by `.github/workflows/update.yml`; see the README's release
process. Nothing is tagged or published by hand.

## Conventions worth knowing

- Don't bypass pre-commit hooks (`--no-verify`, etc.) — CI runs the same
  `prek` config, so anything you skip locally fails there.
- SDD-related documents (superpowers, gsd, han) live in `docs/plans/feature-name/{spec|plan|...}.md`.
