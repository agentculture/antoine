"""Tests for seer.repo.profile (shallow path)."""

from __future__ import annotations

from pathlib import Path

from seer.repo.profile import profile_shallow


def _mk_fixture_repo(root: Path) -> Path:
    """Create a synthetic repo with every optional source populated."""
    root.mkdir()
    (root / "pyproject.toml").write_text("""
[project]
name = "demo"
version = "0.4.2"
dependencies = ["pyyaml"]

[project.scripts]
demo = "demo.cli:main"
""")
    (root / "demo").mkdir()
    (root / "demo" / "__init__.py").write_text("")
    (root / "CHANGELOG.md").write_text("""# Changelog

## [0.4.2] - 2026-05-10

### Added

- New feature.

## [0.4.1] - 2026-05-01

### Fixed

- A bug.

## [0.4.0] - 2026-04-20

### Added

- Initial.
""")
    (root / "CLAUDE.md").write_text("""# CLAUDE.md

## Project Status

Alpha. Coverage ratchet in progress.

## Architecture

Layers all the way down.
""")
    (root / "CITATION.md").write_text("""# Citations

| local | source | sha |
|---|---|---|
| src/x.py | other-repo | abc1234 |
""")
    (root / ".claude" / "skills" / "cicd").mkdir(parents=True)
    (root / "culture.yaml").write_text("agents:\n  - suffix: democult\n")
    return root


def test_profile_shallow_full_fixture(tmp_path: Path) -> None:
    """Full fixture repo exercises every optional source."""
    repo = _mk_fixture_repo(tmp_path / "demo")
    p = profile_shallow(repo)

    assert p["path"] == str(repo)
    assert p["name"] == "demo"
    assert p["version"] == "0.4.2"
    assert p["language"] == "python"
    assert p["manifest"] == "pyproject.toml"
    assert p["entry_points"] == {"demo": "demo.cli:main"}
    assert p["deps_runtime"] == ["pyyaml"]
    assert p["package_layout"] == ["demo/"]
    assert len(p["vendored_skills"]) == 1
    assert p["vendored_skills"][0]["name"] == "cicd"
    assert p["citations"] == [
        {"local": "src/x.py", "source_repo": "other-repo", "sha": "abc1234"},
    ]
    assert len(p["changelog_recent"]) == 3
    assert p["changelog_recent"][0]["version"] == "0.4.2"
    assert p["changelog_recent"][0]["date"] == "2026-05-10"
    assert "Alpha" in p["claude_md_status"]
    assert p["extra"].get("culture_nick") == "democult"


def test_profile_shallow_empty_repo(tmp_path: Path) -> None:
    """Repo with only pyproject.toml degrades silently on every optional source."""
    repo = tmp_path / "empty"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "e"\n')
    p = profile_shallow(repo)
    assert p["vendored_skills"] == []
    assert p["citations"] == []
    assert p["changelog_recent"] == []
    assert p["claude_md_status"] == ""
    assert p["extra"] == {}


def test_profile_shallow_no_manifest_repo(tmp_path: Path) -> None:
    """Repo with no pyproject.toml falls back to unknown language and dir name."""
    repo = tmp_path / "doc-only"
    (repo / ".claude" / "skills" / "x").mkdir(parents=True)
    p = profile_shallow(repo)
    assert p["language"] == "unknown"
    assert p["manifest"] is None
    assert p["name"] == "doc-only"
