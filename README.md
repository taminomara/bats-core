# bats-core

Bash Automated Testing System (bats-core), packaged for pip
## Install

`bats-core` is published to the internal GitLab PyPI registry. In the
consumer project, declare a group-scoped index in `pyproject.toml` (see `mrs`
for a worked example), then `uv add` it:

```toml
[[tool.uv.index]]
name = "server-team"
url = "https://gitlab.corp.cloudlinux.com/api/v4/groups/1645/-/packages/pypi/simple"
explicit = true

[tool.uv.sources]
bats_core = { index = "server-team" }
```

```sh
uv add bats-core
```

Authenticate the index in CI with `UV_INDEX_SERVER_TEAM_USERNAME=gitlab-ci-token`
and `UV_INDEX_SERVER_TEAM_PASSWORD=$CI_JOB_TOKEN` (or `uv auth` locally). The URL
points at group `1645`'s registry (the group that owns the
package) — change it if this package is published elsewhere.

## Development

This repo uses [`uv`](https://docs.astral.sh/uv/) for dependency management,
[`tox`](https://tox.wiki/) (via `tox-uv`) for the test matrix, and
[`prek`](https://github.com/j178/prek) (a pre-commit-compatible runner) for
linting. [`poe`](https://poethepoet.natn.io/) is an optional task wrapper.
Install `uv` first, then:

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


## Release process

No release pipeline is configured (`release_features` is empty). Add `publish-pypi`
or `build-container` via `copier update`, or describe your own release process here.
