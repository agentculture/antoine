"""Tests for the antoine CLI chassis (verbs are registered in later commits)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from antoine import __version__
from antoine.cli import main


def test_version_flag_exits_zero_and_prints_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_args_prints_help_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main([])
    assert rc == 0
    assert "usage: antoine" in capsys.readouterr().out


def test_unknown_verb_routes_through_structured_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["definitely-not-a-verb"])
    assert exc.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_python_dash_m_invocation() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "antoine", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout
