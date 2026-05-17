"""LogEntry round-trip: dataclass <-> JSON line."""

from __future__ import annotations

import json

import pytest

from antoine.kata.log._schema import LogEntry


def _entry() -> LogEntry:
    return LogEntry(
        ts="2026-05-17T14:22:01Z",
        session="sess-abc",
        agent="claude-code",
        tool="Bash",
        args_digest="sha256:" + "0" * 64,
        bash_argv0="git",
        tokens_in=1234,
        tokens_out=567,
        duration_ms=412,
    )


def test_logentry_to_json_line_is_one_line_with_trailing_newline() -> None:
    line = _entry().to_json_line()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    payload = json.loads(line)
    assert payload["tool"] == "Bash"
    assert payload["bash_argv0"] == "git"


def test_logentry_round_trip() -> None:
    original = _entry()
    line = original.to_json_line()
    restored = LogEntry.from_json_line(line)
    assert restored == original


def test_logentry_optional_fields_default_none() -> None:
    minimal = LogEntry(
        ts="2026-05-17T14:22:01Z",
        session="s",
        agent="claude-code",
        tool="Read",
        args_digest="sha256:" + "0" * 64,
    )
    assert minimal.bash_argv0 is None
    assert minimal.tokens_in is None
    assert minimal.tokens_out is None
    assert minimal.duration_ms is None
    # Round-trip preserves the None fields.
    assert LogEntry.from_json_line(minimal.to_json_line()) == minimal


def test_logentry_from_json_line_rejects_missing_required_field() -> None:
    line = '{"session": "s", "agent": "claude-code", "tool": "Read"}\n'
    with pytest.raises(ValueError, match="missing required field"):
        LogEntry.from_json_line(line)


def test_logentry_args_digest_must_be_sha256() -> None:
    with pytest.raises(ValueError, match="args_digest must start with 'sha256:'"):
        LogEntry(
            ts="2026-05-17T14:22:01Z",
            session="s",
            agent="claude-code",
            tool="Read",
            args_digest="md5:deadbeef",
        )
