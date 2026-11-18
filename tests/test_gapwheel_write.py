"""Explicitly writing a gap-wheel index is opt-in and must be safe to reverse."""

import pytest
from test_cli import run

from wheelgap import cli, gapwheel_write

INDEX = "https://wheelgap.github.io/wheels/simple/"
OPTIONS = ["-p", "3.14t", "-t", "win-arm64", "--fix", "--write-gap-wheel-config"]
WHEEL = "nowheels-0.9-cp314-cp314t-win_arm64.whl"


def test_write_requirements_creates_backup_and_is_idempotent(capsys, fake_pypi, gap_wheels, tmp_path):
    file = tmp_path / "requirements.txt"
    original = b"# app dependencies\r\nnowheels==0.9\r\n"
    file.write_bytes(original)
    gap_wheels.add("nowheels", "0.9", WHEEL)
    code, output, err = run(capsys, str(file), *OPTIONS)
    assert code == 1 and output == ""
    assert "updated" in err
    assert file.read_bytes() == f"--extra-index-url {INDEX}\r\n".encode() + original
    backup = tmp_path / "requirements.txt.wheelgap.bak"
    assert backup.read_bytes() == original
    second = run(capsys, str(file), *OPTIONS)
    assert second[0] == 1
    assert "already configured" in second[2]
    assert backup.read_bytes() == original


def test_no_fill_makes_no_file_changes(capsys, fake_pypi, gap_wheels, tmp_path):
    file = tmp_path / "requirements.txt"
    file.write_text("nowheels==0.9\n", encoding="utf-8")
    gap_wheels.add("nowheels", "0.8", "nowheels-0.8-cp314-cp314t-win_arm64.whl")
    code, out, err = run(capsys, str(file), *OPTIONS)
    assert code == 1
    assert out == ""
    assert "requirements unchanged" in err
    assert file.read_text(encoding="utf-8") == "nowheels==0.9\n"
    assert not (tmp_path / "requirements.txt.wheelgap.bak").exists()


@pytest.mark.parametrize("text", [
    "nowheels==0.9 --hash=sha256:" + "a" * 64,
    "--require-hashes\nnowheels==0.9",
    "--index-url https://private.example/simple/\nnowheels==0.9",
    "--extra-index-url https://other.example/\nnowheels==0.9",
    "-r other.txt\nnowheels==0.9",
    "nowheels==0.9 \\\n --hash=sha256:" + "a" * 64,
    "nowheels @ https://other.example/a.whl",
    "--extra-index-url " + INDEX + "\n--index-url https://private.example/simple/",
    "--extra-index-url " + INDEX + "\n--extra-index-url " + INDEX,
])
def test_ambiguous_requirements_are_not_written(capsys, fake_pypi, gap_wheels, tmp_path, text):
    file = tmp_path / "requirements.txt"
    file.write_text(text + "\n", encoding="utf-8")
    gap_wheels.add("nowheels", "0.9", WHEEL)
    code, output, err = run(capsys, str(file), *OPTIONS)
    assert code == 2 and output == ""
    assert "wheelgap: error:" in err
    assert file.read_text(encoding="utf-8") == text + "\n"
    assert not (tmp_path / "requirements.txt.wheelgap.bak").exists()


def test_existing_backup_is_never_overwritten(tmp_path):
    file = tmp_path / "requirements.txt"
    file.write_text("nowheels==0.9\n", encoding="utf-8")
    backup = tmp_path / "requirements.txt.wheelgap.bak"
    backup.write_bytes(b"previous original")
    with pytest.raises(gapwheel_write.UnsafeRequirements, match="backup already exists"):
        gapwheel_write.apply_requirements_index(file)
    assert backup.read_bytes() == b"previous original"
    assert file.read_text(encoding="utf-8") == "nowheels==0.9\n"


def test_symlink_and_missing_input_are_refused_without_changes(tmp_path):
    target = tmp_path / "requirements-real.txt"
    target.write_text("nowheels==0.9\n", encoding="utf-8")
    symlink = tmp_path / "requirements.txt"
    symlink.symlink_to(target)
    with pytest.raises(gapwheel_write.UnsafeRequirements, match="symbolic link"):
        gapwheel_write.apply_requirements_index(symlink)
    assert target.read_text(encoding="utf-8") == "nowheels==0.9\n"
    with pytest.raises(gapwheel_write.UnsafeRequirements):
        gapwheel_write.apply_requirements_index(tmp_path / "missing.txt")


def test_utf8_bom_and_no_final_newline_preserved(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_bytes(b"\xef\xbb\xbfnowheels==0.9")
    assert gapwheel_write.apply_requirements_index(path)
    assert path.read_bytes() == b"\xef\xbb\xbf" + f"--extra-index-url {INDEX}\nnowheels==0.9".encode()


@pytest.mark.parametrize("args", [
    ["nowheels==0.9", *OPTIONS],
    ["requirements.txt", "--write-gap-wheel-config"],
    ["requirements.txt", *OPTIONS, "--print-gap-wheel-snippet"],
    ["requirements.txt", *OPTIONS, "--json"],
    ["requirements.txt", *OPTIONS, "--markdown"],
    ["requirements.txt", *OPTIONS, "--explain"],
])
def test_write_requires_explicit_file_and_safe_mode_before_lookup(
    capsys, fake_pypi, gap_wheels, tmp_path, monkeypatch, args
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "requirements.txt").write_text("nowheels==0.9\n", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert gap_wheels.calls == 0
    assert fake_pypi == []
