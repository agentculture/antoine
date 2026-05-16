"""Tests for seer.lookup.grep_context — D1 test suite."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, SeerError
from seer.lookup.grep_context import grep_with_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LIB_PY_SOURCE = '''\
_INIT_PY = "__init__.py"

def helper():
    return _INIT_PY

class Container:
    def method(self):
        return _INIT_PY
'''


def _make_rg_match_event(file_path: str, line_number: int, text: str) -> str:
    """Return a single rg --json 'match' event as a JSON string."""
    event: dict[str, Any] = {
        "type": "match",
        "data": {
            "path": {"text": file_path},
            "line_number": line_number,
            "lines": {"text": text + "\n"},
            "absolute_offset": 0,
            "submatches": [],
        },
    }
    return json.dumps(event)


def _rg_stdout_for(events: list[str]) -> str:
    """Join event lines into a stdout blob."""
    return "\n".join(events) + "\n"


# ---------------------------------------------------------------------------
# D1-a: basic — three matches across module level + function + method
# ---------------------------------------------------------------------------


def test_grep_basic_with_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib = tmp_path / "lib.py"
    lib.write_text(LIB_PY_SOURCE, encoding="utf-8")
    file_str = str(lib)

    stdout = _rg_stdout_for(
        [
            _make_rg_match_event(file_str, 1, '_INIT_PY = "__init__.py"'),
            _make_rg_match_event(file_str, 4, "    return _INIT_PY"),
            _make_rg_match_event(file_str, 8, "        return _INIT_PY"),
        ]
    )

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = grep_with_context("_INIT_PY", tmp_path)

    assert result["pattern"] == "_INIT_PY"
    matches = result["matches"]
    assert len(matches) == 3

    assert matches[0]["file"] == file_str
    assert matches[0]["line"] == 1
    assert matches[0]["scope"] is None  # module-level assignment
    assert matches[0]["text"] == '_INIT_PY = "__init__.py"'

    assert matches[1]["line"] == 4
    assert matches[1]["scope"] == "helper"
    assert matches[1]["text"] == "    return _INIT_PY"

    assert matches[2]["line"] == 8
    assert matches[2]["scope"] == "Container.method"
    assert matches[2]["text"] == "        return _INIT_PY"


# ---------------------------------------------------------------------------
# D1-b: no matches — rg exits 1, stdout empty
# ---------------------------------------------------------------------------


def test_grep_no_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "dummy.py").write_text("x = 1\n")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = grep_with_context("_INIT_PY", tmp_path)
    assert result["pattern"] == "_INIT_PY"
    assert result["matches"] == []


# ---------------------------------------------------------------------------
# D1-c: rg not found — FileNotFoundError → SeerError(EXIT_ENV_ERROR)
# ---------------------------------------------------------------------------


def test_grep_rg_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "dummy.py").write_text("x = 1\n")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        raise FileNotFoundError("No such file or directory: 'rg'")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SeerError) as exc_info:
        grep_with_context("_INIT_PY", tmp_path)

    err = exc_info.value
    assert err.code == EXIT_ENV_ERROR
    assert "rg" in err.message


# ---------------------------------------------------------------------------
# D1-d: non-Python file — scope is always None
# ---------------------------------------------------------------------------


def test_grep_non_python_file_scope_is_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Project\nSee _INIT_PY for details.\n")
    file_str = str(readme)

    stdout = _rg_stdout_for(
        [
            _make_rg_match_event(file_str, 2, "See _INIT_PY for details."),
        ]
    )

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = grep_with_context("_INIT_PY", tmp_path)
    assert len(result["matches"]) == 1
    assert result["matches"][0]["scope"] is None


# ---------------------------------------------------------------------------
# D1-e: path does not exist → SeerError(EXIT_USER_ERROR)
# ---------------------------------------------------------------------------


def test_grep_path_not_found() -> None:
    with pytest.raises(SeerError) as exc_info:
        grep_with_context("foo", "/nonexistent/path/that/does/not/exist")

    err = exc_info.value
    assert err.code == EXIT_USER_ERROR
