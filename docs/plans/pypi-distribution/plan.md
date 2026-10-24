# bats-core PyPI Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish bats-core to PyPI as `bats-core`, bundling a pinned upstream release fetched at build time, with a scheduled GitHub workflow that bumps, tests and publishes new upstream releases automatically.

**Architecture:** A pure-Python wheel built by hatchling contains an unmodified bats runtime tree under `src/bats_core/_bats/`, populated by `scripts/fetch_bats.py` from the GitHub tag tarball and guarded by a build hook. A single `bats` console script execs the bundled `bin/bats`. tox installs the externally built wheel into every Python env so smoke tests run against the artifact that gets published. `update.yml` detects new upstream releases, bumps the pin on a branch, reuses `ci.yml`, and publishes on green or opens a PR on red.

**Tech Stack:** Python 3.10–3.14, uv, hatchling, tox + tox-uv, pytest, ruff, ty, prek, poethepoet, GitHub Actions, PyPI Trusted Publishing.

**Spec:** `docs/plans/pypi-distribution/spec.md`

## Global Constraints

- Package name `bats-core`, import name `bats_core`, `requires-python = ">=3.10"`, wheel tag `py3-none-any`, no runtime dependencies.
- `project.version` equals the bats version (`1.14.0`), with an optional fourth component for packaging rebuilds (`1.14.0.1`). `tool.bats-core.tag` is `v` + the first three components. Initial pin: tag `v1.14.0`, sha256 `bb537b70b15b732f6d8827dd6578e3d8ce166636ce1f18ea9a074184fcce9177`.
- Only `bats` gets a console script. Nothing from `libexec/` is exposed.
- `src/bats_core/_bats/` is never committed. The repo contains no bats source.
- Tarball URL: `https://github.com/bats-core/bats-core/archive/refs/tags/<tag>.tar.gz`. Only `bin/`, `libexec/bats-core/`, `lib/bats-core/` and `LICENSE.md` are extracted.
- POSIX only. No pre-release tags. No `--jobs` in tests.
- Template conventions stay: `uv run --active --no-sync` inside tox commands, `from __future__ import annotations` in every module, ruff rule set from the template, `pytest.toml` as the pytest config, dev deps pinned exactly in `[dependency-groups].dev`.
- Commit messages: conventional prefix (`feat:`, `test:`, `ci:`, `docs:`, `chore:`), no Jira key, each ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Scripts print with `print()`; `T20` is ignored for `scripts/**` in ruff config.

## Review Focus

1. **Arguments with spaces or shell metacharacters** passed to `bats` must reach bats unchanged. Test added to Task 6 (`test_args_with_spaces_pass_through`).
2. **A tarball whose top-level directory is not `bats-core-<version>`** must still extract. Test added to Task 3 (fixture uses the top-level name `bats-core-xyz`).
3. **A pre-release tag** such as `v1.15.0-RC1` passed to `bump.py` must be rejected, not turned into a bogus version. Test added to Task 7 (`test_version_from_tag_rejects_prerelease`).
4. **GitHub API failure** (403 rate limit, network error) during detect must fail the job without emitting `proceed=true`. Test added to Task 8 (`test_main_propagates_api_error`).
5. **A lost executable bit** on the installed `bin/bats` must not break `bats`. Test added to Task 2 (`test_main_restores_exec_bit`).

---

### Task 1: Scaffold from the team template and strip CloudLinux specifics

**Files:**
- Create (via copier): `AGENTS.md`, `pyproject.toml`, `tox.toml`, `poe_tasks.toml`, `pytest.toml`, `.pre-commit-config.yaml`, `.coveragerc.toml`, `.python-version`, `README.md`, `src/bats_core/__init__.py`, `tests/conftest.py`, `tests/test_example.py`, `docs/plans/AGENTS.md`, `docs/research/AGENTS.md`
- Delete after copier: `.gitlab-ci.yml`, `renovate.json`, `.copier-answers.yml`, `tests/test_public_exports.py`
- Modify: `.gitignore` (keep the existing one, append `src/bats_core/_bats/`), `pyproject.toml`, `pytest.toml`, `AGENTS.md`, `README.md`

**Interfaces:**
- Produces: a repo where `uv sync`, `uv run tox -e lint,type` and `uv run tox -e 3.14` pass with the template's example test.

- [ ] **Step 1: Run copier non-interactively**

Run from the worktree root:

```bash
uvx copier copy --trust --defaults --overwrite \
  --data project_name=bats-core \
  --data package_import_name=bats_core \
  --data 'project_description=Bash Automated Testing System (bats-core), packaged for pip' \
  --data project_type=library \
  --data python_dev_version=3.14 \
  --data python_min_version=3.10 \
  --data 'release_features=[]' \
  /home/tami/p/cl/python-template .
```

