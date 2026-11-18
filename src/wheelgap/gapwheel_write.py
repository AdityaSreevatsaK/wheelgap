"""Explicit, reversible writes of a gap-wheel index to a plain pip requirements file.

Only called when wheelgap has independently verified an exact published wheel
for a requested target. Never touches uv.lock, pyproject.toml, global pip
configuration, Dockerfiles, or implicit directory/package inputs.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path

from .gapwheels import INDEX

MAX_REQUIREMENTS_BYTES = 2_000_000
_INDEX = f"--extra-index-url {INDEX}"
_OPTIONS = re.compile(r"^\s*(?:-r\b|--requirement\b|-c\b|--constraint\b|--index-url\b|-i\b|"
                      r"--extra-index-url\b|--no-index\b|--find-links\b|-f\b|--require-hashes\b|"
                      r"--no-binary\b|--only-binary\b)", re.IGNORECASE)


class UnsafeRequirements(ValueError):
    """File cannot be modified without guessing how pip will interpret it."""


def _check_file(path: Path) -> os.stat_result:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise UnsafeRequirements("refusing to modify requirements through a symbolic link")
    try:
        info = path.stat()
    except OSError as exc:
        raise UnsafeRequirements(f"cannot stat requirements file: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise UnsafeRequirements("requirements input is not a regular file")
    if info.st_size > MAX_REQUIREMENTS_BYTES:
        raise UnsafeRequirements("requirements file exceeds the 2 MB write limit")
    return info


def apply_requirements_index(path: Path) -> bool:
    """Prepend the extra index, saving <requirements>.wheelgap.bak first.

    Returns True if written, False if the exact index line already exists.
    Raises UnsafeRequirements for ambiguity without changing the file.
    """
    info = _check_file(path)
    try:
        original = path.read_bytes()
    except OSError as exc:
        raise UnsafeRequirements(f"cannot read requirements file: {exc}") from exc
    if len(original) > MAX_REQUIREMENTS_BYTES:
        raise UnsafeRequirements("requirements file exceeds the 2 MB write limit")
    if b"\x00" in original:
        raise UnsafeRequirements("requirements file contains NUL bytes")
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    try:
        text = original[len(bom):].decode("utf-8")
    except UnicodeError as exc:
        raise UnsafeRequirements("requirements file is not UTF-8") from exc
    if "\r" in text.replace("\r\n", ""):
        raise UnsafeRequirements("requirements file contains unsupported line endings")
    lines = text.splitlines()
    existing_index = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == _INDEX:
            existing_index += 1
            continue
        # Hash-pinned installs need the new wheel's hash; alternative indexes and
        # nested includes can change dependency resolution in ways we cannot prove.
        if ("--hash" in stripped or "\\" in stripped or stripped.startswith("-")
                or "://" in stripped or stripped.startswith(("git+", "hg+", "svn+"))
                or " @ " in stripped):
            raise UnsafeRequirements(
                "requirements contain hashes, URLs, nested files or pip options; print the snippet and edit manually"
            )
    if existing_index > 1:
        raise UnsafeRequirements("requirements contain duplicate gap-wheel index directives")
    if existing_index == 1:
        return False
    backup = path.with_name(path.name + ".wheelgap.bak")
    if backup.exists() or backup.is_symlink():
        raise UnsafeRequirements(f"backup already exists: {backup}; not overwriting it")
    newline = "\r\n" if "\r\n" in text else "\n"
    modified = bom + (_INDEX + newline).encode("utf-8") + original[len(bom):]
    if len(modified) > MAX_REQUIREMENTS_BYTES:
        raise UnsafeRequirements("modified requirements would exceed the 2 MB limit")
    # Recheck the original immediately before writing; concurrent changes are not
    # silently overwritten. In-place edits by another process after this check must
    # still be coordinated externally, as on most local editors.
    if _check_file(path) != info or path.read_bytes() != original:
        raise UnsafeRequirements("requirements changed while preparing the update")
    backup_fd: int | None = None
    temporary: Path | None = None
    try:
        backup_fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(backup_fd, "wb") as stream:
            backup_fd = None
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(backup, stat.S_IMODE(info.st_mode))
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.wheelgap-", dir=path.parent)
        temporary = Path(tmp_name)
        with os.fdopen(tmp_fd, "wb") as stream:
            stream.write(modified)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(info.st_mode))
        if _check_file(path) != info or path.read_bytes() != original:
            raise UnsafeRequirements("requirements changed during the update; backup kept, original untouched")
        os.replace(temporary, path)
        return True
    except OSError as exc:
        raise UnsafeRequirements(f"could not safely write requirements: {exc}") from exc
    finally:
        if backup_fd is not None:
            os.close(backup_fd)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
