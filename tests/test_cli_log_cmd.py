"""`kata log` CLI: parent + 3 subcommands wired."""

from __future__ import annotations

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
