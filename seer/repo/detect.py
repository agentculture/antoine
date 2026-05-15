"""Generic repo detection + name resolution.

A directory is a "repo of interest" when ANY of the following is true:

  1. it contains ``pyproject.toml``
  2. it contains ``.claude/skills/``
  3. it contains any file listed in ``additional_markers``

Name resolution prefers, in order:

  1. ``[project].name`` from ``pyproject.toml``
  2. ``agents[0].suffix`` (or ``.nick``) from ``culture.yaml``
  3. the directory basename
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml


def is_repo(path: Path, additional_markers: list[str] | None = None) -> bool:
    """Return True if ``path`` qualifies as a repo of interest."""
    if not path.is_dir():
        return False
    if (path / "pyproject.toml").exists():
        return True
    if (path / ".claude" / "skills").is_dir():
        return True
    for marker in additional_markers or []:
        if (path / marker).exists():
            return True
    return False


def find_repos(
    root: Path,
    *,
    additional_markers: list[str] | None = None,
    skip_dirs: list[str] | None = None,
) -> list[Path]:
    """Return the sorted list of child directories under ``root`` that qualify as repos."""
    skip = set(skip_dirs or [])
    repos: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir() or child.name in skip:
            continue
        if is_repo(child, additional_markers):
            repos.append(child)
    return sorted(repos, key=lambda p: p.name)


def _name_from_pyproject(path: Path) -> str | None:
    """Return ``[project].name`` from *path*'s ``pyproject.toml`` if present and parseable."""
    pyproject = path / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    name = (data.get("project") or {}).get("name")
    return str(name) if name else None


def _name_from_culture_yaml(path: Path) -> str | None:
    """Return the first agent's nick (``suffix`` or ``nick``) from ``culture.yaml`` if any."""
    culture_yaml = path / "culture.yaml"
    if not culture_yaml.exists():
        return None
    try:
        data = yaml.safe_load(culture_yaml.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    agents = data.get("agents", [])
    if not agents or not isinstance(agents[0], dict):
        return None
    nick = agents[0].get("suffix") or agents[0].get("nick")
    return str(nick) if nick else None


def resolve_name(path: Path) -> str:
    """Return the repo's preferred name (pyproject → culture.yaml → basename)."""
    return _name_from_pyproject(path) or _name_from_culture_yaml(path) or path.name
