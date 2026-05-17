"""Tests for antoine.repo.detect."""

from __future__ import annotations

from pathlib import Path

from antoine.repo.detect import find_repos, is_repo, resolve_name


def _mkrepo(
    path: Path, *, pyproject: bool = False, skills: bool = False, marker: str | None = None
) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if pyproject:
        (path / "pyproject.toml").write_text("[project]\nname='r'\n")
    if skills:
        (path / ".claude" / "skills").mkdir(parents=True)
    if marker:
        (path / marker).write_text("# marker\n")
    return path


def test_is_repo_pyproject(tmp_path: Path) -> None:
    r = _mkrepo(tmp_path / "r", pyproject=True)
    assert is_repo(r) is True


def test_is_repo_claude_skills(tmp_path: Path) -> None:
    r = _mkrepo(tmp_path / "r", skills=True)
    assert is_repo(r) is True


def test_is_repo_configured_marker(tmp_path: Path) -> None:
    r = _mkrepo(tmp_path / "r", marker="culture.yaml")
    assert is_repo(r, additional_markers=["culture.yaml"]) is True
    assert is_repo(r, additional_markers=["other.yaml"]) is False


def test_is_repo_none(tmp_path: Path) -> None:
    r = _mkrepo(tmp_path / "r")
    assert is_repo(r) is False


def test_is_repo_not_a_directory(tmp_path: Path) -> None:
    f = tmp_path / "file"
    f.write_text("")
    assert is_repo(f) is False


def test_find_repos_sorted_and_filtered(tmp_path: Path) -> None:
    _mkrepo(tmp_path / "alpha", pyproject=True)
    _mkrepo(tmp_path / "beta", skills=True)
    _mkrepo(tmp_path / ".venv", pyproject=True)  # in skip
    _mkrepo(tmp_path / "junk")  # not a repo
    repos = find_repos(tmp_path, skip_dirs=[".venv"])
    assert [r.name for r in repos] == ["alpha", "beta"]


def test_resolve_name_from_pyproject(tmp_path: Path) -> None:
    r = tmp_path / "rrr"
    r.mkdir()
    (r / "pyproject.toml").write_text('[project]\nname = "fancy-name"\n')
    assert resolve_name(r) == "fancy-name"


def test_resolve_name_from_culture_yaml(tmp_path: Path) -> None:
    r = tmp_path / "rrr"
    r.mkdir()
    (r / "culture.yaml").write_text("agents:\n  - suffix: clt-nick\n")
    assert resolve_name(r) == "clt-nick"


def test_resolve_name_falls_back_to_basename(tmp_path: Path) -> None:
    r = tmp_path / "basename-only"
    r.mkdir()
    assert resolve_name(r) == "basename-only"
