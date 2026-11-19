# pytest: Python 3.15 test dependencies on three CI platforms

[pytest](https://github.com/pytest-dev/pytest) is a Python testing framework. This study checks the `uv.lock` at commit [`6665a79fb9a6553ce4e1be5574c21a9e3b769eec`](https://github.com/pytest-dev/pytest/tree/6665a79fb9a6553ce4e1be5574c21a9e3b769eec), using **wheelgap 0.13.0** and package files recorded in the lockfile on **19 November 2026**.

The result concerns **development and test dependencies**, not a missing wheel for pytest itself or a claim that pytest cannot run on Python 3.15.

## Targets and scope

The pinned [test workflow](https://github.com/pytest-dev/pytest/blob/6665a79fb9a6553ce4e1be5574c21a9e3b769eec/.github/workflows/test.yml) includes Python 3.15 on Ubuntu, Windows and macOS. This study checks one representative x86_64 Linux, x64 Windows and ARM64 macOS target, not every runner and Python version from the matrix.

The Linux compatibility assumption is glibc **2.36** and the macOS deployment floor is **15.0**. Those are explicit wheelgap target assumptions, not measurements of the hosted runners. The root [`uv.lock`](https://github.com/pytest-dev/pytest/blob/6665a79fb9a6553ce4e1be5574c21a9e3b769eec/uv.lock) includes development/test dependencies; wheelgap examines the selected locked graph, not a freshly resolved install. The editable pytest package is skipped.

## Reproduce

Download the exact pinned lockfile into an empty directory, then run:

```bash
curl -fL https://raw.githubusercontent.com/pytest-dev/pytest/6665a79fb9a6553ce4e1be5574c21a9e3b769eec/uv.lock -o uv.lock

uvx --from wheelgap==0.13.0 python -m wheelgap uv.lock \
  -p 3.15 \
  -t linux-x86_64,win-amd64,macos-arm64 \
  --glibc 2.36 --macos 15.0 --explain --suggest
```

The scan returned exit code **1**, which is expected when wheelgap finds source-build gaps. Its relevant output was:

```text
wheelgap 0.13.0 · uv.lock · 25 packages · Python 3.15

package              version  linux-x86_64  win-amd64  macos-arm64
numpy (via pytest)   2.4.1    ● source      ● source   ● source
pyyaml (via pytest)  6.0.3    ● source      ● source   ● source

23 packages with wheels for every target hidden (--all to show)

skipped 1 non-index package: pytest (editable)
linux-x86_64  2 from source
win-amd64     2 from source
macos-arm64   2 from source
2 of 25 packages have gaps: 2 will build from source.
```

Here `source` means an sdist exists but no matching prebuilt wheel was found. It does **not** prove the source build will succeed.

## Why these two packages are reported

**NumPy 2.4.1:** Its available binary files for these platforms target earlier CPython versions, such as `cp314-cp314`, which are incompatible with CPython 3.15. The dependency path in `--explain` is `pytest → numpy`. At the time of this check, `--suggest` found **NumPy 2.5.2** with wheels for all three targets. A lockfile update and tests would be needed before adopting that release.

**PyYAML 6.0.3:** The same Python-version mismatch occurs on each selected platform. For example, its `cp314-cp314-win_amd64` wheel is not a CPython 3.15 wheel. The dependency path is `pytest → pyyaml`. `--suggest` found **no newer release** supplying wheels for all three selected targets at scan time. A source build remains an option, subject to validating its build dependencies and compatibility.

## What this check does and does not establish

The check inspects pinned package artefacts, not actual execution of pytest, installation of its full development environment or source compilation. The result does not imply a runtime dependency problem for users installing pytest. Other Python versions, optional groups, operating-system revisions and alternative index settings require their own checks.

For any dependency update, regenerate the project's lockfile and run its normal CI. For packages that remain source-only on Python 3.15, verify the build on each supported platform rather than assuming an sdist is usable.
