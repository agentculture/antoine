"""Tests for SeerError and the exit-code policy."""

from __future__ import annotations

from seer.cli._errors import (
    EXIT_ENV_ERROR,
    EXIT_SUCCESS,
    EXIT_USER_ERROR,
    SeerError,
)


def test_exit_code_constants() -> None:
    assert EXIT_SUCCESS == 0
    assert EXIT_USER_ERROR == 1
    assert EXIT_ENV_ERROR == 2


def test_seer_error_is_an_exception() -> None:
    err = SeerError(code=1, message="bad input", remediation="try --help")
    assert isinstance(err, Exception)
    assert str(err) == "bad input"


def test_seer_error_to_dict() -> None:
    err = SeerError(code=2, message="missing tool", remediation="install it")
    assert err.to_dict() == {
        "code": 2,
        "message": "missing tool",
        "remediation": "install it",
    }


def test_remediation_defaults_to_empty() -> None:
    err = SeerError(code=1, message="x")
    assert err.remediation == ""
