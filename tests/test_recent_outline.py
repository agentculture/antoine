"""Tests for seer.lookup.recent_outline — E1 test suite."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from seer.cli._errors import EXIT_USER_ERROR, SeerError
from seer.lookup.recent_outline import recent_with_outline, render_recent_markdown

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(tmp_path: Path, *args: str) -> None:
    """Run a git command in tmp_path, raise on failure."""
    subprocess.run(  # noqa: S607
        ["git", "-C", str(tmp_path), *args],
        check=True,
        capture_output=True,
    )


def _make_repo(tmp_path: Path) -> Path:
    """Initialise a bare git repo with a local identity."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    return tmp_path


def _commit(tmp_path: Path, message: str) -> None:
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", message)


# ---------------------------------------------------------------------------
# E1-a: basic — two commits, Python file with added + modified symbols
# ---------------------------------------------------------------------------


def test_recent_outline_basic(tmp_path: Path) -> None:
    """Two commits: first adds foo, second adds bar and modifies foo's span."""
    _make_repo(tmp_path)

    # First commit: lib.py with function foo (3 lines)
    lib = tmp_path / "lib.py"
    lib.write_text(
        "def foo():\n" "    # body\n" "    return 1\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "first: add foo")

    # Second commit: add bar AND expand foo's body (changes line span)
    lib.write_text(
        "def foo():\n"
        "    # body\n"
        "    x = 1\n"
        "    return x\n"
        "\n"
        "def bar():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    _commit(tmp_path, "second: add bar, modify foo")

    data = recent_with_outline(n=2, path=tmp_path)

    assert "commits" in data
    commits = data["commits"]
    assert len(commits) == 2

    # newest first (second commit)
    second = commits[0]
    assert "sha" in second
    assert len(second["sha"]) == 7
    assert "date" in second
    assert "T" not in second["date"]  # just YYYY-MM-DD
    assert "subject" in second
    assert "changes" in second
    assert len(second["changes"]) == 1
    ch = second["changes"][0]
    assert ch["file"] == "lib.py"
    assert ch["added"] == ["bar"]
    assert ch["removed"] == []
    assert ch["modified"] == ["foo"]

    # oldest (first commit)
    first = commits[1]
    assert len(first["changes"]) == 1
    ch0 = first["changes"][0]
    assert ch0["file"] == "lib.py"
    assert ch0["added"] == ["foo"]
    assert ch0["removed"] == []
    assert ch0["modified"] == []


# ---------------------------------------------------------------------------
# E1-b: non-Python file — empty added/removed/modified
# ---------------------------------------------------------------------------


def test_recent_outline_non_python(tmp_path: Path) -> None:
    """A commit that only touches README.md produces empty symbol lists."""
    _make_repo(tmp_path)

    # Need at least one commit first
    (tmp_path / "lib.py").write_text("x = 1\n", encoding="utf-8")
    _commit(tmp_path, "init")

    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    _commit(tmp_path, "add readme")

    data = recent_with_outline(n=1, path=tmp_path)
    commits = data["commits"]
    assert len(commits) == 1
    ch = commits[0]["changes"][0]
    assert ch["file"] == "README.md"
    assert ch["added"] == []
    assert ch["removed"] == []
    assert ch["modified"] == []


# ---------------------------------------------------------------------------
# E1-c: no commits — empty repo
# ---------------------------------------------------------------------------


def test_recent_outline_empty_repo(tmp_path: Path) -> None:
    """A fresh git init with no commits returns {'commits': []}."""
    _make_repo(tmp_path)
    data = recent_with_outline(n=5, path=tmp_path)
    assert data == {"commits": []}


# ---------------------------------------------------------------------------
# E1-d: n=0 or negative → SeerError(EXIT_USER_ERROR)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_n", [0, -1, -100])
def test_recent_outline_bad_n(tmp_path: Path, bad_n: int) -> None:
    _make_repo(tmp_path)
    with pytest.raises(SeerError) as exc_info:
        recent_with_outline(n=bad_n, path=tmp_path)
    assert exc_info.value.code == EXIT_USER_ERROR


# ---------------------------------------------------------------------------
# E1-e: path is not a directory → SeerError(EXIT_USER_ERROR)
# ---------------------------------------------------------------------------


def test_recent_outline_bad_path(tmp_path: Path) -> None:
    non_dir = tmp_path / "does_not_exist"
    with pytest.raises(SeerError) as exc_info:
        recent_with_outline(n=5, path=non_dir)
    assert exc_info.value.code == EXIT_USER_ERROR


def test_recent_outline_path_is_file(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("hello\n")
    with pytest.raises(SeerError) as exc_info:
        recent_with_outline(n=5, path=f)
    assert exc_info.value.code == EXIT_USER_ERROR


# ---------------------------------------------------------------------------
# E1-f: render_recent_markdown output shape
# ---------------------------------------------------------------------------


def test_render_recent_markdown_basic() -> None:
    data = {
        "commits": [
            {
                "sha": "abc1234",
                "date": "2026-05-15",
                "subject": "feat: add bar",
                "changes": [
                    {
                        "file": "lib.py",
                        "added": ["bar"],
                        "removed": [],
                        "modified": ["foo"],
                    }
                ],
            }
        ]
    }
    md = render_recent_markdown(data)
    assert "### abc1234" in md
    assert "2026-05-15" in md
    assert "feat: add bar" in md
    assert "lib.py" in md
    assert "+bar" in md
    assert "~foo" in md


def test_render_recent_markdown_non_python() -> None:
    data = {
        "commits": [
            {
                "sha": "def5678",
                "date": "2026-05-14",
                "subject": "docs: update readme",
                "changes": [
                    {
                        "file": "README.md",
                        "added": [],
                        "removed": [],
                        "modified": [],
                    }
                ],
            }
        ]
    }
    md = render_recent_markdown(data)
    assert "### def5678" in md
    assert "README.md" in md
    # Non-python with empty lists: file listed without +/-/~ decoration
    assert "**README.md**" not in md


def test_render_recent_markdown_empty() -> None:
    data = {"commits": []}
    md = render_recent_markdown(data)
    assert "_No commits found._" in md
