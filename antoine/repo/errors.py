"""Domain-specific :class:`AntoineError` factories for antoine.repo.

Centralising error construction here keeps message / reason / remediation
copy uniform across every raise site.
"""

from __future__ import annotations

from pathlib import Path

from antoine.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, AntoineError


def manifest_not_found(path: Path) -> AntoineError:
    """Return a AntoineError for a missing pyproject.toml manifest."""
    return AntoineError(
        code=EXIT_USER_ERROR,
        kind="user_error",
        message=f"Cannot find pyproject.toml in {path}",
        reason=(
            "No recognized manifest at the given path. Looked for "
            "pyproject.toml, .claude/skills/, and any configured "
            "additional_markers."
        ),
        remediation=(
            "Confirm the path points to a repo root, not a subdirectory. "
            "To treat this directory as a repo regardless, add a marker "
            "via .claude/skills/repo-map/config.json → additional_markers."
        ),
    )


def malformed_pyproject(path: Path, detail: str) -> AntoineError:
    """Return a AntoineError for a pyproject.toml that exists but won't parse."""
    return AntoineError(
        code=EXIT_ENV_ERROR,
        kind="env_error",
        message=f"Cannot parse {path}",
        reason=f"TOML syntax error: {detail}",
        remediation=(
            f'Validate with `python3 -c "import tomllib; '
            f"tomllib.load(open('{path}', 'rb'))\"` or fix the file."
        ),
    )


def invalid_depth(value: str) -> AntoineError:
    """Return a AntoineError for a `--depth` value that is neither a non-negative int nor 'all'."""
    return AntoineError(
        code=EXIT_USER_ERROR,
        kind="user_error",
        message=f"Invalid --depth value: '{value}'",
        reason="--depth must be a non-negative integer or 'all'.",
        remediation="Try `--depth 1` (default), `--depth 3`, or `--depth all`.",
    )


def path_not_a_directory(path: Path) -> AntoineError:
    """Return a AntoineError for a path that doesn't exist or isn't a directory."""
    return AntoineError(
        code=EXIT_USER_ERROR,
        kind="user_error",
        message=f"Path does not exist or is not a directory: {path}",
        reason="The given path was not a directory on disk.",
        remediation="Pass an absolute path to an existing directory.",
    )


def seed_not_under_root(seed: Path, roots: list[Path]) -> AntoineError:
    """Return a AntoineError for a seed repo that doesn't live under any configured root."""
    root_list = ", ".join(str(r) for r in roots)
    return AntoineError(
        code=EXIT_USER_ERROR,
        kind="user_error",
        message=f"Seed repo {seed} is not under any configured root",
        reason=f"Edge resolution requires the seed to live in a configured root: {root_list}.",
        remediation=(
            "Pass --root, or add the seed's parent to "
            ".claude/skills/repo-map/config.json `roots`."
        ),
    )
