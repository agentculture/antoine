"""Store layout: paths, append, read."""

from __future__ import annotations

from pathlib import Path

import pytest

from antoine.kata.log._schema import LogEntry
from antoine.kata.log._store import LogStore


def _entry(ts: str = "2026-05-17T14:22:01Z", session: str = "s") -> LogEntry:
    return LogEntry(
        ts=ts,
        session=session,
        agent="claude-code",
        tool="Bash",
        args_digest="sha256:" + "0" * 64,
        bash_argv0="git",
    )


def test_logstore_root_defaults_to_cwd_dot_antoine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store = LogStore()
    assert store.root == tmp_path / ".antoine" / "log"


def test_logstore_root_can_be_overridden(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path / "custom")
    assert store.root == tmp_path / "custom"


def test_append_creates_shape_file_per_day(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry(ts="2026-05-17T10:00:00Z"))
    store.append(_entry(ts="2026-05-17T23:59:59Z"))
    store.append(_entry(ts="2026-05-18T00:00:01Z"))

    files = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    assert files == ["2026-05-17.jsonl", "2026-05-18.jsonl"]


def test_append_writes_one_line_per_entry(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry())
    store.append(_entry(session="t"))

    lines = (tmp_path / "2026-05-17.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_read_all_returns_entries_in_chronological_order(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry(ts="2026-05-18T00:00:01Z"))
    store.append(_entry(ts="2026-05-17T10:00:00Z"))
    store.append(_entry(ts="2026-05-17T11:00:00Z"))

    ts_order = [e.ts for e in store.read_all()]
    assert ts_order == [
        "2026-05-17T10:00:00Z",
        "2026-05-17T11:00:00Z",
        "2026-05-18T00:00:01Z",
    ]


def test_read_all_on_empty_store_returns_empty_list(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    assert list(store.read_all()) == []


def test_read_all_skips_blank_lines(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry())
    # Simulate a malformed write (trailing blank).
    (tmp_path / "2026-05-17.jsonl").write_text(
        _entry().to_json_line() + "\n\n" + _entry(session="t").to_json_line()
    )
    sessions = [e.session for e in store.read_all()]
    assert sessions == ["s", "t"]


def test_read_all_raises_on_corrupt_line(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    (tmp_path / "2026-05-17.jsonl").write_text("not json\n")
    with pytest.raises(ValueError, match="log corrupted"):
        list(store.read_all())
