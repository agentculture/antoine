"""Tests for the ``antoine recent`` CLI verb — E2 test suite."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from antoine.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(tmp_path: Path, *args: str) -> None:
    subprocess.run(  # noqa: S607
        ["git", "-C", str(tmp_path), *args],
        check=True,
        capture_output=True,
    )


def _make_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    return tmp_path


def _commit(tmp_path: Path, message: str) -> None:
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", message)


# ---------------------------------------------------------------------------
# E2-a: recent appears in top-level help text
# ---------------------------------------------------------------------------


def test_recent_verb_in_help_text(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "recent" in out


# ---------------------------------------------------------------------------
# E2-b: --help works without error
# ---------------------------------------------------------------------------


def test_recent_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["recent", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "recent" in out


# ---------------------------------------------------------------------------
# E2-c: end-to-end JSON mode
# ---------------------------------------------------------------------------


def test_recent_json_shape(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Build a real git repo, call recent --json, assert JSON shape."""
    _make_repo(tmp_path)

    lib = tmp_path / "lib.py"
    lib.write_text("def foo():\n    return 1\n", encoding="utf-8")
    _commit(tmp_path, "add foo")

    lib.write_text(
        "def foo():\n    x = 1\n    return x\n\ndef bar():\n    return 2\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "add bar, modify foo")

    rc = main(["recent", str(tmp_path), "-n", "2", "--json"])
    assert rc == 0

    data = json.loads(capsys.readouterr().out)
    assert "commits" in data
    commits = data["commits"]
    assert len(commits) == 2

    # newest first
    newest = commits[0]
    assert len(newest["sha"]) == 7
    assert "T" not in newest["date"]
    assert "changes" in newest

    # The lib.py change has bar added and foo modified
    lib_change = next(c for c in newest["changes"] if c["file"] == "lib.py")
    assert "bar" in lib_change["added"]
    assert "foo" in lib_change["modified"]


# ---------------------------------------------------------------------------
# E2-d: end-to-end Markdown mode renders ### headers
# ---------------------------------------------------------------------------


def test_recent_markdown_headers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Markdown mode output contains ### commit headers."""
    _make_repo(tmp_path)

    (tmp_path / "lib.py").write_text("def alpha():\n    pass\n", encoding="utf-8")
    _commit(tmp_path, "initial commit")

    rc = main(["recent", str(tmp_path), "-n", "1"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "###" in out
    assert "initial commit" in out


# ---------------------------------------------------------------------------
# E2-e: default path is cwd, default n is 20
# ---------------------------------------------------------------------------


def test_recent_defaults_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When no path or -n given, recent uses '.' and 20 commits."""
    _make_repo(tmp_path)
    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    _commit(tmp_path, "commit x")

    monkeypatch.chdir(tmp_path)
    rc = main(["recent", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "commits" in data
