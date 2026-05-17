"""`kata log` CLI: parent + 3 subcommands wired."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from antoine.cli import main


def test_log_with_no_subcommand_prints_help_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["log"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tail" in out
    assert "gc" in out
    assert "grep" in out


def test_log_unknown_subcommand_exits_one_with_remediation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["log", "nope"])
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "log --help" in err


def _seed_log(root: Path, count: int = 3) -> None:
    """Write `count` synthetic entries into root/2026-05-17.jsonl."""
    root.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(count):
        lines.append(
            json.dumps(
                {
                    "ts": f"2026-05-17T10:00:{i:02d}Z",
                    "session": f"s{i}",
                    "agent": "claude-code",
                    "tool": "Bash",
                    "args_digest": "sha256:" + "0" * 64,
                    "bash_argv0": "git",
                }
            )
        )
    (root / "2026-05-17.jsonl").write_text("\n".join(lines) + "\n")


def test_log_tail_prints_last_n_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_log(tmp_path / ".antoine" / "log", count=5)

    rc = main(["log", "tail", "-n", "2"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2
    # Last two entries: s3, s4.
    assert "s3" in out[0]
    assert "s4" in out[1]


def test_log_tail_default_n_is_10(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_log(tmp_path / ".antoine" / "log", count=3)
    rc = main(["log", "tail"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3  # only 3 in store; tail caps at what's there


def test_log_tail_with_empty_store_exits_two_with_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["log", "tail"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "No capture data" in err
    assert "kata learn" in err  # remediation hint
