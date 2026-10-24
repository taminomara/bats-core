# bats-core on PyPI — design

## Goal

Publish [bats-core](https://github.com/bats-core/bats-core) as a PyPI package
named `bats-core`, so that `pip install bats-core` (or `uv tool install
bats-core`, `uvx --from bats-core bats`) gives a working `bats` executable.
The package tracks upstream releases automatically: a scheduled GitHub Actions
workflow detects a new bats release, rebuilds the package against it,
smoke-tests the result and publishes it without human intervention. A failing
smoke test produces a PR with the failure instead of a silent skip.

The git repository never contains bats source. The pinned release tarball is
downloaded from GitHub at build time and verified against a recorded SHA-256.

## Non-goals

- Windows support. bats requires bash; the package is POSIX-only and says so
  in classifiers and README.
- Pre-release bats versions (`-RC*`). Only non-prerelease GitHub releases are
  tracked.
- Man pages, docs, bats' own test suite. Only the runtime tree is shipped.
- Bundling companion libraries (`bats-support`, `bats-assert`, `bats-file`).

## Versioning

The PyPI version equals the bats version: bats `v1.14.0` is published as
`bats-core==1.14.0`. Packaging-only rebuilds append a fourth component:
`1.14.0.1`, `1.14.0.2`. Under PEP 440 these sort after `1.14.0` and before
`1.14.1`; `==1.14.0.*` matches all builds of one bats release.

Version-related state lives in exactly one file, `pyproject.toml`:

```toml
[project]
version = "1.14.0"

[tool.bats-core]
tag = "v1.14.0"
sha256 = "<sha256 of https://github.com/bats-core/bats-core/archive/refs/tags/v1.14.0.tar.gz>"
```

`project.version` is the package version; `tool.bats-core.tag` is the upstream
tag it bundles. They differ only by the `v` prefix and the optional fourth
component. The update bot rewrites exactly these three values and nothing else.

## Package layout

```
pyproject.toml
README.md
LICENSE                       # this repo's MIT license (packaging code)
hatch_build.py                # build guard, see below
src/bats_core/
  __init__.py                 # BATS_ROOT path constant, __version__
  __main__.py                 # entry point: exec bundled bin/bats
  _bats/                      # populated by scripts/fetch_bats.py, gitignored
    LICENSE.md                #   upstream MIT license, shipped in the wheel
    bin/bats
    libexec/bats-core/*
    lib/bats-core/*
scripts/fetch_bats.py         # download + verify + unpack
scripts/bump.py               # rewrite the pin; used by the update workflow
tests/
  unit/                       # tests for the scripts, offline
  smoke/                      # tests against an installed wheel
.github/workflows/
  ci.yml
  update.yml
```

Build backend: hatchling. The wheel is `py3-none-any`, `requires-python >= 3.9`.
No runtime dependencies. Dev tooling: `uv`, `pytest`, `ruff`.

### Entry point

`[project.scripts] bats = "bats_core.__main__:main"`. `main()` resolves
`<package dir>/_bats/bin/bats` and `os.execv`s it with `sys.argv[1:]`,
after making sure the file mode is executable (wheels preserve modes, but a
defensive `chmod` is cheap and some installers drop the bits). If the file is
missing, it prints a one-line error naming the path and exits with status 127.

No entry points are created for `libexec/bats-core/*`; those are internal to
bats and are found by `bin/bats` relative to its own location. That works
unchanged inside the package because `bin/bats` resolves `BATS_ROOT` with
`readlink -f` on its own path.

### What `fetch_bats.py` does

1. Read `tool.bats-core.tag` and `sha256` from `pyproject.toml` (stdlib
   `tomllib`; on Python < 3.11 fall back to `tomli`, a dev-only dependency).
2. Download `https://github.com/bats-core/bats-core/archive/refs/tags/<tag>.tar.gz`
   to a temporary file with `urllib`, following the redirect to `codeload`.
3. Compute SHA-256 and compare with the pin. On mismatch: delete the file,
   exit non-zero with both hashes printed.
4. Extract only `bin/`, `libexec/bats-core/`, `lib/bats-core/` and
   `LICENSE.md` from the tarball's single top-level directory into
   `src/bats_core/_bats/`, replacing any previous contents. Reject members
   with absolute paths, `..` components, or link types.
5. Print the tag and the destination.

Flags: `--tag` and `--sha256` override the pin (the update workflow fetches a
candidate before committing the pin). `--print-sha256` downloads, prints the
hash and exits without extracting (used to compute the pin for a new release).

### Build guard

A hatchling build hook (`hatch_build.py`, registered under
`[tool.hatch.build.hooks.custom]`) runs before every sdist and wheel build. It
fails with a clear message if `src/bats_core/_bats/bin/bats` is missing, or if
the bundled bats version does not match `tool.bats-core.tag`. bats declares
its version as a quoted string in `libexec/bats-core/bats`
(`version() { printf 'Bats %s\n' "1.14.0"; }` in v1.14.0); the hook extracts
it with a regex and compares to the tag without the `v`. This catches "bumped
the pin, forgot to re-run fetch".

The sdist includes `src/bats_core/_bats/`, so installing from sdist never
needs network access.

## Smoke tests

`tests/smoke/` runs against whatever `bats` is on `PATH`. CI installs the
freshly built wheel into a clean venv first, so the tests exercise the
installed artifact, not the source tree. Locally
`uv run --isolated --with dist/*.whl pytest tests/smoke` does the same.

Tests:

- `bats --version` prints `Bats <project.version without fourth component>`.
- `python -m bats_core --version` prints the same.
- A passing `.bats` file exits 0 and emits valid TAP (`1..1`, `ok 1 ...`).
- A failing `.bats` file exits 1 and emits `not ok 1 ...`.
- `--formatter junit` emits `<testsuites`.
- `--jobs 2` on two files passes. This exercises `bats-exec-suite` and the
  semaphore library, proving `lib/` is found.
- `setup_file`/`teardown_file` run, exercising `bats-exec-file`.

CI matrix: `ubuntu-latest` and `macos-latest`, Python `3.9` and `3.x`
(latest). macOS ships bash 3.2, which is bats' floor, so the macOS leg
doubles as the old-bash check.

## Workflows

### `ci.yml` — on push to `main`, on pull requests, and `workflow_call`

1. Checkout, set up `uv` and Python.
2. `uv run pytest tests/unit`.
3. `uv run scripts/fetch_bats.py`.
4. `uv build` (sdist + wheel). Upload `dist/` as an artifact.
5. Matrix job: download `dist/`, create a venv, install the wheel, run
   `pytest tests/smoke`.
6. One job installs from the **sdist** on Linux and runs `bats --version`,
   proving the sdist is self-contained.

### `update.yml` — scheduled daily and `workflow_dispatch`

Inputs for manual dispatch: `tag` (optional, default: latest upstream) and
`rebuild` (boolean: publish a fourth-component rebuild of the current pin).

1. **Detect.** Query `GET /repos/bats-core/bats-core/releases/latest`. This
   endpoint already excludes prereleases and drafts. Compare `tag_name` to
   `tool.bats-core.tag`. If equal, `rebuild` is false, and PyPI already has
   `project.version`, exit 0 with a "nothing to do" notice. If a branch
   `bump/<version>` already exists on the remote, also exit 0: a previous
   attempt is awaiting a human.
2. **Bump.** `scripts/bump.py <tag>` computes the tarball SHA-256 via
   `fetch_bats.py --print-sha256`, rewrites the three pin values in
   `pyproject.toml`, and prints the new package version. For `rebuild` it
   keeps the tag and increments or appends the fourth component. Commit on a
   branch `bump/<version>` and push it.
3. **Build and test.** Call `ci.yml` via `workflow_call` on the bump branch.
4. **On green.** Fast-forward `main` to the bump commit, create tag
   `v<version>`, publish `dist/` to PyPI with `pypa/gh-action-pypi-publish`
   using Trusted Publishing, and create a GitHub release with auto-generated
   notes plus a link to the upstream release. Delete the bump branch.
5. **On red.** Open a PR from `bump/<version>` to `main` titled
   `Bump bats to <tag> (smoke tests failing)` with a link to the failed run in
   the body. The branch stays until a human merges or deletes it, which is
   what the detect step's branch check keys on.

The job that pushes to `main` and tags uses `GITHUB_TOKEN` with
`contents: write`; opening PRs needs `pull-requests: write`. The design
assumes no branch protection on `main`. If protection is added later, the
"on green" step has to merge via PR with auto-merge instead of pushing; the
README records this.

### Publishing

PyPI Trusted Publishing: the `bats-core` project on PyPI is configured with
owner `taminomara`, repository `bats-core`, workflow `update.yml`, environment
`pypi`. The publish job declares `environment: pypi` and
`permissions: id-token: write`. No PyPI API token is stored anywhere.

Before the first release the project owner registers a *pending publisher* on
PyPI by hand. This is a one-time step documented in the README. Then a
`workflow_dispatch` run with no inputs performs the initial publish: detect
sees the pin matches upstream but PyPI has no such version, so it proceeds.

## Error handling summary

| Failure | Behaviour |
|---|---|
| Tarball hash mismatch | fetch exits non-zero, nothing written; CI fails |
| `_bats/` missing at build | hatch hook fails the build with instructions |
| Bundled version ≠ pin | hatch hook fails the build |
| Smoke test red on bump | PR with failing-run link; no publish, no tag |
| Publish fails after tag is pushed | Workflow fails, tag exists without a PyPI release. Re-run `workflow_dispatch`; detect sees PyPI lacks the version and proceeds; publish uses `skip-existing: true` |
| GitHub API error on detect | Job fails; next day retries. Nothing is mutated before detect succeeds |

## Testing the packaging code itself

`tests/unit/` covers `fetch_bats.py` (hash mismatch, path traversal
rejection, selective extraction) and `bump.py` (version derivation,
fourth-component increment, pyproject rewrite) using a locally generated
tarball fixture, with the download function stubbed. No network.

## Decisions

- Hatchling over setuptools: declarative config, small custom-hook API.
- No download inside the build backend: installs from PyPI stay reproducible
  and offline.
- Only `bats` gets an entry point.
- Smoke tests target the installed wheel, not the source tree.
- Auto-publish on green, PR on red (chosen over PR-always and silent-skip).
- Four-component version for rebuilds (chosen over `.postN`).
