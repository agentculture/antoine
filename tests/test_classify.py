"""Tests for seer.lookup.classify."""

from __future__ import annotations

from pathlib import Path

import pytest

from seer.cli._errors import EXIT_USER_ERROR, SeerError
from seer.lookup.classify import classify


def test_classify_empty_repo_returns_no_tags(tmp_path: Path) -> None:
    """Empty dir with no manifest, no markers — empty tag list, unknown language."""
    repo = tmp_path / "empty"
    repo.mkdir()
    result = classify(repo)
    assert result["path"] == str(repo)
    assert result["manifest"] is None
    assert result["language"] == "unknown"
    assert result["tags"] == []


def test_classify_path_not_found_raises_seer_error(tmp_path: Path) -> None:
    """Nonexistent path raises SeerError with EXIT_USER_ERROR code."""
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SeerError) as exc:
        classify(missing)
    assert exc.value.code == EXIT_USER_ERROR
    assert "path not found" in exc.value.message


def test_classify_path_is_file_raises_seer_error(tmp_path: Path) -> None:
    """File path raises SeerError with EXIT_USER_ERROR code and 'directory' hint."""
    f = tmp_path / "regular_file.txt"
    f.write_text("hi")
    with pytest.raises(SeerError) as exc:
        classify(f)
    assert exc.value.code == EXIT_USER_ERROR
    assert "directory" in exc.value.message
