"""Tests for SeerError and the exit-code policy."""

from __future__ import annotations

from seer.cli._errors import (
    EXIT_ENV_ERROR,
    EXIT_INTERNAL,
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


def test_exit_internal_constant() -> None:
    assert EXIT_INTERNAL == 3


def test_seer_error_accepts_reason_and_kind() -> None:
    err = SeerError(
        code=1,
        kind="user_error",
        message="bad",
        reason="path not found",
        remediation="check the path",
    )
    assert err.reason == "path not found"
    assert err.kind == "user_error"


def test_seer_error_to_dict_includes_non_empty_optionals() -> None:
    err = SeerError(
        code=1,
        kind="user_error",
        message="bad",
        reason="path not found",
        remediation="check the path",
    )
    assert err.to_dict() == {
        "code": 1,
        "kind": "user_error",
        "message": "bad",
        "reason": "path not found",
        "remediation": "check the path",
    }


def test_seer_error_to_dict_omits_empty_optionals() -> None:
    err = SeerError(code=1, message="bad")
    assert err.to_dict() == {"code": 1, "message": "bad"}


def test_seer_error_to_dict_omits_only_empty_optionals() -> None:
    err = SeerError(code=2, message="bad", reason="missing tool")
    assert err.to_dict() == {
        "code": 2,
        "message": "bad",
        "reason": "missing tool",
    }
