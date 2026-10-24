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

The version is static, not derived from git tags. The bot writes the version,
builds and tests, and only then tags; a tag-derived version would be
`1.14.0.devN` at build time.

## Scaffold: the team Python template, stripped

The repository is generated with `uvx copier copy ~/p/cl/python-template .`
and these answers: `project_name=bats-core`, `package_import_name=bats_core`,
`project_type=library` (it is the only type with a multi-version tox matrix
and a configurable floor), `python_dev_version=3.14`,
`python_min_version=3.10`, `release_features=[]`.

**Kept from the template**: `uv` with `uv.lock`, `[dependency-groups].dev`,
`tox.toml` with `tox-uv`, `poe_tasks.toml`, `pytest.toml`,
`.pre-commit-config.yaml` with `prek` and `ruff`, `ty` config,
`.python-version`, the `[tool.ruff]` rule set, `AGENTS.md`, `docs/plans/` and
`docs/research/` with their `AGENTS.md`, `src/` layout, `tests/conftest.py`.

**Removed**: `.gitlab-ci.yml`, `renovate.json` (extends a CloudLinux-internal
preset), `.copier-answers.yml` (the template is internal and we diverge from it
on purpose; `copier update` is not expected to work), `test_public_exports.py`
(the package has no Python API), the GitLab registry install section of the
README, the "Releases" and template-update paragraphs of `AGENTS.md`, every
Jira and GitLab mention.

**Replaced**: build backend `setuptools` + `setuptools_scm` → `hatchling` with
a static version and a custom build hook (see Build guard). `project.scripts`
gets the `bats` entry point.

## Package layout

```
pyproject.toml
README.md
LICENSE                       # this repo's MIT license (packaging code)
AGENTS.md
hatch_build.py                # build guard
tox.toml
poe_tasks.toml
pytest.toml
.pre-commit-config.yaml
.python-version
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
scripts/check_upstream.py     # the update workflow's detect step
scripts/build.py              # clean dist/, fetch, `uv build`
tests/
  conftest.py
  test_main.py                # entry point error path and chmod
  test_fetch_bats.py          # offline tests for the fetch script
  test_bump.py                # offline tests for the bump script
  test_check_upstream.py      # offline tests for the detect logic
  test_hatch_build.py         # offline tests for the build guard
  test_smoke.py               # against the installed wheel
docs/plans/pypi-distribution/ # this spec and its plan
.github/workflows/
  ci.yml
  update.yml
```

The wheel is `py3-none-any`, `requires-python >= 3.10`. No runtime
dependencies. `tomli` is a dev dependency with marker `python_version < "3.11"`
for the scripts.

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
   `tomllib`; `tomli` on 3.10).
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
the bundled bats version does not match the first three components of
`project.version`. bats declares its version on one line of
`libexec/bats-core/bats` (`export BATS_VERSION='1.14.0'`); the hook extracts
it with a regex. This catches "bumped the pin, forgot to re-run fetch". The
hook compares against `project.version` rather than `tool.bats-core.tag` so
it needs no TOML parser in the build environment; the two agree by the
versioning invariant above.

The hook skips editable builds, so `uv sync` on a fresh clone works before
the first fetch.

`src/bats_core/_bats/` is gitignored, and hatchling excludes VCS-ignored files
by default, so it is listed under `[tool.hatch.build].artifacts` to force it
into both the wheel and the sdist. Installing from sdist never needs network
access.

### `scripts/build.py`

Deletes `dist/`, runs the fetch, runs `uv build`. It is the single way to
produce `dist/`, used by the `build` poe task, by the tox package env, and by
CI. Deleting `dist/` first matters because tox locates the wheel by glob and
requires exactly one match.

## Testing

### tox matrix

`tox.toml` comes from the template: `env_list = ["3.14", "3.13", "3.12",
"3.11", "3.10", "type", "lint", "coverage-clean", "coverage-combine"]`,
`tox-uv` as the backend, `uv run --active --no-sync pytest tests --cov` as the
command. `tox-uv` downloads missing interpreters through `uv`, so `tox p`
works on a machine with only one Python installed.

One deliberate change from the template: `package = "external"` instead of
`package = "uv"`. The template installs the project into each env from the
working tree; here every env must install the **built wheel**, because the
smoke tests exist to prove the artifact we publish works. The package env is:

```toml
[env_run_base]
package = "external"

[env.".pkg_external"]
commands = [["uv", "run", "--active", "--no-sync", "python", "scripts/build.py"]]
package_glob = "{tox_root}/dist/*.whl"
```

tox runs `scripts/build.py` once, then installs the one wheel it finds in
`dist/` into every Python env. The same `dist/` is what CI uploads and the
update workflow publishes, so the tested bytes are the published bytes.

If `package = "external"` turns out not to cooperate with `tox-uv`, the
fallback is `package = "wheel"`: tox builds the wheel through hatchling, the
build guard still runs, and CI builds `dist/` separately with `scripts/build.py`
for upload. The plan has a task to verify which one works.

### Tests

All tests live in `tests/` and run in every Python env.

