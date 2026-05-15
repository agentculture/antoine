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


def test_classify_python_manifest_fires_python_tag(tmp_path: Path) -> None:
    repo = tmp_path / "py"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "py"\nversion = "0.1.0"\n')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "python" in tag_names
    py_tag = next(t for t in result["tags"] if t["name"] == "python")
    assert py_tag["evidence"] == "pyproject.toml present"
    assert result["manifest"] == "pyproject.toml"
    assert result["language"] == "python"


def test_classify_node_manifest_fires_node_tag(tmp_path: Path) -> None:
    repo = tmp_path / "node"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "node-app", "version": "0.1.0"}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "node" in tag_names
    assert "python" not in tag_names
    node_tag = next(t for t in result["tags"] if t["name"] == "node")
    assert node_tag["evidence"] == "package.json present"
    assert result["manifest"] == "package.json"
    assert result["language"] == "node"


def test_classify_bash_only_fires_bash_tag(tmp_path: Path) -> None:
    repo = tmp_path / "bash"
    repo.mkdir()
    scripts = repo / "scripts"
    scripts.mkdir()
    (scripts / "foo.sh").write_text("#!/bin/bash\n")
    (scripts / "bar.sh").write_text("#!/bin/bash\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "bash" in tag_names
    assert "python" not in tag_names
    assert "node" not in tag_names
    bash_tag = next(t for t in result["tags"] if t["name"] == "bash")
    assert "scripts/" in bash_tag["evidence"]
    assert "2 .sh file" in bash_tag["evidence"]


def test_classify_polyglot_both_python_and_node_tags(tmp_path: Path) -> None:
    """Both manifests present → both tags fire; scalar language defaults to python."""
    repo = tmp_path / "poly"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "poly"\n')
    (repo / "package.json").write_text('{"name": "poly"}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "python" in tag_names
    assert "node" in tag_names
    assert result["language"] == "python"
    assert result["manifest"] == "pyproject.toml"
