# bats-core

This package installs the `bats` command from
[Bats](https://github.com/bats-core/bats-core), the Bash Automated Testing
System, packaged for pip. It runs the upstream release unchanged. It works on
Linux and macOS and needs bash 3.2 or newer.

## Install

```sh
pip install bats-core
```

Or as a standalone tool:

```sh
uv tool install bats-core
uvx --from bats-core bats --version
```

## Write and run a test

Write a test file:

```bash
# test/addition.bats
@test "addition works" {
  result="$((2 + 2))"
  [ "$result" -eq 4 ]
}
```

Run it:

```sh
bats test/
```

Everything about writing and running tests is in the
[upstream documentation](https://bats-core.readthedocs.io/). Companion
libraries such as `bats-support` and `bats-assert` are not bundled.

## Version numbers and pinning

The package version is the bats version: `bats-core==1.14.0` installs
bats 1.14.0. When only the packaging changes, a fourth component is added,
such as `1.14.0.1`. To follow one bats release including packaging fixes,
pin `bats-core==1.14.0.*`.

New upstream releases are published here automatically with a 3 days cooldown.

## License

The packaging code is MIT licensed, see `LICENSE`. Bats is MIT licensed by
its authors; its license ships inside the package as
`bats_core/_bats/LICENSE.md`.

For development, release and maintenance notes see
[CONTRIBUTING.md](https://github.com/taminomara/bats-core/blob/main/CONTRIBUTING.md).
