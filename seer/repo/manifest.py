"""pyproject.toml reader with structured-error mapping."""

from __future__ import annotations

import tomllib
from pathlib import Path

from seer.repo.errors import malformed_pyproject, manifest_not_found


def read_pyproject(repo: Path) -> dict[str, object]:
    """Parse ``repo/pyproject.toml`` into a stable dict.

    Returns a dict with keys ``name``, ``version``, ``entry_points``,
    ``deps_runtime``, ``deps_dev``. Raises :class:`SeerError` (user_error)
    when the file is missing, or (env_error) when it cannot be parsed.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        raise manifest_not_found(repo)
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise malformed_pyproject(pyproject, str(e)) from e

    project = data.get("project", {}) or {}
    scripts = project.get("scripts", {}) or {}
    dep_groups = data.get("dependency-groups", {}) or {}

    return {
        "name": project.get("name") or repo.name,
        "version": project.get("version", ""),
        "entry_points": dict(scripts),
        "deps_runtime": list(project.get("dependencies", []) or []),
        "deps_dev": list(dep_groups.get("dev", []) or []),
    }
