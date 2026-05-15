"""Tests for seer.repo.errors factory functions."""

from __future__ import annotations

from pathlib import Path

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, SeerError
from seer.repo import errors


def test_manifest_not_found() -> None:
    err = errors.manifest_not_found(Path("/x/nope"))
    assert isinstance(err, SeerError)
    assert err.code == EXIT_USER_ERROR
    assert err.kind == "user_error"
    assert "/x/nope" in err.message
    assert err.reason
    assert err.remediation


def test_malformed_pyproject() -> None:
    err = errors.malformed_pyproject(Path("/x/pyproject.toml"), "bad bracket")
    assert err.code == EXIT_ENV_ERROR
    assert err.kind == "env_error"
    assert "pyproject.toml" in err.message
    assert "bad bracket" in err.reason
    assert err.remediation


def test_invalid_depth() -> None:
    err = errors.invalid_depth("foo")
    assert err.code == EXIT_USER_ERROR
    assert err.kind == "user_error"
    assert "foo" in err.message
    assert "depth" in err.reason.lower()
    assert "all" in err.remediation


def test_path_not_a_directory() -> None:
    err = errors.path_not_a_directory(Path("/x/nope"))
    assert err.code == EXIT_USER_ERROR
    assert err.kind == "user_error"
    assert "/x/nope" in err.message
    assert err.reason and err.remediation


def test_seed_not_under_root() -> None:
    err = errors.seed_not_under_root(Path("/x/seed"), [Path("/home/spark/git")])
    assert err.code == EXIT_USER_ERROR
    assert "/x/seed" in err.message
    assert "/home/spark/git" in err.reason
    assert err.remediation