Expected: files listed above appear; `README.md` is overwritten (it is rewritten in Task 11 anyway); the existing `LICENSE` and `.gitignore` survive (`--overwrite` only replaces files the template renders, and the template's `.gitignore` is equivalent to the existing one; either is fine).

- [ ] **Step 2: Delete the CloudLinux-specific files**

Remove `.gitlab-ci.yml`, `renovate.json`, `.copier-answers.yml`, `tests/test_public_exports.py`. Confirm no `Dockerfile*` or `.dockerignore` was rendered.

- [ ] **Step 3: Trim `pyproject.toml` dev dependencies and pytest config**

In `[dependency-groups].dev` remove `pytest-asyncio`. In `pytest.toml` remove `asyncio_mode = "auto"`. Leave the build system as the template rendered it for now; Task 2 replaces it.

- [ ] **Step 4: Append the bundle directory to `.gitignore`**

Add the line `src/bats_core/_bats/` under a `# bats runtime fetched by scripts/fetch_bats.py` comment.

- [ ] **Step 5: Strip `AGENTS.md`**

Delete the "Releases" section, the bullet about `.copier-answers.yml` / `copier update`, and the sentence about `@pytest.mark.asyncio`. Replace the opening placeholder paragraph with two sentences: the package bundles a pinned bats-core release fetched by `scripts/fetch_bats.py`, and `project.version` mirrors the bats version. Leave the rest for Task 11.

- [ ] **Step 6: Lock, sync, and run the baseline**

Run: `uv lock && uv sync && uv run tox -e lint,type,3.14`
Expected: all three envs OK. `lint` may fix trailing whitespace on first run; re-run until clean.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold from python-template, strip GitLab/Renovate/Jira"
```

---

### Task 2: Package skeleton, hatchling build config, and the `bats` entry point

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/bats_core/__init__.py`
- Create: `src/bats_core/__main__.py`
- Create: `tests/test_main.py`
- Delete: `tests/test_example.py`

**Interfaces:**
- Produces: `bats_core.BATS_ROOT: pathlib.Path` (the `_bats` directory), `bats_core.BATS_EXE: pathlib.Path` (`BATS_ROOT / "bin" / "bats"`), `bats_core.__version__: str` (from `importlib.metadata`), `bats_core.__main__.main(argv: list[str] | None = None) -> int`.
- Produces: `pyproject.toml` with `[tool.bats-core] tag`, `sha256`; `[project.scripts] bats = "bats_core.__main__:main"`.

- [ ] **Step 1: Replace the build system and version in `pyproject.toml`**

Set exactly:

```toml
[project]
name = "bats-core"
version = "1.14.0"
description = "Bash Automated Testing System (bats-core), packaged for pip"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
dependencies = []
classifiers = [
    "Environment :: Console",
    "Intended Audience :: Developers",
    "Operating System :: POSIX",
    "Operating System :: MacOS",
    "Programming Language :: Unix Shell",
    "Programming Language :: Python :: 3",
    "Topic :: Software Development :: Testing",
]

[project.urls]
Homepage = "https://github.com/taminomara/bats-core"
Upstream = "https://github.com/bats-core/bats-core"

[project.scripts]
bats = "bats_core.__main__:main"

[tool.bats-core]
tag = "v1.14.0"
sha256 = "bb537b70b15b732f6d8827dd6578e3d8ce166636ce1f18ea9a074184fcce9177"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build]
artifacts = ["src/bats_core/_bats/"]

[tool.hatch.build.targets.wheel]
packages = ["src/bats_core"]

[tool.hatch.build.hooks.custom]
path = "hatch_build.py"
```

Remove `dynamic = ["version"]`, `[tool.setuptools*]` and `[tool.setuptools_scm]`. Add to dev deps: `hatchling` (pinned to the current release) and `tomli==2.2.1; python_version < "3.11"` (adjust pin to current). Add `[tool.ruff.lint.per-file-ignores] "scripts/**" = ["T20"]`. Set `[tool.ty.src] include = ["src", "tests", "scripts", "hatch_build.py"]`. In `.coveragerc.toml` set `source = ["bats_core", "scripts"]`.

`hatch_build.py` does not exist yet; create a placeholder containing only a `BuildHookInterface` subclass with `PLUGIN_NAME = "custom"` and an empty `initialize`. Task 4 fills it in.

- [ ] **Step 2: Write `src/bats_core/__init__.py`**

Module docstring, `from __future__ import annotations`, `BATS_ROOT = Path(__file__).resolve().parent / "_bats"`, `BATS_EXE = BATS_ROOT / "bin" / "bats"`, `__version__ = importlib.metadata.version("bats-core")`, `__all__ = ["BATS_EXE", "BATS_ROOT", "__version__"]`.

- [ ] **Step 3: Write the failing tests in `tests/test_main.py`**

```python
def test_main_execs_bundled_bats(monkeypatch, tmp_path):
    exe = tmp_path / "bin" / "bats"; exe.parent.mkdir(); exe.write_text("#!/bin/sh\n"); exe.chmod(0o755)
    calls = []
    monkeypatch.setattr(bats_core.__main__, "BATS_EXE", exe)
    monkeypatch.setattr(os, "execv", lambda path, argv: calls.append((path, argv)))
    assert bats_core.__main__.main(["--version"]) == 0
    assert calls == [(str(exe), [str(exe), "--version"])]

def test_main_restores_exec_bit(monkeypatch, tmp_path):
    # same setup but exe.chmod(0o644); after main(), (exe.stat().st_mode & 0o111) != 0

def test_main_missing_bundle_exits_127(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(bats_core.__main__, "BATS_EXE", tmp_path / "missing" / "bats")
    assert bats_core.__main__.main([]) == 127
    assert "missing/bats" in capsys.readouterr().err
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: bats_core.__main__`.

- [ ] **Step 5: Implement `main(argv: list[str] | None = None) -> int` in `src/bats_core/__main__.py`**

`argv` defaults to `sys.argv[1:]`. If `BATS_EXE` is not a file: print `bats: bundled executable not found at <path>` to stderr, return 127. If the mode lacks `0o111`, `chmod` it to `mode | 0o755`. Then `os.execv(str(BATS_EXE), [str(BATS_EXE), *argv])` and return 0 (reached only when execv is patched). Guard with `if __name__ == "__main__": sys.exit(main())`. Import `BATS_EXE` from `bats_core` at module level so tests can monkeypatch the `__main__` attribute.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv sync && uv run pytest tests/test_main.py -v`
Expected: 3 passed. (`uv sync` re-installs the project editable under hatchling; the placeholder hook does nothing.)

- [ ] **Step 7: Delete `tests/test_example.py`, run lint and type**

Run: `uv run tox -e lint,type`
Expected: OK.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: hatchling package skeleton with bats entry point"
```

---

### Task 3: `scripts/fetch_bats.py` — download, verify, extract

**Files:**
- Create: `scripts/fetch_bats.py`
- Create: `tests/test_fetch_bats.py`
- Modify: `pytest.toml` (add `pythonpath = ["scripts", "."]`)

**Interfaces:**
- Produces, in `fetch_bats`:
  - `TARBALL_URL = "https://github.com/bats-core/bats-core/archive/refs/tags/{tag}.tar.gz"`
  - `RUNTIME_PATHS = ("bin/", "libexec/bats-core/", "lib/bats-core/", "LICENSE.md")`
  - `@dataclass(frozen=True) class Pin: version: str; tag: str; sha256: str`
  - `class HashMismatch(Exception)` with attributes `expected`, `actual`
  - `class UnsafeMember(Exception)`
  - `read_pin(pyproject: Path) -> Pin`
  - `download(url: str, dest: Path) -> None` — `urllib.request.urlretrieve`-style, follows redirects
  - `sha256_of(path: Path) -> str`
  - `fetch_tarball(tag: str, dest_dir: Path) -> Path` — calls `download(TARBALL_URL.format(tag=tag), dest_dir / f"{tag}.tar.gz")` and returns that path
  - `extract_runtime(tarball: Path, dest: Path) -> None` — clears `dest`, writes only `RUNTIME_PATHS`
  - `main(argv: list[str] | None = None) -> int` — CLI flags `--tag`, `--sha256`, `--print-sha256`, `--dest` (default `src/bats_core/_bats` relative to repo root), `--pyproject` (default repo `pyproject.toml`)
- Repo root is `Path(__file__).resolve().parents[1]`.

- [ ] **Step 1: Add `pythonpath = ["scripts", "."]` to `pytest.toml`**

- [ ] **Step 2: Write the tarball fixture and failing tests in `tests/test_fetch_bats.py`**

Fixture `fake_tarball(tmp_path) -> tuple[Path, str]` builds `bats-core-xyz/` (deliberately not the upstream name) containing `bin/bats` (mode 0o755, content `#!/usr/bin/env bash\n`), `libexec/bats-core/bats` (mode 0o755, content `export BATS_VERSION='1.14.0'\n`), `lib/bats-core/common.bash`, `LICENSE.md`, plus files that must NOT be extracted: `README.md`, `test/foo.bats`, `docs/x.md`, `man/bats.1`; tars it with `tarfile`, returns `(path, sha256)`. Tests:

```python
def test_read_pin(tmp_path):  # writes a minimal pyproject with version/tag/sha256, asserts Pin fields
def test_extract_runtime_keeps_only_runtime_paths(fake_tarball, tmp_path):
    # after extract: bin/bats, libexec/bats-core/bats, lib/bats-core/common.bash, LICENSE.md exist;
    # README.md, test/, docs/, man/ do not; bin/bats mode & 0o111 != 0
def test_extract_runtime_replaces_previous_contents(fake_tarball, tmp_path):
    # pre-create dest/bin/stale; after extract it is gone
@pytest.mark.parametrize("name", ["bats-core-xyz/../evil", "/abs/evil", "bats-core-xyz/bin/../../evil"])
def test_extract_runtime_rejects_traversal(name, tmp_path):  # tarball with that member -> UnsafeMember
def test_extract_runtime_rejects_symlinks(tmp_path):  # member of type SYMTYPE under bin/ -> UnsafeMember
def test_main_hash_mismatch_writes_nothing(fake_tarball, tmp_path, monkeypatch, capsys):
    # monkeypatch fetch_bats.download to copy fixture; pyproject sha256 = "0"*64
    # main([...]) == 1; dest does not exist; stderr contains both hashes
def test_main_happy_path(fake_tarball, tmp_path, monkeypatch, capsys):
    # pyproject sha256 = fixture sha; main([...]) == 0; dest/bin/bats exists; stdout mentions the tag
def test_main_print_sha256(fake_tarball, tmp_path, monkeypatch, capsys):
    # main(["--tag", "v9.9.9", "--print-sha256"]) == 0; stdout.strip() == fixture sha; nothing extracted
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_fetch_bats.py -v`
Expected: FAIL with `ModuleNotFoundError: fetch_bats`.

- [ ] **Step 4: Implement `scripts/fetch_bats.py`**

`tomllib` import: `if sys.version_info >= (3, 11): import tomllib else: import tomli as tomllib`. `extract_runtime`: open with `tarfile.open`, determine the single top-level directory from the first member, iterate members; for each compute the path relative to the top directory; reject if `member.isdev() or member.issym() or member.islnk()`, if `name` is absolute, or if any component is `..` (raise `UnsafeMember(name)`); skip unless the relative path starts with one of `RUNTIME_PATHS`; extract regular files and directories to `dest` preserving mode. Download into a `tempfile.TemporaryDirectory` so a mismatch leaves nothing behind. `main` prints `Fetched bats <tag> into <dest>` on success.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_fetch_bats.py -v`
Expected: all passed.

- [ ] **Step 6: Run the real fetch once**

Run: `uv run scripts/fetch_bats.py && ls src/bats_core/_bats && git status --short`
Expected: `LICENSE.md bin lib libexec`; `git status` does not list `_bats`.

- [ ] **Step 7: Lint, type, commit**

Run: `uv run tox -e lint,type` → OK.

```bash
git add scripts/fetch_bats.py tests/test_fetch_bats.py pytest.toml
git commit -m "feat: fetch_bats.py downloads, verifies and unpacks the pinned release"
```

---

### Task 4: Build guard hook and `scripts/build.py`

**Files:**
- Modify: `hatch_build.py`
- Create: `tests/test_hatch_build.py`
- Create: `scripts/build.py`
- Modify: `poe_tasks.toml` (add `build` task)

**Interfaces:**
- Produces, in `hatch_build`: `class BundleError(Exception)`, `base_version(package_version: str) -> str` (first three dot-separated components), `bundled_version(bats_dir: Path) -> str` (regex `^export BATS_VERSION='([^']+)'` over `bats_dir / "libexec/bats-core/bats"`, `BundleError` if missing), `check_bundle(bats_dir: Path, package_version: str) -> None` (`BundleError` if `bats_dir / "bin/bats"` is missing or versions differ; message tells the reader to run `uv run poe build`).
- Produces: `scripts/build.py` with `main() -> int`; `uv run poe build` leaves exactly one `.whl` and one `.tar.gz` in `dist/`.

