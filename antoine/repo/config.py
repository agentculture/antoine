"""Per-workspace defaults for repo-map.

Loaded from `.claude/skills/repo-map/config.json` (or any path the caller
passes). Missing file => defaults; missing keys => per-key defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SKIP_DIRS: tuple[str, ...] = (
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
)


def _default_roots() -> list[Path]:
    """Return the default root search path list."""
    return [Path.home() / "git"]


def _default_skip_dirs() -> list[str]:
    """Return the default list of directory names to skip during traversal."""
    return list(DEFAULT_SKIP_DIRS)


@dataclass
class RepoMapConfig:
    """Per-workspace defaults consumed by every repo-map verb."""

    roots: list[Path] = field(default_factory=_default_roots)
    additional_markers: list[str] = field(default_factory=list)
    skip_dirs: list[str] = field(default_factory=_default_skip_dirs)
    default_connections_depth: int = 1


def load_config(path: Path | None = None) -> RepoMapConfig:
    """Load config from `path` (default `.claude/skills/repo-map/config.json`).

    Returns :class:`RepoMapConfig` with defaults filled in for missing keys.
    Raises :exc:`json.JSONDecodeError` if the file exists but is not valid JSON.
    """
    if path is None:
        path = Path(".claude/skills/repo-map/config.json")
    if not path.exists():
        return RepoMapConfig()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return RepoMapConfig(
        roots=([Path(r) for r in raw["roots"]] if "roots" in raw else _default_roots()),
        additional_markers=list(raw.get("additional_markers", [])),
        skip_dirs=list(raw.get("skip_dirs", DEFAULT_SKIP_DIRS)),
        default_connections_depth=int(raw.get("default_connections_depth", 1)),
    )
