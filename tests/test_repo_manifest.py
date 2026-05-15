"""Tests for seer.repo.manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, SeerError
from seer.repo.manifest import read_pyproject


def _write_pyproject(repo: Path, body: str) -> None:
    (repo / "pyproject.toml").write_text(body)


def test_read_pyproject_happy_path(tmp_path: Path) -> None:
    _write_pyproject(
        tmp_path,
        """
[project]
name = "demo"
version = "1.2.3"
dependencies = ["requests>=2.0", "pyyaml"]

[project.scripts]
demo-cli = "demo.cli:main"

[dependency-groups]
dev = ["pytest"]
""",
    )
    m = read_pyproject(tmp_path)
    assert m["name"] == "demo"
    assert m["version"] == "1.2.3"
    assert m["deps_runtime"] == ["requests>=2.0", "pyyaml"]
    assert m["entry_points"] == {"demo-cli": "demo.cli:main"}
    assert m["deps_dev"] == ["pytest"]


def test_read_pyproject_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SeerError) as exc:
        read_pyproject(tmp_path)
    assert exc.value.code == EXIT_USER_ERROR


def test_read_pyproject_malformed_toml_raises(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, '[project\nname = "x"')
    with pytest.raises(SeerError) as exc:
        read_pyproject(tmp_path)
    assert exc.value.code == EXIT_ENV_ERROR
    assert "pyproject.toml" in exc.value.message


def test_read_pyproject_missing_project_table_uses_defaults(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "[build-system]\nrequires = []\n")
    m = read_pyproject(tmp_path)
    assert m["name"] == tmp_path.name
    assert m["version"] == ""
    assert m["deps_runtime"] == []
    assert m["entry_points"] == {}
    assert m["deps_dev"] == []