- [ ] **Step 1: Write failing tests in `tests/test_hatch_build.py`**

```python
@pytest.mark.parametrize(("v", "base"), [("1.14.0", "1.14.0"), ("1.14.0.1", "1.14.0"), ("1.14.0.12", "1.14.0")])
def test_base_version(v, base)
def test_check_bundle_missing_exe(tmp_path):  # BundleError, message contains "poe build"
def test_check_bundle_version_mismatch(tmp_path):  # bundled '1.13.0', package "1.14.0" -> BundleError naming both
def test_check_bundle_ok(tmp_path):  # bundled '1.14.0', package "1.14.0.1" -> no raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hatch_build.py -v` → FAIL (`ImportError` for the names).

- [ ] **Step 3: Implement `hatch_build.py`**

The hook class: `initialize(self, version, build_data)` returns early when `version == "editable"`, otherwise calls `check_bundle(Path(self.root) / "src" / "bats_core" / "_bats", self.metadata.version)`. Stdlib only besides hatchling.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_hatch_build.py -v` → passed.

- [ ] **Step 5: Implement `scripts/build.py` and the poe task**

`main()`: `shutil.rmtree(ROOT / "dist", ignore_errors=True)`; `fetch_bats.main([])` (import sibling module; return its code if non-zero); locate `uv` with `shutil.which("uv")`, print `uv not found on PATH` and return 2 if absent; `subprocess.run([uv, "build", "--out-dir", str(ROOT / "dist")], cwd=ROOT, check=True)`; return 0. In `poe_tasks.toml` add:

```toml
[tasks.build]
help = "Fetch the pinned bats release and build sdist + wheel into dist/"
cmd = "python scripts/build.py"
```

- [ ] **Step 6: Verify the guard and the build end to end**

Run: `rm -rf src/bats_core/_bats && uv build 2>&1 | tail -3`
Expected: build fails, output contains `poe build`.

Run: `uv run poe build && ls dist && unzip -l dist/*.whl | grep -E '_bats/(bin/bats|LICENSE.md|lib/bats-core/common.bash)'`
Expected: one wheel, one sdist; the three paths are listed.

Run: `tar tzf dist/*.tar.gz | grep -c '_bats/'`
Expected: a number ≥ 20 (the runtime tree is in the sdist).

Run: `python3 -c "import zipfile,glob,stat; z=zipfile.ZipFile(glob.glob('dist/*.whl')[0]); i=z.getinfo([n for n in z.namelist() if n.endswith('_bats/bin/bats')][0]); print(oct(i.external_attr>>16))"`
Expected: a mode with the executable bits (`0o100755`).

- [ ] **Step 7: Lint, type, commit**

```bash
git add hatch_build.py tests/test_hatch_build.py scripts/build.py poe_tasks.toml
git commit -m "feat: build guard hook and scripts/build.py"
```

---

### Task 5: tox installs the externally built wheel

**Files:**
- Modify: `tox.toml`

**Interfaces:**
- Produces: `uv run tox p` builds `dist/` once via `scripts/build.py` and installs the wheel in every Python env.

- [ ] **Step 1: Switch packaging to external**

In `[env_run_base]` replace `package = "uv"` with `package = "external"`. Add:

```toml
[env.".pkg_external"]
description = "Build dist/ from the pinned bats release"
commands = [["python", "{tox_root}/scripts/build.py"]]
package_glob = "{tox_root}/dist/*.whl"
```

(Verified in a probe with tox 4.67 and tox-uv 1.37: the package env runs the command once and all run envs install the matching wheel.)

- [ ] **Step 2: Verify**

Run: `uv run tox p -- -q 2>&1 | tail -15`
Expected: `3.10` through `3.14`, `lint`, `type`, coverage envs all OK; `Fetched bats v1.14.0` appears once in the package env output.

Run: `uv run tox -e 3.10 -- -q -k test_main` → OK (proves `tomli` is present on 3.10 for the scripts imported by tests).

- [ ] **Step 3: Commit**

```bash
git add tox.toml
git commit -m "test: tox installs the externally built wheel"
```

---

### Task 6: Smoke tests against the installed wheel

**Files:**
- Create: `tests/test_smoke.py`
- Create: `tests/data/` with `passing.bats`, `failing.bats`, `with helper.bats`, `helper.bash`, `file_hooks.bats`

**Interfaces:**
- Consumes: `bats` on `PATH` (tox env), `hatch_build.base_version`, `bats_core.__version__`.

- [ ] **Step 1: Write the fixture files**

`passing.bats`: one test `@test "addition" { [ $((1 + 1)) -eq 2 ]; }`. `failing.bats`: one test `@test "fails" { false; }`. `with helper.bats` (space in the name on purpose): `load helper` then `@test "helper" { run say_hi; [ "$status" -eq 0 ]; [ "$output" = "hi" ]; }`. `helper.bash`: `say_hi() { echo hi; }`. `file_hooks.bats`: `setup_file() { echo "setup_file ran" >&3; }`, `teardown_file() { echo "teardown_file ran" >&3; }`, one passing test.

- [ ] **Step 2: Write the tests**

Helper `run_bats(*args) -> subprocess.CompletedProcess` using `shutil.which("bats")` (assert not None), `capture_output=True, text=True`. `DATA = Path(__file__).parent / "data"`. Expected version `f"Bats {base_version(bats_core.__version__)}"`.

```python
def test_version(): assert run_bats("--version").stdout.strip() == EXPECTED_VERSION
def test_python_m_version(): subprocess [sys.executable, "-m", "bats_core", "--version"] -> same
def test_passing_file_tap():
    r = run_bats("--formatter", "tap", DATA / "passing.bats"); r.returncode == 0; lines == ["1..1", "ok 1 addition"]
def test_failing_file_tap():
    r = run_bats("--formatter", "tap", DATA / "failing.bats"); r.returncode == 1; "not ok 1 fails" in r.stdout
def test_junit_formatter(): "<testsuites" in run_bats("--formatter", "junit", DATA / "passing.bats").stdout
def test_args_with_spaces_pass_through():
    r = run_bats("--formatter", "tap", DATA / "with helper.bats"); r.returncode == 0; "ok 1 helper" in r.stdout
def test_file_hooks_run():
    r = run_bats("--formatter", "tap", DATA / "file_hooks.bats"); "setup_file ran" in r.stdout and "teardown_file ran" in r.stdout
```

- [ ] **Step 3: Run inside tox**

Run: `uv run tox -e 3.14 -- -q tests/test_smoke.py` → 7 passed.

Run: `uv run tox p -- -q 2>&1 | tail -12` → all OK.

- [ ] **Step 4: Commit**

```bash
git add tests/test_smoke.py tests/data
git commit -m "test: smoke tests for the installed bats wheel"
```

---

### Task 7: `scripts/bump.py` — rewrite the pin

**Files:**
- Create: `scripts/bump.py`
- Create: `tests/test_bump.py`

**Interfaces:**
- Consumes: `fetch_bats.read_pin`, `fetch_bats.fetch_tarball`, `fetch_bats.sha256_of`, `fetch_bats.Pin`.
- Produces, in `bump`:
  - `TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")`
  - `class InvalidTag(ValueError)`
  - `version_from_tag(tag: str) -> str` — `"v1.14.0" -> "1.14.0"`, `InvalidTag` otherwise
  - `next_rebuild(version: str) -> str` — `"1.14.0" -> "1.14.0.1"`, `"1.14.0.1" -> "1.14.0.2"`
  - `tarball_sha256(tag: str) -> str` — `fetch_tarball` into a temp dir, `sha256_of`
  - `rewrite_pin(text: str, version: str, tag: str, sha256: str) -> str` — replaces exactly the lines `^version = "..."$`, `^tag = "..."$`, `^sha256 = "..."$`; raises `ValueError` if any pattern matches other than exactly once
  - `main(argv: list[str] | None = None) -> int` — usage `bump.py TAG [--rebuild] [--sha256 HEX] [--pyproject PATH]`; prints the new version to stdout; if `GITHUB_OUTPUT` is set appends `version=<v>\n`

- [ ] **Step 1: Write failing tests in `tests/test_bump.py`**

```python
def test_version_from_tag(): version_from_tag("v1.14.0") == "1.14.0"
@pytest.mark.parametrize("tag", ["v1.15.0-RC1", "1.14.0", "v1.14", "v1.14.0.1"])
def test_version_from_tag_rejects_prerelease(tag): pytest.raises(InvalidTag)
@pytest.mark.parametrize(("cur", "nxt"), [("1.14.0", "1.14.0.1"), ("1.14.0.1", "1.14.0.2"), ("1.14.0.9", "1.14.0.10")])
def test_next_rebuild(cur, nxt)
def test_rewrite_pin_touches_only_three_lines():  # realistic pyproject text; diff against original is exactly 3 lines
def test_rewrite_pin_refuses_ambiguous():  # text with two `version = ` lines -> ValueError
def test_main_new_tag(tmp_path, monkeypatch, capsys):
    # monkeypatch bump.tarball_sha256 -> "a"*64; main(["v1.15.0", "--pyproject", p]) == 0
    # read_pin(p) == Pin("1.15.0", "v1.15.0", "a"*64); stdout.strip() == "1.15.0"
def test_main_rebuild_keeps_tag(tmp_path, monkeypatch):
    # pin 1.14.0/v1.14.0; main(["v1.14.0", "--rebuild", "--sha256", "b"*64, ...]); version "1.14.0.1", tag unchanged, sha "b"*64
def test_main_rebuild_requires_current_tag(tmp_path):  # main(["v1.15.0", "--rebuild", ...]) == 2 with message
def test_main_writes_github_output(tmp_path, monkeypatch):  # GITHUB_OUTPUT file gets "version=1.15.0\n"
```

- [ ] **Step 2: Run tests to verify they fail** → `ModuleNotFoundError: bump`.

- [ ] **Step 3: Implement `scripts/bump.py`**

Pure string/regex work; `argparse` for the CLI. `--sha256` skips the download. Rebuild with a tag different from the current pin returns 2 after printing `--rebuild requires the current tag <pin.tag>`.

- [ ] **Step 4: Run tests to verify they pass** → all passed.

- [ ] **Step 5: Lint, type, commit**

```bash
git add scripts/bump.py tests/test_bump.py
git commit -m "feat: bump.py rewrites the bats pin"
```

---

### Task 8: `scripts/check_upstream.py` — the detect step

**Files:**
- Create: `scripts/check_upstream.py`
- Create: `tests/test_check_upstream.py`

**Interfaces:**
- Consumes: `fetch_bats.read_pin`, `bump.version_from_tag`, `bump.next_rebuild`.
- Produces, in `check_upstream`:
  - `LATEST_URL = "https://api.github.com/repos/bats-core/bats-core/releases/latest"`
  - `PYPI_URL = "https://pypi.org/pypi/bats-core/{version}/json"`
  - `@dataclass(frozen=True) class Decision: proceed: bool; tag: str; version: str; reason: str`
  - `latest_tag() -> str` — GET `LATEST_URL` with `Accept: application/vnd.github+json` and `Authorization: Bearer $GH_TOKEN` when set; raises `urllib.error.HTTPError` through
  - `pypi_has(version: str) -> bool` — 200 → True, 404 → False, anything else raises
  - `branch_exists(name: str) -> bool` — `git ls-remote --exit-code --heads origin <name>` return code 0
  - `decide(pin: Pin, latest: str, tag_override: str | None, rebuild: bool, pypi_has: Callable[[str], bool], branch_exists: Callable[[str], bool]) -> Decision`
  - `main(argv: list[str] | None = None) -> int` — flags `--tag`, `--rebuild`, `--pyproject`; prints the decision; writes `proceed=`, `tag=`, `version=`, `reason=` lines to `GITHUB_OUTPUT` when set

`decide` rules, in order: target = `tag_override or latest`. If `rebuild`: target must equal `pin.tag` (else `Decision(False, ..., reason="rebuild requires current tag")`), version = `next_rebuild(pin.version)`. Elif target ≠ `pin.tag`: version = `version_from_tag(target)`. Else: version = `pin.version`; if `pypi_has(version)` → `Decision(False, reason="up to date")`. In every proceeding case, if `branch_exists(f"bump/{version}")` → `Decision(False, reason="bump/<version> exists, awaiting a human")`.

- [ ] **Step 1: Write failing tests in `tests/test_check_upstream.py`**

```python
PIN = Pin("1.14.0", "v1.14.0", "x"*64)
def test_decide_new_release(): decide(PIN, "v1.15.0", None, False, never, never) -> proceed, tag v1.15.0, version 1.15.0
def test_decide_up_to_date(): decide(PIN, "v1.14.0", None, False, always, never) -> not proceed, reason "up to date"
def test_decide_initial_publish(): decide(PIN, "v1.14.0", None, False, never, never) -> proceed, version 1.14.0
def test_decide_rebuild(): decide(PIN, "v1.14.0", None, True, always, never) -> proceed, version 1.14.0.1
def test_decide_rebuild_wrong_tag(): decide(PIN, "v1.15.0", None, True, ...) -> not proceed
def test_decide_tag_override_wins(): decide(PIN, "v1.15.0", "v1.14.1", False, never, never) -> version 1.14.1
def test_decide_branch_exists_blocks(): branch_exists returns True for "bump/1.15.0" -> not proceed, reason mentions the branch
def test_main_writes_github_output(tmp_path, monkeypatch): patch latest_tag/pypi_has/branch_exists; GITHUB_OUTPUT contains proceed=true, tag=v1.15.0, version=1.15.0
def test_main_propagates_api_error(tmp_path, monkeypatch):
    # latest_tag raises HTTPError(403); main() raises (or returns non-zero); GITHUB_OUTPUT has no "proceed=true"
```

- [ ] **Step 2: Run tests to verify they fail** → `ModuleNotFoundError: check_upstream`.

- [ ] **Step 3: Implement `scripts/check_upstream.py`**

`main` must not catch exceptions from `latest_tag`; a traceback failing the job is the desired behaviour. `proceed` is written lowercase `true`/`false`.

- [ ] **Step 4: Run tests to verify they pass** → all passed.

- [ ] **Step 5: Live sanity check**

Run: `uv run scripts/check_upstream.py`
Expected: prints a decision with `tag=v1.14.0` and `proceed=true`, reason about PyPI lacking the version (nothing is published yet). Takes two HTTPS calls and one `git ls-remote`.

- [ ] **Step 6: Lint, type, commit**

```bash
git add scripts/check_upstream.py tests/test_check_upstream.py
git commit -m "feat: check_upstream.py decides whether a bump is due"
```

---

### Task 9: `ci.yml`

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: a workflow usable via `workflow_call` with input `ref` (string, optional); uploads artifact `dist` from the Linux leg.

- [ ] **Step 1: Write the workflow**

```yaml
name: CI
on:
  push: { branches: [main] }
  pull_request:
  workflow_call:
    inputs:
      ref: { type: string, required: false, default: "" }
permissions: { contents: read }
jobs:
  test:
    strategy:
      fail-fast: false
      matrix: { os: [ubuntu-latest, macos-latest] }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
        with: { ref: "${{ inputs.ref || github.ref }}" }
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --frozen
      - run: uv run tox p -- --color=yes
      - uses: actions/upload-artifact@v4
        if: matrix.os == 'ubuntu-latest'
        with: { name: dist, path: dist/, if-no-files-found: error }
  sdist-install:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: astral-sh/setup-uv@v6
      - uses: actions/download-artifact@v4
        with: { name: dist, path: dist }
      - run: |
          uv venv .venv
          uv pip install --python .venv dist/*.tar.gz
          .venv/bin/bats --version
```

Use the current major of each action if newer ones exist; the shapes above are stable across majors.

- [ ] **Step 2: Lint the workflow**

Run: `uvx --from actionlint-py actionlint .github/workflows/ci.yml` (fallback if that package is unavailable: `uvx yamllint -d relaxed .github/workflows/ci.yml`).
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: test matrix on Linux and macOS, sdist install check"
```

---

### Task 10: `update.yml`

**Files:**
- Create: `.github/workflows/update.yml`

**Interfaces:**
- Consumes: `scripts/check_upstream.py` outputs `proceed`, `tag`, `version`; `scripts/bump.py` output `version`; `ci.yml` `workflow_call` with `ref`; artifact `dist`.

- [ ] **Step 1: Write the workflow**

Triggers: `schedule: - cron: "17 6 * * *"` and `workflow_dispatch` with inputs `tag` (string, default `""`) and `rebuild` (boolean, default `false`). Top-level `permissions: { contents: write, pull-requests: write }`. Bot identity for commits: `github-actions[bot]` / `41898282+github-actions[bot]@users.noreply.github.com`. `GH_TOKEN: ${{ github.token }}` on every step that calls `gh` or `check_upstream.py`.

Jobs:

1. `detect` (ubuntu): checkout, setup-uv, `uv sync --frozen`, step id `check` running `uv run scripts/check_upstream.py ${{ inputs.tag && format('--tag {0}', inputs.tag) || '' }} ${{ inputs.rebuild && '--rebuild' || '' }}`. Job outputs `proceed`, `tag`, `version` from `steps.check.outputs`.
2. `bump` (needs detect, `if: needs.detect.outputs.proceed == 'true'`): checkout with `fetch-depth: 0`, setup-uv, `uv sync --frozen`, `uv run scripts/bump.py "$TAG" $REBUILD_FLAG`, configure bot identity, `git switch -c "bump/$VERSION"`, `git add pyproject.toml`, `git diff --cached --quiet || git commit -m "Bump bats to $TAG"`, `git push -u origin "bump/$VERSION"`. Outputs `version`, `branch`.
3. `test` (needs `[detect, bump]`): `uses: ./.github/workflows/ci.yml` with `ref: ${{ needs.bump.outputs.branch }}`.
4. `publish` (needs `[detect, bump, test]`, `environment: pypi`, `permissions: { id-token: write, contents: write }`): checkout `main` with `fetch-depth: 0`; `git fetch origin "$BRANCH"`; `git merge --ff-only "origin/$BRANCH"`; `git push origin main`; `git tag "v$VERSION"`; `git push origin "v$VERSION"`; download artifact `dist` to `dist/`; `pypa/gh-action-pypi-publish@release/v1` with `skip-existing: true`; `gh release create "v$VERSION" --generate-notes --notes "Bundles upstream https://github.com/bats-core/bats-core/releases/tag/$TAG"`; `git push origin --delete "$BRANCH"`.
5. `report-failure` (needs `[detect, bump, test]`, `if: failure() && needs.bump.result == 'success'`): checkout; `gh pr create --base main --head "$BRANCH" --title "Bump bats to $TAG (smoke tests failing)" --body "Automated bump failed CI: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"`.

Pass `TAG`, `VERSION`, `BRANCH` into steps through `env:` from the job outputs rather than inlining expressions into shell.

- [ ] **Step 2: Lint the workflow**

Run: `uvx --from actionlint-py actionlint .github/workflows/update.yml` (or the yamllint fallback).
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update.yml
git commit -m "ci: scheduled upstream tracking with auto-publish and failure PRs"
```

---

### Task 11: README, AGENTS.md, final review

**Files:**
- Modify: `README.md`, `AGENTS.md`

- [ ] **Step 1: Rewrite `README.md`**

Sections, in order: title and one-paragraph description (what it is, upstream link, POSIX only, bash ≥ 3.2); **Install** (`pip install bats-core`, `uv tool install bats-core`, `uvx --from bats-core bats`); **Versioning** (mirrors bats, fourth component for rebuilds, `==1.14.0.*` tip); **Development** (keep the template's uv/tox/poe block, add `uv run poe build`, mention that `_bats/` is fetched, not committed); **Release process** (daily `update.yml`, auto-publish on green, PR on red, manual `workflow_dispatch` with `tag`/`rebuild`); **One-time setup** (register a pending Trusted Publisher on PyPI for `taminomara/bats-core`, workflow `update.yml`, environment `pypi`; create the `pypi` environment in repo settings; if branch protection is ever enabled on `main`, the publish job must switch to merging via PR); **License** (packaging code MIT, bats-core MIT with its `LICENSE.md` shipped in the wheel). Remove the GitLab registry text and the "No release pipeline is configured" line.

- [ ] **Step 2: Finish `AGENTS.md`**

Add a "Layout" section naming `scripts/fetch_bats.py`, `scripts/bump.py`, `scripts/check_upstream.py`, `scripts/build.py`, `hatch_build.py` with one line each, and a "Releases" section pointing at the README's release process. Confirm no remaining mention of GitLab, Jira, Renovate, copier, or setuptools_scm: `grep -n -i -E 'gitlab|jira|renovate|copier|setuptools' AGENTS.md README.md pyproject.toml` returns nothing.

- [ ] **Step 3: Full run**

Run: `uv run tox p -- -q 2>&1 | tail -12` → all OK.

- [ ] **Step 4: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: README and agent notes for the PyPI distribution"
```

---

## Out of band for the human

- `gh` is not authenticated in this session (token invalid), so nothing here pushes to GitHub. After the branch is merged: push `main`, register the PyPI pending publisher, create the `pypi` environment, and run `update.yml` once via `workflow_dispatch` for the initial `1.14.0` release.
- PRs opened by `GITHUB_TOKEN` do not trigger `ci.yml`; re-run manually on a failure PR after fixing.
