"""Temporary CI-only import formatting diagnostic."""

import subprocess


def test_ruff_import_layout_matches_configuration():
    result = subprocess.run(
        ["ruff", "check", "--select", "I", "--diff", "src/wheelgap/issue_links.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
