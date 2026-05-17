"""Args sidecar — raw args keyed by (session, row_index)."""
from __future__ import annotations

from pathlib import Path

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
