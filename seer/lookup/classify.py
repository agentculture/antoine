"""Project-type classifier.

`classify(path)` returns a dict with `path`, `manifest`, `language`, and
`tags` (a list of `{name, evidence}` dicts). Per-tag rules are pure
functions of a `_Context` snapshot — one filesystem walk per call.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from seer.cli._errors import EXIT_USER_ERROR, SeerError
from seer.repo.errors import malformed_pyproject


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
    ctx = _Context(path=path)

    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            ctx.pyproject = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise malformed_pyproject(pyproject, str(e)) from e

    package_json = path / "package.json"
    if package_json.exists():
        try:
            ctx.package_json = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Treat malformed package.json the same as absent — Node tools handle
            # this gracefully; we don't need to fail the whole classify call.
            ctx.package_json = None

    scripts_dir = path / "scripts"
    if scripts_dir.is_dir():
        ctx.bash_scripts = sorted(p for p in scripts_dir.iterdir() if p.suffix == ".sh")

    return ctx


def _rule_python(ctx: _Context) -> dict[str, str] | None:
    if ctx.pyproject is None:
        return None
    return {"name": "python", "evidence": "pyproject.toml present"}


def _rule_node(ctx: _Context) -> dict[str, str] | None:
    if ctx.package_json is None:
        return None
    return {"name": "node", "evidence": "package.json present"}


def _rule_bash(ctx: _Context) -> dict[str, str] | None:
    if ctx.pyproject is not None or ctx.package_json is not None:
        return None
    if not ctx.bash_scripts:
        return None
    n = len(ctx.bash_scripts)
    file_word = "file" if n == 1 else "files"
    return {
        "name": "bash",
        "evidence": f"scripts/ contains {n} .sh {file_word}; no Python/Node manifest",
    }


def _rule_cli(ctx: _Context) -> dict[str, str] | None:
    # Python: [project.scripts] non-empty.
    if ctx.pyproject is not None:
        scripts = (ctx.pyproject.get("project", {}) or {}).get("scripts", {}) or {}
        if scripts:
            entries = ", ".join(f'{k} = "{v}"' for k, v in scripts.items())
            return {"name": "cli", "evidence": f"[project.scripts] defines {entries}"}
    # Node: package.json `bin` non-empty (object or string).
    if ctx.package_json is not None:
        bin_field = ctx.package_json.get("bin")
        if bin_field:
            if isinstance(bin_field, dict):
                names = ", ".join(bin_field.keys())
            else:
                names = ctx.package_json.get("name", "<unnamed>")
            return {"name": "cli", "evidence": f"package.json bin defines {names}"}
    return None


def _rule_library(ctx: _Context) -> dict[str, str] | None:
    """Importable Python package: `<name>/__init__.py` or `src/<name>/__init__.py`."""
    if ctx.pyproject is None:
        return None
    name = (ctx.pyproject.get("project", {}) or {}).get("name")
    if not name:
        return None
    # PyPI normalises hyphen vs underscore; check both possible package dir names.
    candidates = [name, name.replace("-", "_")]
    for candidate in candidates:
        flat = ctx.path / candidate / "__init__.py"
        if flat.exists():
            return {"name": "library", "evidence": f"`{candidate}/__init__.py` present"}
        nested = ctx.path / "src" / candidate / "__init__.py"
        if nested.exists():
            return {"name": "library", "evidence": f"`src/{candidate}/__init__.py` present"}
    return None


_RULES = [_rule_python, _rule_node, _rule_bash, _rule_cli, _rule_library]


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
