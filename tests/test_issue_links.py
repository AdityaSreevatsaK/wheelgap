"""PyPI issue URL discovery never leaks private names or untrusted Markdown links."""

import json

import pytest

from wheelgap import pypi
from wheelgap.check import Row, Status
from wheelgap.cli import main
from wheelgap.issue_links import markdown_link, populate_issues_urls, project_issues_url
from wheelgap.sources import Package, Source
from wheelgap.targets import build_targets


@pytest.mark.parametrize(
    "links,expected",
    [
        ({"Issues": "https://github.com/org/repo/issues"}, "https://github.com/org/repo/issues"),
        ({"bUG TRACkeR": "https://bugs.example.org/new"}, "https://bugs.example.org/new"),
        ({"Tracker": "http://unsafe.invalid/issue", "Source": "https://github.com/org/repo"},
         "https://github.com/org/repo/issues"),
        ({"Homepage": "https://github.com/org/repo.git"}, "https://github.com/org/repo/issues"),
        ({"Homepage": "https://example.org/project"}, None),
        ({"Issues": "https://github.com/org/repo/issues\n::warning::bad"}, None),
        ({"Issues": "https://user:pass@example.org/issues"}, None),
        ({"Issues": "javascript:alert(1)"}, None),
    ],
)
def test_tracker_url_validation_and_precedence(links, expected):
    assert project_issues_url({"project_urls": links}) == expected


def test_tracker_link_escapes_markdown_punctuation():
    assert markdown_link("https://example.org/issue/(bug)") == "https://example.org/issue/%28bug%29"


def test_explain_text_markdown_and_json_add_tracker_link(monkeypatch, fake_pypi, capsys):
    original = pypi.fetch_json

    def fetch_with_tracker(url, **kwargs):
        data = original(url, **kwargs)
        if url.endswith("/nowheels/json") or url.endswith("/nowheels/0.9/json"):
            data["info"]["project_urls"] = {"Bug Tracker": "https://github.com/org/repo/issues"}
        return data

    monkeypatch.setattr(pypi, "fetch_json", fetch_with_tracker)
    args = ["nowheels==0.9", "-p", "3.13", "-t", "win-arm64", "--explain", "--no-cache"]
    for more, expected in (
        ([], "ask for a wheel: https://github.com/org/repo/issues"),
        (["--markdown"], "[issue tracker](https://github.com/org/repo/issues)"),
    ):
        code = main([*args, *more])
        out = capsys.readouterr().out
        assert code == 1
        assert expected in out
    assert main([*args, "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    pkg = next(p for p in data["packages"] if p["name"] == "nowheels")
    assert pkg["issues_url"] == "https://github.com/org/repo/issues"


def test_never_look_up_private_package_trackers(monkeypatch):
    urls = []

    def track(url, **kwargs):
        urls.append(url)
        raise AssertionError("private package URL leaked")

    monkeypatch.setattr(pypi, "fetch_json", track)
    target = build_targets(["3.13"], ["win-arm64"])[0]
    pkg = Package("private-pkg", "1.0", registry="https://private.example/simple")
    source = Source("private.lock", [pkg])
    populate_issues_urls([Row(pkg, {target: Status.SOURCE})], [source])
    assert pkg.issues_url is None
    assert urls == []
