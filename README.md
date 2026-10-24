# bats-core

[bats-core](https://github.com/bats-core/bats-core), the Bash Automated
Testing System, packaged for pip. Installing this package gives you a `bats`
executable that runs the bundled upstream release unchanged. It is POSIX-only
and needs bash 3.2 or newer, exactly like upstream.

## Install

```sh
pip install bats-core
uv tool install bats-core
uvx --from bats-core bats --version
```

## Versioning

The package version is the bats version: `bats-core==1.14.0` bundles bats
v1.14.0. Packaging-only rebuilds add a fourth component (`1.14.0.1`,
`1.14.0.2`). To track a bats release including rebuilds, pin with
`bats-core==1.14.0.*`.

## Development

The upstream runtime tree is not committed. `scripts/fetch_bats.py` downloads
the release tarball pinned in `pyproject.toml` under `[tool.bats-core]`,
verifies its SHA-256, and unpacks `bin/`, `libexec/`, `lib/` and `LICENSE.md`
into `src/bats_core/_bats/` (gitignored). A hatchling build hook refuses to
build a wheel or sdist when that directory is missing or its version does not
match `project.version`.

This repo uses [`uv`](https://docs.astral.sh/uv/) for dependency management,
[`tox`](https://tox.wiki/) (via `tox-uv`) for the test matrix, and
[`prek`](https://github.com/j178/prek) (a pre-commit-compatible runner) for
linting. [`poe`](https://poethepoet.natn.io/) is an optional task wrapper.
Install `uv` first, then:

```sh
# Install / sync the dev environment
uv sync

# Fetch the pinned bats release and build sdist + wheel into dist/
uv run poe build

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

tox builds `dist/` once through `scripts/build.py` and installs that wheel
into every Python environment, so the smoke tests exercise the artifact that
gets published.

## Release process

Releases are automatic. `.github/workflows/update.yml` runs daily:

1. `scripts/check_upstream.py` compares the latest upstream release with the
   pin and checks whether PyPI already has the matching version.
2. If a bump is due, `scripts/bump.py` rewrites the pin on a branch
   `bump/<version>` and `ci.yml` runs the full matrix against it.
3. On green, the workflow fast-forwards `main`, tags `v<version>`, publishes
   `dist/` to PyPI through Trusted Publishing, and creates a GitHub release.
4. On red, it opens a pull request from the bump branch with a link to the
   failed run. The branch stays until a human merges or deletes it; while it
   exists, later scheduled runs skip that version instead of opening
   duplicates. Pull requests opened by the workflow token do not trigger
   `ci.yml` by themselves; re-run CI manually after fixing.
5. If the publish job itself fails after `main` was updated, the workflow
   opens an issue instead. Every publish step is idempotent, so the next
   scheduled run (or a manual dispatch) retries the release.

Run the workflow by hand from the Actions tab to publish early, target a
specific `tag`, or publish a packaging `rebuild` of the current pin.

### One-time setup

- Register a pending publisher for the `bats-core` project on PyPI with owner
  `taminomara`, repository `bats-core`, workflow `update.yml`, environment
  `pypi`.
- Create the `pypi` environment in the repository settings.
- Enable "Allow GitHub Actions to create and approve pull requests" under
  Settings → Actions → General. Without it the on-red path cannot open its
  pull request.
- Dispatch `update.yml` once with no inputs to publish the current pin.
- The publish job pushes to `main` directly. If branch protection is ever
  enabled on `main`, change that step to merge through a pull request with
  auto-merge.

## License

The packaging code is MIT licensed (see `LICENSE`). bats-core is MIT licensed
by its authors; its `LICENSE.md` ships inside the wheel under
`bats_core/_bats/`.
