"""Args sidecar — raw args keyed by (session, row_index)."""

from __future__ import annotations

from pathlib import Path

import pytest

from antoine.kata.log._args import ArgsSidecar


def test_append_and_read_round_trip(tmp_path: Path) -> None:
    side = ArgsSidecar(root=tmp_path)
    side.append("sess-1", {"command": "git log --oneline"})
    side.append("sess-1", {"command": "git show HEAD"})
    side.append("sess-2", {"path": "README.md"})

    one = list(side.read("sess-1"))
    two = list(side.read("sess-2"))
    assert one == [
        {"command": "git log --oneline"},
        {"command": "git show HEAD"},
    ]
    assert two == [{"path": "README.md"}]


def test_read_unknown_session_returns_empty(tmp_path: Path) -> None:
    side = ArgsSidecar(root=tmp_path)
    assert list(side.read("nope")) == []


def test_sidecar_files_live_in_args_subdir(tmp_path: Path) -> None:
    side = ArgsSidecar(root=tmp_path)
    side.append("s", {"x": 1})
    assert (tmp_path / "args" / "s.jsonl").exists()
    # Top-level (shape) area is untouched.
    assert not (tmp_path / "s.jsonl").exists()


@pytest.mark.parametrize(
    "bad",
    [
        "../escape",  # path traversal
        "a/b",  # slash separator
        "a\\b",  # backslash separator
        "",  # empty
        ".",  # bare dot
        "..",  # parent ref
        "spaces ok?",  # whitespace + meta
    ],
)
def test_append_rejects_unsafe_session_ids(tmp_path: Path, bad: str) -> None:
    """An unsafe session id MUST raise rather than create a stray file.

    The args sidecar's privacy invariant relies on `kata log gc`'s flat
    `args/*.jsonl` scan reaching every file before TTL — a session id like
    `../escape` or `a/b` would silently bypass that. Reject at write time.
    """
    side = ArgsSidecar(root=tmp_path)
    with pytest.raises(ValueError, match="unsafe session id"):
        side.append(bad, {"x": 1})
    # No file was created anywhere under the root.
    assert list(tmp_path.rglob("*.jsonl")) == []
