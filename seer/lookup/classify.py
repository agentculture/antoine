"""Project-type classifier.

`classify(path)` returns a dict with `path`, `manifest`, `language`, and
`tags` (a list of `{name, evidence}` dicts). Per-tag rules are pure
functions of a `_Context` snapshot — one filesystem walk per call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from seer.cli._errors import EXIT_USER_ERROR, SeerError


@dataclass
class _Context:
    """Filesystem snapshot consumed by per-tag rules. One walk per classify() call."""

    path: Path
    pyproject: dict | None = None
    package_json: dict | None = None
    bash_scripts: list[Path] = field(default_factory=list)
    has_dockerfile: bool = False
    has_compose: bool = False
    compose_filename: str | None = None
    has_tests_dir: bool = False
    workflow_files: list[Path] = field(default_factory=list)
    has_culture_yaml: bool = False


def _build_context(path: Path) -> _Context:
    """Walk *path* once and capture every signal the rule set needs."""
    return _Context(path=path)


# Per-tag rules will be added in Tasks 3-6. Empty list for now.
_RULES: list = []


def _path_not_found_error(p: Path) -> SeerError:
    return SeerError(
        code=EXIT_USER_ERROR,
        kind="user_error",
        message=f"path not found: {p}",
        reason="classify expected a directory path that exists on disk.",
        remediation="check the path argument and retry.",
    )


def _path_not_a_directory_error(p: Path) -> SeerError:
    return SeerError(
        code=EXIT_USER_ERROR,
        kind="user_error",
        message=f"classify expects a directory, got file: {p}",
        reason="classify operates on a repository root, not a single file.",
        remediation="pass the parent directory.",
    )


def classify(path: Path) -> dict[str, object]:
    """Return `{path, manifest, language, tags}` for the repo at *path*."""
    if not path.exists():
        raise _path_not_found_error(path)
    if not path.is_dir():
        raise _path_not_a_directory_error(path)

    ctx = _build_context(path)
    tags: list[dict[str, str]] = []
    for rule in _RULES:
        result = rule(ctx)
        if result is not None:
            tags.append(result)

    # Manifest + language derivation. Python wins over Node when both present
    # (see spec — polyglot caller should read the tag list, not the scalar).
    if ctx.pyproject is not None:
        manifest: str | None = "pyproject.toml"
        language = "python"
    elif ctx.package_json is not None:
        manifest = "package.json"
        language = "node"
    else:
        manifest = None
        language = "unknown"

    return {
        "path": str(path),
        "manifest": manifest,
        "language": language,
        "tags": tags,
    }