`test_fetch_bats.py`, `test_bump.py`, `test_check_upstream.py`,
`test_hatch_build.py` and `test_main.py` are offline: a fixture generates a
tarball shaped like the upstream one, the download function is monkeypatched
to return it, and network and git lookups are passed in as callables. They
cover hash mismatch, path traversal and symlink rejection, selective
extraction, version derivation from a tag, fourth-component increment, the
`pyproject.toml` rewrite leaving everything else untouched, every branch of
the detect decision, the build guard, and the entry point's missing-file and
lost-exec-bit paths. `pytest.toml` sets `pythonpath = ["scripts", "."]` so
tests import the scripts and `hatch_build.py` directly.

`test_smoke.py` locates `bats` with `shutil.which` (the tox env's `bin/` is on
`PATH`) and `python -m bats_core` via `sys.executable`, then:

- `bats --version` prints `Bats <project.version without fourth component>`.
- `python -m bats_core --version` prints the same.
- A passing `.bats` file exits 0 and emits valid TAP (`1..1`, `ok 1 ...`).
- A failing `.bats` file exits 1 and emits `not ok 1 ...`.
- `--formatter junit` emits `<testsuites`.
- A test file that `load`s a helper `.bash` file and uses `run` plus `$status`
  passes, exercising `lib/bats-core/test_functions.bash`.
- `setup_file`/`teardown_file` run, exercising `bats-exec-file`.

`--jobs` is not exercised: bats implements it with GNU parallel, which the
runners do not guarantee.

Coverage is collected as in the template. It is meaningful for the scripts and
near-zero for `__main__.py`, which execs away; that is accepted.

### `lint` and `type` envs

Unchanged from the template: `prek run --all-files` (ruff check, ruff format,
hygiene hooks) and `ty check`. `scripts/` and `hatch_build.py` are included in
`[tool.ty.src].include`.

### Local commands

```sh
uv sync
uv run poe build       # dist/ from the pinned bats
uv run poe test        # 3.14 only
uv run poe test-all    # tox p: full matrix + lint + type
```

## Workflows

### `ci.yml` — on push to `main`, on pull requests, and `workflow_call`

Matrix over `ubuntu-latest` and `macos-latest`:

1. Checkout, `astral-sh/setup-uv`, `uv sync --frozen`.
2. `uv run tox p -- --color=yes`. The package env runs `scripts/build.py`,
   which performs the GitHub download.
3. Upload `dist/` from the Linux leg as an artifact named `dist`.
4. A final Linux job downloads `dist`, installs the **sdist** into a fresh
   venv and runs `bats --version`, proving the sdist is self-contained.

macOS ships bash 3.2, which is bats' floor, so the macOS leg doubles as the
old-bash check.

### `update.yml` — scheduled daily and `workflow_dispatch`

Inputs for manual dispatch: `tag` (optional, default: latest upstream) and
`rebuild` (boolean: publish a fourth-component rebuild of the current pin).

1. **Detect** (`scripts/check_upstream.py`, so the logic is unit-tested
   offline). Query `GET /repos/bats-core/bats-core/releases/latest`. This
   endpoint already excludes prereleases and drafts. Compare `tag_name` to
   `tool.bats-core.tag`. If equal, `rebuild` is false, and PyPI already has
   `project.version` (`GET https://pypi.org/pypi/bats-core/<version>/json`
   returns 200), exit 0 with a "nothing to do" notice. If a branch
   `bump/<version>` already exists on the remote, also exit 0: a previous
   attempt is awaiting a human.
2. **Bump.** `scripts/bump.py <tag>` computes the tarball SHA-256 via
   `fetch_bats.py --print-sha256`, rewrites the three pin values in
   `pyproject.toml`, and prints the new package version. For `rebuild` it
   keeps the tag and increments or appends the fourth component. Commit on a
   branch `bump/<version>` and push it.
3. **Build and test.** Call `ci.yml` via `workflow_call` on the bump branch.
4. **On green.** Fast-forward `main` to the bump commit, create tag
   `v<version>`, download the `dist` artifact and publish it to PyPI with
   `pypa/gh-action-pypi-publish` using Trusted Publishing, create a GitHub
   release with auto-generated notes plus a link to the upstream release.
   Delete the bump branch.
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
| Publish fails after `main` is updated | The bump branch is already deleted, an issue is opened, and the next scheduled run (or a manual dispatch) retries: detect sees PyPI lacks the version and proceeds; tagging, the PyPI upload (`skip-existing: true`) and the GitHub release are all idempotent |
| GitHub API error on detect | Job fails; next day retries. Nothing is mutated before detect succeeds |

## Decisions

- Scaffold from the team template, strip GitLab, Jira, Renovate and the
  internal-registry docs.
- Hatchling with a static version over setuptools_scm: the version comes from
  upstream, not from our tags.
- No download inside the build backend: installs from PyPI stay reproducible
  and offline.
- tox installs the externally built wheel so tests and publish share one
  artifact.
- Only `bats` gets an entry point.
- Auto-publish on green, PR on red (chosen over PR-always and silent-skip).
- Four-component version for rebuilds (chosen over `.postN`).
- Python 3.10–3.14 matrix, matching the template's supported range.
