"""Tests for seer.lookup.classify."""

from __future__ import annotations

from pathlib import Path

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
