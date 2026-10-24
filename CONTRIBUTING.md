# Contributing

This repository packages upstream bats-core for PyPI. It contains no bats
source: `scripts/fetch_bats.py` downloads the source archive of the commit
pinned in `pyproject.toml` under `[tool.bats-core]` (`tag`, `commit`,
`sha256`), verifies its SHA-256, and unpacks `bin/`, `libexec/`, `lib/` and
`LICENSE.md` into `src/bats_core/_bats/` (gitignored). A hatchling build hook
(`hatch_build.py`) refuses to build a wheel or sdist when that directory is
missing or its version does not match `project.version`.

The archive is fetched by commit rather than by tag because a commit is
immutable and a tag is not. The SHA-256 is recorded when the pin is bumped,
so it guarantees that every build and rebuild of a version uses identical
upstream bytes; it does not authenticate the release. The checks that do
stand between upstream and PyPI are below under "What gates a release".

## Development

The repo uses [`uv`](https://docs.astral.sh/uv/) for dependency management,
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
gets published. In CI a dedicated `build` job produces `dist/` with no
project environment installed, and the test jobs download it and run with
`BATS_CORE_PREBUILT=1`, which makes `scripts/build.py` reuse the wheel
instead of rebuilding. Every platform tests, and the release publishes, the
same file.

### Layout

- `src/bats_core/__main__.py` — the `bats` console script; execs the bundled
  `_bats/bin/bats`.
- `scripts/fetch_bats.py` — downloads the pinned tarball, verifies SHA-256,
  unpacks the runtime tree into `src/bats_core/_bats/`.
- `scripts/build.py` — cleans `dist/`, fetches, runs `uv build`. The only way
  `dist/` is produced (poe `build`, the tox package env, CI). With
  `BATS_CORE_PREBUILT` set it reuses the single wheel already in `dist/`.
- `scripts/bump.py` — resolves a tag to its commit via the GitHub API,
  checks the tag signature, and rewrites `version`, `tag`, `commit` and
  `sha256` in `pyproject.toml` for a new upstream tag or a packaging rebuild.
- `scripts/check_upstream.py` — the update workflow's detect step; decides
  whether a bump is due and writes the decision to `$GITHUB_OUTPUT`.
- `hatch_build.py` — hatchling hook that refuses to build without a bundle
  matching `project.version`.
- `tests/test_smoke.py` runs against the installed wheel; the other tests are
  offline and import the scripts directly (`pytest.toml` adds `scripts/` to
  `pythonpath`).

## Release process

Releases are automatic. `.github/workflows/update.yml` runs daily:

1. `scripts/check_upstream.py` compares the latest upstream release with the
   pin and checks whether PyPI already has the matching version.
2. If a bump is due, `scripts/bump.py` resolves the tag to its commit,
   rewrites the pin on a branch `bump/<version>`, and `ci.yml` runs the full
   matrix against it.
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

The workflow operates on the branch it was dispatched from: it bumps on a
branch cut from it, fast-forwards it, and opens failure PRs against it. The
schedule only ever runs on `main`.

### What gates a release

Anyone who can publish a release in `bats-core/bats-core` can, in
principle, get code onto PyPI under this name. Three checks limit that:

- **Cooldown.** The schedule ignores upstream releases younger than
  `COOLDOWN_DAYS` (3, set in `update.yml`). A release that upstream pulls
  within that window is never published here. A manual dispatch that names
  a `tag` bypasses the cooldown; one without a tag does not.
- **Tag signature.** When the upstream tag is annotated and signed,
  `bump.py` requires GitHub to report the signature as verified and refuses
  otherwise. Upstream has also released from unsigned lightweight tags, so an
  unsigned tag is accepted with a workflow warning rather than refused.
- **Smoke tests on both platforms**, as described above.

On our side, Trusted Publishing attaches PEP 740 attestations to every file
uploaded to PyPI, naming this repository, workflow and commit.

### Backporting a packaging fix to an older bats

`1.13.0.1` sorts below `1.14.0`, so a backport never changes what a plain
`pip install bats-core` resolves to; users pinned to `bats-core==1.13.0.*`
pick it up.

1. Cut a release branch from `main`, pin it to the old bats, and cherry-pick
   the fix:

   ```sh
   git switch -c release/1.13 main
   uv run scripts/bump.py v1.13.0
   git commit -am "Pin bats 1.13.0"
   git cherry-pick <fix>
   git push -u origin release/1.13
   ```

2. Dispatch `update.yml` on `release/1.13` with `tag: v1.13.0` and `rebuild`
   checked. That publishes `1.13.0.1`. If `1.13.0` itself was never
   published from this repo, dispatch once without `rebuild` first.

3. Keep the release branch; the `v1.13.0.*` tags point into it.

Always pass `tag` when dispatching on a release branch. Without it, detect
compares the pin against the latest upstream release and would try to move
the branch to the newest bats.

### Dependency updates

Dependabot (`.github/dependabot.yml`) opens one grouped PR per ecosystem
every week: Python dev dependencies and `uv.lock` (`uv`), GitHub Actions,
and pre-commit hook revisions. `.github/workflows/automerge.yml` watches CI
and, when a Dependabot PR's run is green, fast-forwards `main` to it over
the deploy key and deletes the branch. GitHub marks the PR merged. If `main`
moved in the meantime the job skips; Dependabot rebases, CI re-runs, and the
job gets another chance.

### Publishing target

`PYPI_HOST` at the top of `update.yml` selects the index, for both the
upload and the "does this version already exist" check. It is `pypi.org`.
To rehearse the pipeline, set it to `test.pypi.org`; TestPyPI needs its own
pending publisher registration. Tags and GitHub releases created during a
TestPyPI phase stay valid: every publish step is idempotent, so the first
live run uploads the existing version to PyPI and skips the rest.

### One-time setup

- Register a pending publisher for the `bats-core` project with owner
  `taminomara`, repository `bats-core`, workflow `update.yml`, environment
  `pypi`. Do this on the index `PYPI_HOST` points at; TestPyPI and PyPI
  each need their own.
- Create the `pypi` environment. Limit its deployment branches to `main` and
  `release/*`. Do not add required reviewers unless every release should
  wait for a manual approval.
- Generate an SSH key pair. Add the public key under Settings → Deploy keys
  with write access, and the private key as the environment secret
  `DEPLOY_KEY` on `pypi`. The publish job pushes the base branch and the
  `v*` tag with this key; everything else uses `GITHUB_TOKEN`.
- Create the `automerge` environment with deployment branch `main` and the
  same private key as its `DEPLOY_KEY` secret. The automerge job runs there
  so it never holds PyPI publishing rights.
- Rulesets (Settings → Rules). Bypass list for both: the deploy key and the
  Maintain and Repository admin roles, bypass mode "Always".
  - Branches `main` and `release/*`: restrict creations, restrict updates,
    restrict deletions, block force pushes, require linear history.
  - Tags `v*`: restrict creations, restrict updates, restrict deletions.
  Do not require pull requests or signed commits; the bot fast-forwards
  unsigned bump commits directly.
- Leave the default workflow token permissions at read-only; both workflows
  declare what they need.
- Enable "Allow GitHub Actions to create and approve pull requests" under
  Settings → Actions → General. Without it the on-red path cannot open its
  pull request.
- Dispatch `update.yml` once with no inputs to publish the current pin.

Anyone with write access can dispatch `update.yml`, and on `main` that does
no more than the nightly run. A `rebuild` or `tag` dispatch is the one
action a non-maintainer could take; keep write access to maintainers if that
matters.
