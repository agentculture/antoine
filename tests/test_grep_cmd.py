"""Tests for the ``seer grep`` CLI verb — D2 test suite."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from seer.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


LIB_PY_SOURCE = """\
_INIT_PY = "__init__.py"

def helper():
    return _INIT_PY
"""


# ---------------------------------------------------------------------------
# D2-a: grep appears in top-level help text
# ---------------------------------------------------------------------------


def test_grep_verb_in_help_text(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "grep" in out


# ---------------------------------------------------------------------------
# D2-b: JSON output shape
# ---------------------------------------------------------------------------


def test_grep_json_output_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lib = tmp_path / "lib.py"
    lib.write_text(LIB_PY_SOURCE, encoding="utf-8")
    file_str = str(lib)

    stdout_blob = (
        _make_rg_match_event(file_str, 1, '_INIT_PY = "__init__.py"')
        + "\n"
        + _make_rg_match_event(file_str, 4, "    return _INIT_PY")
        + "\n"
    )

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, returncode=0, stdout=stdout_blob, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    rc = main(["grep", "_INIT_PY", str(tmp_path), "--json"])
    assert rc == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert data["pattern"] == "_INIT_PY"
    assert isinstance(data["matches"], list)
    assert len(data["matches"]) == 2

    first = data["matches"][0]
    assert first["file"] == file_str
    assert first["line"] == 1
    assert first["scope"] is None  # module-level
    assert first["text"] == '_INIT_PY = "__init__.py"'

    second = data["matches"][1]
    assert second["line"] == 4
    assert second["scope"] == "helper"


# ---------------------------------------------------------------------------
# D2-c: markdown output (default, no --json)
# ---------------------------------------------------------------------------


def test_grep_markdown_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lib = tmp_path / "lib.py"
    lib.write_text(LIB_PY_SOURCE, encoding="utf-8")
    file_str = str(lib)

    stdout_blob = _make_rg_match_event(file_str, 4, "    return _INIT_PY") + "\n"

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, returncode=0, stdout=stdout_blob, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    rc = main(["grep", "_INIT_PY", str(tmp_path)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "grep" in out
    assert "| File | Line | Scope | Text |" in out
    assert "helper" in out


# ---------------------------------------------------------------------------
# D2-d: no matches — empty matches list in JSON mode
# ---------------------------------------------------------------------------


def test_grep_json_no_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "dummy.py").write_text("x = 1\n")

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return CompletedProcess(cmd, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    rc = main(["grep", "PATTERN_NOT_FOUND", str(tmp_path), "--json"])
    assert rc == 0

    data = json.loads(capsys.readouterr().out)
    assert data["matches"] == []
