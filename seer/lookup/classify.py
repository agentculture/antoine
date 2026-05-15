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

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, SeerError
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


_COMPOSE_FILENAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


def _load_pyproject(path: Path) -> dict | None:
    """Parse `path/pyproject.toml` or return None if absent.

    Raises `SeerError(EXIT_ENV_ERROR)` if the file exists but is unreadable
    (OS error, non-UTF8) or malformed (invalid TOML).
    """
    pyproject = path / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        text = pyproject.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise _pyproject_unreadable_error(pyproject, str(e)) from e
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise malformed_pyproject(pyproject, str(e)) from e


def _load_package_json(path: Path) -> dict | None:
    """Parse `path/package.json` or return None if absent / unreadable / malformed.

    Soft-fails on any read/decode/parse error — Node tools handle missing or
    bad manifests gracefully and we follow the same "fail-soft for optional
    sources" pattern here.
    """
    package_json = path / "package.json"
    if not package_json.exists():
        return None
    try:
        return json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _detect_compose(path: Path) -> str | None:
    """Return the first matching compose filename present at *path*, or None."""
    for compose in _COMPOSE_FILENAMES:
        if (path / compose).exists():
            return compose
    return None


def _build_context(path: Path) -> _Context:
    """Walk *path* once and capture every signal the rule set needs."""
    ctx = _Context(path=path)
    ctx.pyproject = _load_pyproject(path)
    ctx.package_json = _load_package_json(path)

    scripts_dir = path / "scripts"
    if scripts_dir.is_dir():
        ctx.bash_scripts = sorted(p for p in scripts_dir.iterdir() if p.suffix == ".sh")

    ctx.has_dockerfile = (path / "Dockerfile").exists()
    compose = _detect_compose(path)
    if compose is not None:
        ctx.has_compose = True
        ctx.compose_filename = compose

    ctx.has_culture_yaml = (path / "culture.yaml").exists()
    ctx.has_tests_dir = (path / "tests").is_dir()

    workflows_dir = path / ".github" / "workflows"
    if workflows_dir.is_dir():
        ctx.workflow_files = sorted(
            p for p in workflows_dir.iterdir() if p.suffix in (".yml", ".yaml")
        )

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


def _rule_dockerized(ctx: _Context) -> dict[str, str] | None:
    if ctx.has_dockerfile:
        return {"name": "dockerized", "evidence": "Dockerfile present"}
    if ctx.has_compose and ctx.compose_filename:
        return {"name": "dockerized", "evidence": f"{ctx.compose_filename} present"}
    return None


def _rule_tested(ctx: _Context) -> dict[str, str] | None:
    if not ctx.has_tests_dir:
        return None
    # Python path: pytest in [dependency-groups] dev
    if ctx.pyproject is not None:
        dev_deps = (ctx.pyproject.get("dependency-groups", {}) or {}).get("dev", []) or []
        # Strip version spec: pytest>=8.0 -> pytest; pytest==8.1 -> pytest; etc.
        dep_names = {d.split(">=")[0].split("==")[0].split("~=")[0].strip() for d in dev_deps}
        if "pytest" in dep_names:
            return {
                "name": "tested",
                "evidence": "tests/ exists; pytest in dependency-groups.dev",
            }
    # Node path: scripts.test defined
    if ctx.package_json is not None:
        scripts = ctx.package_json.get("scripts", {}) or {}
        if scripts.get("test"):
            return {
                "name": "tested",
                "evidence": f"tests/ exists; package.json scripts.test = {scripts['test']!r}",
            }
    return None


def _rule_packaged_pypi(ctx: _Context) -> dict[str, str] | None:
    needles = ("pypi.org", "pypa/gh-action-pypi-publish")
    for wf in ctx.workflow_files:
        try:
            text = wf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Best-effort: skip unreadable / undecodable workflow files
            # rather than aborting classification.
            continue
        if any(needle in text for needle in needles):
            return {
                "name": "packaged-pypi",
                "evidence": f".github/workflows/{wf.name} uploads to pypi.org",
            }
    return None


def _rule_agentculture_sibling(ctx: _Context) -> dict[str, str] | None:
    if ctx.has_culture_yaml:
        return {"name": "agentculture-sibling", "evidence": "culture.yaml present"}
    return None


_RULES = [
    _rule_python,
    _rule_node,
    _rule_bash,
    _rule_cli,
    _rule_library,
    _rule_dockerized,
    _rule_tested,
    _rule_packaged_pypi,
    _rule_agentculture_sibling,
]


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


def _pyproject_unreadable_error(p: Path, detail: str) -> SeerError:
    return SeerError(
        code=EXIT_ENV_ERROR,
        kind="env_error",
        message=f"cannot read pyproject.toml at {p}",
        reason=f"OS or decode error while reading the manifest: {detail}",
        remediation=("check file permissions and confirm the file is valid UTF-8."),
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
