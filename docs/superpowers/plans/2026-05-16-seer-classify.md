# `seer classify` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `seer classify [path]` — a new verb that returns a deterministic list of project-type tags (e.g. `python`, `cli`, `library`, `dockerized`, `tested`, `packaged-pypi`, `agentculture-sibling`) each paired with the concrete file-grounded evidence that fired it, in one tool call.

**Architecture:** New package `seer/lookup/` (engine + renderer) wired as a new sub-command on the existing CLI chassis (`seer/cli/_commands/classify.py`). Reuses `seer.repo.manifest.read_pyproject`, the chassis's `SeerError` routing, the `--json` flag plumbing, and `emit_result`. A single `_Context` walk gathers all filesystem signals once; per-tag rules are pure functions of that context. New companion skill `.claude/skills/code-lookup/` (sibling to `repo-map`) houses the SKILL.md + a shell wrapper that calls `python -m seer classify`.

**Tech Stack:** Python 3.12, `tomllib` (stdlib), `json` (stdlib), `pathlib`, pytest + pytest-xdist + pytest-cov, uv. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-05-16-seer-classify-design.md` (committed in `d597904`).

---

## File Structure

**Create:**
- `seer/lookup/__init__.py` — public re-exports (`classify`, `render_classify_markdown`).
- `seer/lookup/classify.py` — `_Context` builder + per-tag rule functions + top-level `classify(path)` entry.
- `seer/lookup/render.py` — `render_classify_markdown(data: dict) -> str`.
- `seer/cli/_commands/classify.py` — `cmd_classify(args)` + `register(sub)`. Mirrors `seer/cli/_commands/learn.py` shape.
- `.claude/skills/code-lookup/SKILL.md` — frontmatter enumerating output fields + token-math + when-NOT-to-use, plus a short body.
- `.claude/skills/code-lookup/scripts/classify.sh` — shell wrapper: `exec uv run --directory "$PROJECT_ROOT" python -m seer classify "$@"`. Marked executable.
- `tests/test_classify.py` — engine tests (one per tag rule + validation + edge cases).
- `tests/test_classify_render.py` — markdown renderer tests.

**Modify:**
- `seer/cli/__init__.py` — import + register `classify` alongside `learn` / `explain` / `whoami` (around line 60-68).
- `docs/skill-sources.md` — add row for `code-lookup` (seer-cli-original skill, like `repo-map`).
- `pyproject.toml` — bump `version = "0.4.1"` → `"0.4.2"`.
- `CHANGELOG.md` — prepend `## [0.4.2] - 2026-05-16` entry.

**Total new files: 8 (incl. shell wrapper). Total modified: 4.** Each touch is a small, scoped change.

---

## Tag rule reference (used by Tasks 3-6)

Every rule receives the `_Context` and returns `dict | None` of shape `{"name": str, "evidence": str}`. Tags appear in the output in the order rules are registered in `_RULES`:

| Order | Tag | Rule signature | Fires when |
|---|---|---|---|
| 1 | `python` | `_rule_python(ctx)` | `ctx.pyproject is not None` |
| 2 | `node` | `_rule_node(ctx)` | `ctx.package_json is not None` |
| 3 | `bash` | `_rule_bash(ctx)` | `ctx.bash_scripts` non-empty AND `ctx.pyproject is None` AND `ctx.package_json is None` |
| 4 | `cli` | `_rule_cli(ctx)` | Python `[project.scripts]` non-empty OR Node `package.json` `bin` non-empty |
| 5 | `library` | `_rule_library(ctx)` | An importable `<name>/__init__.py` or `src/<name>/__init__.py` exists |
| 6 | `dockerized` | `_rule_dockerized(ctx)` | `Dockerfile` exists OR `docker-compose.yml` / `compose.yml` exists |
| 7 | `tested` | `_rule_tested(ctx)` | `tests/` dir exists AND (`pytest` is in pyproject `[dependency-groups] dev` OR `package.json` has a `scripts.test` field) |
| 8 | `packaged-pypi` | `_rule_packaged_pypi(ctx)` | Any `.github/workflows/*.yml` text contains `pypi.org` or `pypa/gh-action-pypi-publish` |
| 9 | `agentculture-sibling` | `_rule_agentculture_sibling(ctx)` | `culture.yaml` exists |

---

## Task 1: Scaffold the package + register the empty verb

**Files:**
- Create: `seer/lookup/__init__.py`
- Create: `seer/lookup/classify.py`
- Create: `seer/lookup/render.py`
- Create: `seer/cli/_commands/classify.py`
- Modify: `seer/cli/__init__.py:60-68`
- Create: `tests/test_classify.py`

This task wires the verb end-to-end with **zero tag rules**: `seer classify .` succeeds and returns `tags: []`. It establishes the test+CLI scaffolding so subsequent tasks only add rules.

- [ ] **Step 1: Write the failing skeleton test**

Create `tests/test_classify.py`:

```python
"""Tests for seer.lookup.classify."""

from __future__ import annotations

from pathlib import Path

from seer.lookup.classify import classify


def test_classify_empty_repo_returns_no_tags(tmp_path: Path) -> None:
    """Empty dir with no manifest, no markers — empty tag list, unknown language."""
    repo = tmp_path / "empty"
    repo.mkdir()
    result = classify(repo)
    assert result["path"] == str(repo)
    assert result["manifest"] is None
    assert result["language"] == "unknown"
    assert result["tags"] == []
```

- [ ] **Step 2: Run the test and confirm it fails (no module yet)**

Run: `uv run pytest tests/test_classify.py -v`

Expected: `ModuleNotFoundError: No module named 'seer.lookup'`.

- [ ] **Step 3: Create the engine package skeleton**

Create `seer/lookup/__init__.py`:

```python
"""seer.lookup — codebase classification + lookup verbs.

This package is the sibling of `seer.repo`: it answers "what kind of project
is this?" / "where is X?" rather than "tell me about this repo."
"""

from __future__ import annotations

from seer.lookup.classify import classify
from seer.lookup.render import render_classify_markdown

__all__ = ["classify", "render_classify_markdown"]
```

Create `seer/lookup/classify.py`:

```python
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
```

Create `seer/lookup/render.py`:

```python
"""Markdown emitter for seer.lookup.classify."""

from __future__ import annotations

from typing import Any


def render_classify_markdown(data: dict[str, Any]) -> str:
    """Render a classify() dict as a markdown report."""
    # Filled in by Task 7. Placeholder until then so the package imports clean.
    return ""
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `uv run pytest tests/test_classify.py -v`

Expected: PASS. The test only asserts on the scaffold's empty-repo return shape.

- [ ] **Step 5: Wire the verb into the CLI chassis**

Create `seer/cli/_commands/classify.py`:

```python
"""``seer classify [path]`` — project-type classifier.

Returns a deterministic list of tags describing what kind of project the
repo at *path* is (cli / library / dockerized / tested / packaged-pypi / …),
each paired with concrete file-grounded evidence.
"""

# pylint: disable=duplicate-code  # verb-registration boilerplate

from __future__ import annotations

import argparse
from pathlib import Path

from seer.cli._output import emit_result
from seer.lookup.classify import classify
from seer.lookup.render import render_classify_markdown


def cmd_classify(args: argparse.Namespace) -> int:
    """Handle the ``classify`` verb."""
    path = Path(args.path).resolve()
    data = classify(path)
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result({"ok": True, "data": data}, json_mode=True)
    else:
        emit_result(render_classify_markdown(data), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    """Register the ``classify`` sub-command on *sub*."""
    p = sub.add_parser(
        "classify",
        help="Classify a repo by project-type tags (cli / library / dockerized / …).",
    )
    p.add_argument("path", nargs="?", default=".", help="Path to the repo (default: cwd).")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_classify)
```

Modify `seer/cli/__init__.py`. Locate the existing import block around line 60 (`from seer.cli._commands import explain as _explain_cmd` …) and the registration block right after it. Add `classify` to both:

```python
    from seer.cli._commands import classify as _classify_cmd
    from seer.cli._commands import explain as _explain_cmd
    from seer.cli._commands import learn as _learn_cmd
    from seer.cli._commands import whoami as _whoami_cmd

    _learn_cmd.register(sub)
    _explain_cmd.register(sub)
    _whoami_cmd.register(sub)
    _classify_cmd.register(sub)
```

- [ ] **Step 6: Sanity-check the CLI wiring**

Run: `uv run python -m seer classify --help`

Expected: argparse help output containing `usage: seer classify [-h] [--json] [path]` and the description line.

Run: `uv run python -m seer classify /tmp 2>&1 | head -5`

Expected: empty markdown body (because the renderer is still a stub) and exit code 0. (The renderer returning `""` is fine for this task; Task 7 fills it in.)

- [ ] **Step 7: Run the full suite — no regressions**

Run: `uv run pytest -n auto`

Expected: 192 prior + 1 new = **193 passed**.

- [ ] **Step 8: Commit**

```bash
git add seer/lookup/ seer/cli/_commands/classify.py seer/cli/__init__.py tests/test_classify.py
git commit -m "feat: scaffold seer.lookup package + register classify verb

Empty rule set; emits {tags: []} for any path. Foundation for Tasks 2-6.

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Path validation

**Files:**
- Modify: `tests/test_classify.py` (append tests)

The engine already raises the right errors (Task 1, Step 3); this task pins them with tests so future refactors can't drop the contract.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classify.py`:

```python
import pytest

from seer.cli._errors import EXIT_USER_ERROR, SeerError


def test_classify_path_not_found_raises_seer_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SeerError) as exc:
        classify(missing)
    assert exc.value.code == EXIT_USER_ERROR
    assert "path not found" in exc.value.message


def test_classify_path_is_file_raises_seer_error(tmp_path: Path) -> None:
    f = tmp_path / "regular_file.txt"
    f.write_text("hi")
    with pytest.raises(SeerError) as exc:
        classify(f)
    assert exc.value.code == EXIT_USER_ERROR
    assert "directory" in exc.value.message
```

- [ ] **Step 2: Run the new tests — they should pass without code changes**

Run: `uv run pytest tests/test_classify.py -v`

Expected: 3 PASS (the empty-repo one + both new). The implementation was put in place in Task 1 Step 3.

- [ ] **Step 3: Commit**

```bash
git add tests/test_classify.py
git commit -m "test: pin path-validation contract for classify

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Manifest-detection tags (`python`, `node`, `bash`)

**Files:**
- Modify: `seer/lookup/classify.py` (extend `_build_context`, add 3 rules)
- Modify: `tests/test_classify.py` (append 3 tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classify.py`:

```python
def test_classify_python_manifest_fires_python_tag(tmp_path: Path) -> None:
    repo = tmp_path / "py"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "py"\nversion = "0.1.0"\n')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "python" in tag_names
    py_tag = next(t for t in result["tags"] if t["name"] == "python")
    assert py_tag["evidence"] == "pyproject.toml present"
    assert result["manifest"] == "pyproject.toml"
    assert result["language"] == "python"


def test_classify_node_manifest_fires_node_tag(tmp_path: Path) -> None:
    repo = tmp_path / "node"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "node-app", "version": "0.1.0"}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "node" in tag_names
    assert "python" not in tag_names
    node_tag = next(t for t in result["tags"] if t["name"] == "node")
    assert node_tag["evidence"] == "package.json present"
    assert result["manifest"] == "package.json"
    assert result["language"] == "node"


def test_classify_bash_only_fires_bash_tag(tmp_path: Path) -> None:
    repo = tmp_path / "bash"
    repo.mkdir()
    scripts = repo / "scripts"
    scripts.mkdir()
    (scripts / "foo.sh").write_text("#!/bin/bash\n")
    (scripts / "bar.sh").write_text("#!/bin/bash\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "bash" in tag_names
    assert "python" not in tag_names
    assert "node" not in tag_names
    bash_tag = next(t for t in result["tags"] if t["name"] == "bash")
    assert "scripts/" in bash_tag["evidence"]
    assert "2 .sh file" in bash_tag["evidence"]


def test_classify_polyglot_both_python_and_node_tags(tmp_path: Path) -> None:
    """Both manifests present → both tags fire; scalar language defaults to python."""
    repo = tmp_path / "poly"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "poly"\n')
    (repo / "package.json").write_text('{"name": "poly"}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "python" in tag_names
    assert "node" in tag_names
    assert result["language"] == "python"
    assert result["manifest"] == "pyproject.toml"
```

- [ ] **Step 2: Run them — confirm they fail**

Run: `uv run pytest tests/test_classify.py -v -k 'python_manifest or node_manifest or bash_only or polyglot'`

Expected: 4 FAIL with `"python" in tag_names` / `"node" in tag_names` / `"bash" in tag_names` assertions (tag list is currently empty).

- [ ] **Step 3: Extend `_build_context` to load both manifests + scripts**

In `seer/lookup/classify.py`, add these imports near the top (after the existing `from seer.cli._errors`):

```python
import json
import tomllib

from seer.repo.errors import malformed_pyproject
```

Replace `_build_context` with:

```python
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
```

Add the three rule functions and register them. Append to `seer/lookup/classify.py` (above `_RULES`):

```python
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
    return {
        "name": "bash",
        "evidence": f"scripts/ contains {n} .sh file{'s' if n != 1 else ''}; no Python/Node manifest",
    }
```

Replace the empty `_RULES = []` with:

```python
_RULES = [_rule_python, _rule_node, _rule_bash]
```

- [ ] **Step 4: Run the tests — confirm they pass**

Run: `uv run pytest tests/test_classify.py -v`

Expected: all 7 tests PASS.

- [ ] **Step 5: Confirm no regressions in the full suite**

Run: `uv run pytest -n auto`

Expected: 192 prior + 7 new = **199 passed**.

- [ ] **Step 6: Commit**

```bash
git add seer/lookup/classify.py tests/test_classify.py
git commit -m "feat(classify): add python / node / bash manifest-detection tags

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Manifest-derived tags (`cli`, `library`)

**Files:**
- Modify: `seer/lookup/classify.py` (add 2 rules + extend `_Context` for entry-point capture)
- Modify: `tests/test_classify.py` (append 4 tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classify.py`:

```python
def test_classify_python_cli_with_entry_point(tmp_path: Path) -> None:
    repo = tmp_path / "tool"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "tool"\nversion = "0.1.0"\n'
        '[project.scripts]\ntool = "tool.cli:main"\n'
    )
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "cli" in tag_names
    cli_tag = next(t for t in result["tags"] if t["name"] == "cli")
    assert "tool" in cli_tag["evidence"]
    assert "tool.cli:main" in cli_tag["evidence"]


def test_classify_node_cli_with_bin(tmp_path: Path) -> None:
    repo = tmp_path / "ncli"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "ncli", "bin": {"ncli": "./cli.js"}}')
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "cli" in tag_names
    cli_tag = next(t for t in result["tags"] if t["name"] == "cli")
    assert "ncli" in cli_tag["evidence"]


def test_classify_python_library_fires_library_tag(tmp_path: Path) -> None:
    repo = tmp_path / "lib"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "lib"\n')
    pkg = repo / "lib"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "library" in tag_names
    lib_tag = next(t for t in result["tags"] if t["name"] == "library")
    assert "lib/__init__.py" in lib_tag["evidence"]


def test_classify_library_src_layout(tmp_path: Path) -> None:
    repo = tmp_path / "srclib"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "srclib"\n')
    pkg = repo / "src" / "srclib"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "library" in tag_names
    lib_tag = next(t for t in result["tags"] if t["name"] == "library")
    assert "src/srclib/__init__.py" in lib_tag["evidence"]


def test_classify_library_without_scripts_no_cli_tag(tmp_path: Path) -> None:
    repo = tmp_path / "libnocli"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "libnocli"\n')
    pkg = repo / "libnocli"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "library" in tag_names
    assert "cli" not in tag_names
```

- [ ] **Step 2: Confirm they fail**

Run: `uv run pytest tests/test_classify.py -v -k 'cli or library'`

Expected: 5 FAIL.

- [ ] **Step 3: Implement the two rules**

In `seer/lookup/classify.py`, append (above `_RULES`):

```python
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
```

Extend `_RULES`:

```python
_RULES = [_rule_python, _rule_node, _rule_bash, _rule_cli, _rule_library]
```

- [ ] **Step 4: Run the tests — confirm they pass**

Run: `uv run pytest tests/test_classify.py -v`

Expected: 12 PASS.

- [ ] **Step 5: Full suite green**

Run: `uv run pytest -n auto`

Expected: **204 passed** (192 prior + 12 new).

- [ ] **Step 6: Commit**

```bash
git add seer/lookup/classify.py tests/test_classify.py
git commit -m "feat(classify): add cli + library manifest-derived tags

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: File-marker tags (`dockerized`, `agentculture-sibling`)

**Files:**
- Modify: `seer/lookup/classify.py` (extend `_build_context` + 2 rules)
- Modify: `tests/test_classify.py` (append 3 tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classify.py`:

```python
def test_classify_dockerized_from_dockerfile(tmp_path: Path) -> None:
    repo = tmp_path / "docked"
    repo.mkdir()
    (repo / "Dockerfile").write_text("FROM python:3.12\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "dockerized" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "dockerized")
    assert tag["evidence"] == "Dockerfile present"


def test_classify_dockerized_from_compose_only(tmp_path: Path) -> None:
    repo = tmp_path / "composed"
    repo.mkdir()
    (repo / "docker-compose.yml").write_text("version: '3'\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "dockerized" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "dockerized")
    assert "docker-compose.yml" in tag["evidence"]


def test_classify_agentculture_sibling(tmp_path: Path) -> None:
    repo = tmp_path / "sib"
    repo.mkdir()
    (repo / "culture.yaml").write_text("agents:\n  - suffix: sib\n")
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "agentculture-sibling" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "agentculture-sibling")
    assert tag["evidence"] == "culture.yaml present"
```

- [ ] **Step 2: Confirm they fail**

Run: `uv run pytest tests/test_classify.py -v -k 'docker or agentculture'`

Expected: 3 FAIL.

- [ ] **Step 3: Extend `_build_context` and add rules**

In `_build_context`, before the final `return ctx`, append:

```python
    if (path / "Dockerfile").exists():
        ctx.has_dockerfile = True
    for compose in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        if (path / compose).exists():
            ctx.has_compose = True
            ctx.compose_filename = compose
            break

    if (path / "culture.yaml").exists():
        ctx.has_culture_yaml = True
```

Append the rules above `_RULES`:

```python
def _rule_dockerized(ctx: _Context) -> dict[str, str] | None:
    if ctx.has_dockerfile:
        return {"name": "dockerized", "evidence": "Dockerfile present"}
    if ctx.has_compose and ctx.compose_filename:
        return {"name": "dockerized", "evidence": f"{ctx.compose_filename} present"}
    return None


def _rule_agentculture_sibling(ctx: _Context) -> dict[str, str] | None:
    if ctx.has_culture_yaml:
        return {"name": "agentculture-sibling", "evidence": "culture.yaml present"}
    return None
```

Extend `_RULES`:

```python
_RULES = [
    _rule_python,
    _rule_node,
    _rule_bash,
    _rule_cli,
    _rule_library,
    _rule_dockerized,
    _rule_agentculture_sibling,
]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_classify.py -v`

Expected: 15 PASS.

- [ ] **Step 5: Full suite green**

Run: `uv run pytest -n auto`

Expected: **207 passed**.

- [ ] **Step 6: Commit**

```bash
git add seer/lookup/classify.py tests/test_classify.py
git commit -m "feat(classify): add dockerized + agentculture-sibling file-marker tags

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Workflow-content tags (`tested`, `packaged-pypi`)

**Files:**
- Modify: `seer/lookup/classify.py` (extend `_build_context` + 2 rules)
- Modify: `tests/test_classify.py` (append 4 tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classify.py`:

```python
def test_classify_tested_python_pytest_in_dev(tmp_path: Path) -> None:
    repo = tmp_path / "tpy"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "tpy"\n'
        '[dependency-groups]\ndev = ["pytest>=8.0"]\n'
    )
    (repo / "tests").mkdir()
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "tested" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "tested")
    assert "tests/" in tag["evidence"]
    assert "pytest" in tag["evidence"]


def test_classify_not_tested_when_pytest_missing(tmp_path: Path) -> None:
    repo = tmp_path / "tno"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "tno"\n')
    (repo / "tests").mkdir()  # dir exists but pytest not in deps
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "tested" not in tag_names


def test_classify_tested_node_with_test_script(tmp_path: Path) -> None:
    repo = tmp_path / "tnode"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "tnode", "scripts": {"test": "jest"}}')
    (repo / "tests").mkdir()
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "tested" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "tested")
    assert "test" in tag["evidence"]


def test_classify_packaged_pypi_from_workflow(tmp_path: Path) -> None:
    repo = tmp_path / "pkg"
    repo.mkdir()
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "publish.yml").write_text(
        "on: push\njobs:\n  pub:\n    steps:\n      - uses: pypa/gh-action-pypi-publish@v1\n"
    )
    result = classify(repo)
    tag_names = [t["name"] for t in result["tags"]]
    assert "packaged-pypi" in tag_names
    tag = next(t for t in result["tags"] if t["name"] == "packaged-pypi")
    assert "publish.yml" in tag["evidence"]
```

- [ ] **Step 2: Confirm they fail**

Run: `uv run pytest tests/test_classify.py -v -k 'tested or packaged'`

Expected: 4 FAIL.

- [ ] **Step 3: Extend `_build_context`**

In `_build_context`, before the final `return ctx`, append:

```python
    if (path / "tests").is_dir():
        ctx.has_tests_dir = True

    workflows_dir = path / ".github" / "workflows"
    if workflows_dir.is_dir():
        ctx.workflow_files = sorted(
            p for p in workflows_dir.iterdir() if p.suffix in (".yml", ".yaml")
        )
```

- [ ] **Step 4: Add the rules**

Append above `_RULES`:

```python
def _rule_tested(ctx: _Context) -> dict[str, str] | None:
    if not ctx.has_tests_dir:
        return None
    # Python path: pytest in [dependency-groups] dev
    if ctx.pyproject is not None:
        dev_deps = (ctx.pyproject.get("dependency-groups", {}) or {}).get("dev", []) or []
        if any(d.split(">=")[0].split("==")[0].split("~=")[0].strip() == "pytest" for d in dev_deps):
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
        except OSError:
            continue
        if any(needle in text for needle in needles):
            return {
                "name": "packaged-pypi",
                "evidence": f".github/workflows/{wf.name} uploads to pypi.org",
            }
    return None
```

Extend `_RULES`:

```python
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
```

(Order matches the spec's tag-display order.)

- [ ] **Step 5: Add the evidence-non-empty invariant test**

Append to `tests/test_classify.py`:

```python
def test_classify_every_returned_tag_has_evidence(tmp_path: Path) -> None:
    """No rule may emit an empty evidence string — contract invariant."""
    repo = tmp_path / "full"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "full"\n[project.scripts]\nfull = "full.cli:main"\n'
        '[dependency-groups]\ndev = ["pytest"]\n'
    )
    pkg = repo / "full"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (repo / "Dockerfile").write_text("FROM python:3.12\n")
    (repo / "tests").mkdir()
    (repo / "culture.yaml").write_text("agents:\n  - suffix: full\n")
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "publish.yml").write_text("uses: pypa/gh-action-pypi-publish@v1\n")
    result = classify(repo)
    assert result["tags"], "expected at least one tag"
    for tag in result["tags"]:
        assert isinstance(tag.get("name"), str) and tag["name"], f"empty name in {tag}"
        assert isinstance(tag.get("evidence"), str) and tag["evidence"], f"empty evidence in {tag}"
```

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/test_classify.py -v`

Expected: 20 PASS.

Run: `uv run pytest -n auto`

Expected: **212 passed**.

- [ ] **Step 7: Commit**

```bash
git add seer/lookup/classify.py tests/test_classify.py
git commit -m "feat(classify): add tested + packaged-pypi workflow-content tags

Plus an evidence-non-empty invariant test that pins the contract across
every rule.

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Markdown renderer

**Files:**
- Modify: `seer/lookup/render.py` (real implementation)
- Create: `tests/test_classify_render.py`

- [ ] **Step 1: Write the failing renderer tests**

Create `tests/test_classify_render.py`:

```python
"""Tests for seer.lookup.render."""

from __future__ import annotations

from seer.lookup.render import render_classify_markdown


def _fixture() -> dict:
    return {
        "path": "/home/user/projects/demo",
        "manifest": "pyproject.toml",
        "language": "python",
        "tags": [
            {"name": "python", "evidence": "pyproject.toml present"},
            {"name": "cli", "evidence": '[project.scripts] defines demo = "demo.cli:main"'},
            {"name": "library", "evidence": "`demo/__init__.py` present"},
            {"name": "tested", "evidence": "tests/ exists; pytest in dependency-groups.dev"},
            {"name": "agentculture-sibling", "evidence": "culture.yaml present"},
        ],
    }


def test_render_includes_path_header() -> None:
    md = render_classify_markdown(_fixture())
    assert md.startswith("# /home/user/projects/demo\n")


def test_render_includes_manifest_and_language_line() -> None:
    md = render_classify_markdown(_fixture())
    assert "- **Manifest:** pyproject.toml (python)" in md


def test_render_includes_tag_summary_line() -> None:
    md = render_classify_markdown(_fixture())
    assert "- **Tags:** python, cli, library, tested, agentculture-sibling" in md


def test_render_inserts_section_break_before_tags_heading() -> None:
    md = render_classify_markdown(_fixture())
    idx = md.index("## Tags")
    prefix = md[:idx]
    assert prefix.rstrip().endswith("---"), "no `---` separator before `## Tags`"


def test_render_tags_table_has_two_columns_per_row() -> None:
    md = render_classify_markdown(_fixture())
    # Find the Tags table body (lines between the column-separator row and the next
    # blank line or EOF). Each body row must be `| <tag> | <evidence> |`.
    lines = md.splitlines()
    in_table = False
    for line in lines:
        if line.startswith("|---|"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            # 3 pipes = 2 columns
            assert line.count("|") == 3, f"row not 2-col shape: {line!r}"


def test_render_empty_tags_still_renders_header() -> None:
    empty = {"path": "/x", "manifest": None, "language": "unknown", "tags": []}
    md = render_classify_markdown(empty)
    assert "# /x\n" in md
    assert "**Manifest:** none (unknown)" in md
    assert "**Tags:** _(none)_" in md
    # No Tags table when list is empty.
    assert "## Tags" not in md


def test_render_no_manifest_renders_none() -> None:
    no_mf = {
        "path": "/y",
        "manifest": None,
        "language": "unknown",
        "tags": [{"name": "bash", "evidence": "scripts/ contains 1 .sh file"}],
    }
    md = render_classify_markdown(no_mf)
    assert "**Manifest:** none (unknown)" in md
```

- [ ] **Step 2: Confirm they fail**

Run: `uv run pytest tests/test_classify_render.py -v`

Expected: 7 FAIL (renderer returns `""`).

- [ ] **Step 3: Implement `render_classify_markdown`**

Replace the body of `seer/lookup/render.py` with:

```python
"""Markdown emitter for seer.lookup.classify."""

from __future__ import annotations

from typing import Any


def _section_break(lines: list[str]) -> None:
    """Emit a blank line + horizontal rule before a top-level section heading."""
    lines.append("")
    lines.append("---")


def render_classify_markdown(data: dict[str, Any]) -> str:
    """Render a classify() dict as a markdown report."""
    lines: list[str] = []
    lines.append(f"# {data.get('path', '(unknown)')}")

    manifest = data.get("manifest")
    language = data.get("language") or "unknown"
    if manifest:
        lines.append(f"- **Manifest:** {manifest} ({language})")
    else:
        lines.append(f"- **Manifest:** none ({language})")

    tags = data.get("tags") or []
    if tags:
        names = ", ".join(t["name"] for t in tags)
        lines.append(f"- **Tags:** {names}")
    else:
        lines.append("- **Tags:** _(none)_")

    if tags:
        _section_break(lines)
        lines.append("## Tags")
        lines.append("| Tag | Evidence |")
        lines.append("|---|---|")
        for t in tags:
            lines.append(f"| `{t['name']}` | {t['evidence']} |")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the renderer tests**

Run: `uv run pytest tests/test_classify_render.py -v`

Expected: 7 PASS.

- [ ] **Step 5: Manual sanity check on a real repo**

Run: `uv run python -m seer classify /home/spark/git/agtag`

Expected: markdown output with:
- `# /home/spark/git/agtag`
- `- **Manifest:** pyproject.toml (python)`
- `- **Tags:** python, cli, library, tested, packaged-pypi, agentculture-sibling`
- `---` separator before `## Tags`
- Table rows for each tag with concrete evidence (e.g. `[project.scripts] defines agtag = "agtag.cli:main"`).

Run: `uv run python -m seer classify /home/spark/git/agtag --json | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['data']['tags']))"`

Expected: `6` (or more if `bash` also fires due to agtag's scripts/ contents — adjust expectation by inspecting the output if so).

- [ ] **Step 6: Full suite green**

Run: `uv run pytest -n auto`

Expected: **219 passed** (212 + 7 renderer tests).

- [ ] **Step 7: Lint**

Run: `uv run flake8 --config=.flake8 seer/ tests/ && uv run black --check seer/ tests/ && uv run isort --check seer/ tests/`

Expected: all clean. If black or isort report changes, run them without `--check` and re-stage.

- [ ] **Step 8: Commit**

```bash
git add seer/lookup/render.py tests/test_classify_render.py
git commit -m "feat(classify): render classify result as markdown with section break

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: SKILL.md + shell wrapper + skill-sources row + dogfood

**Files:**
- Create: `.claude/skills/code-lookup/SKILL.md`
- Create: `.claude/skills/code-lookup/scripts/classify.sh` (chmod +x)
- Modify: `docs/skill-sources.md` (append row)

- [ ] **Step 1: Create the shell wrapper**

Create `.claude/skills/code-lookup/scripts/classify.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
exec uv run --directory "$PROJECT_ROOT" python -m seer classify "$@"
```

Make it executable:

```bash
chmod +x .claude/skills/code-lookup/scripts/classify.sh
```

- [ ] **Step 2: Create the SKILL.md**

Create `.claude/skills/code-lookup/SKILL.md`:

```markdown
---
name: code-lookup
description: >
  Classify what kind of project a repo is — in one tool call, with
  deterministic tags + per-tag evidence. `scripts/classify.sh [<path>]`
  returns: manifest type + language, and a tag list (`python`, `node`,
  `bash`, `cli`, `library`, `dockerized`, `tested`, `packaged-pypi`,
  `agentculture-sibling`), each with the concrete evidence that fired
  it (e.g. "Dockerfile present", "[project.scripts] defines `foo = …`",
  ".github/workflows/publish.yml uploads to pypi.org"). Markdown by
  default; `--json` for machine-readable. Prefer this over manually
  reading pyproject.toml + Dockerfile + workflows + culture.yaml
  separately — one call collapses ~5–7 Read/Bash steps into a
  structured tag list with citations. When NOT to use: if you only
  need one specific fact (e.g. "is there a Dockerfile"), Read/glob is
  cheaper than this verb.
---

# code-lookup

Sibling of `repo-map`. While `repo-map` answers *"tell me about this
repo"* (profile + connections + workspace graph), `code-lookup` is the
slot for *"what shape is this project? where is X? what's in this
file?"* questions. v1 ships `classify` only; future verbs (`outline`,
`find-symbol`) will land here.

## When to use

| Mode | Invocation |
| --- | --- |
| Classify a project by type tags | `scripts/classify.sh [<path>]` |

## Output

`scripts/classify.sh /path/to/repo` returns one markdown report with:

- a header line naming the path
- `**Manifest:**` line with the canonical manifest + language
- `**Tags:**` summary line
- a `## Tags` table where each row is `| <tag> | <evidence> |`

Pass `--json` for the machine-readable envelope (`{ok, data}` shape,
same as `repo-map`).

## Composition with repo-map

For "tell me about this repo from scratch":

1. `classify <path>` — what *kind* of repo is this (CLI? service?
   dockerized?). Cheap.
2. `bash .claude/skills/repo-map/scripts/profile.sh <path>` — the
   structured profile (deps, package tree, vendored skills, recent
   changelog).

One call each, no re-grepping.

## Engine

`seer/lookup/` — `python -m seer classify <path>`. The shell wrapper is
a one-liner; the agent-facing contract is the verb and its flags.
```

- [ ] **Step 3: Append the skill-sources.md row**

Modify `docs/skill-sources.md`. After the existing `| `repo-map` | _internal implementation_ — seer-cli origin | …` row, add:

```markdown
| `code-lookup` | _internal implementation_ — seer-cli origin | 2026-05-16 | **Runtime:** thin shell wrapper under `.claude/skills/code-lookup/scripts/classify.sh` that invokes `uv run --directory <repo-root> python -m seer classify`. Engine lives in `seer/lookup/` in this repo. **Divergence:** N/A — original to seer-cli, sibling of `repo-map`. If/when promoted upstream, this row flips to a `Re-vendor from steward` pointer. |
```

- [ ] **Step 4: End-to-end dogfood on agtag**

Run: `bash .claude/skills/code-lookup/scripts/classify.sh /home/spark/git/agtag`

Expected output (modulo agtag-specific evidence strings):
- `# /home/spark/git/agtag`
- `**Manifest:** pyproject.toml (python)`
- `**Tags:**` line including `python, cli, library, tested, packaged-pypi, agentculture-sibling` (and possibly `bash` if `agtag/scripts/` has `.sh` files — check; if so, `bash` should be ABSENT because pyproject is present; this is also a test of Task 3's `bash` rule).
- `---` separator
- A `## Tags` table with one row per tag.

Run: `bash .claude/skills/code-lookup/scripts/classify.sh /home/spark/git/seer-cli`

Expected: similar tag set; this is the dogfood pass.

- [ ] **Step 5: Markdownlint the new SKILL.md**

Run: `markdownlint-cli2 ".claude/skills/code-lookup/SKILL.md"` (or `npx markdownlint-cli2@0.21.0 …` to match CI).

Expected: 0 errors. If MD022/MD032 fire, add the missing blank lines around lists/headings.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/code-lookup/ docs/skill-sources.md
git commit -m "skill: add code-lookup with classify wrapper + provenance row

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Version bump + CHANGELOG + push + open PR

**Files:**
- Modify: `pyproject.toml` (version)
- Modify: `CHANGELOG.md` (prepend entry)

- [ ] **Step 1: Bump the version**

Run the vendored version-bump skill so `pyproject.toml` + `CHANGELOG.md` move together:

```bash
echo '{"added":["seer classify verb: deterministic project-type tags with per-tag evidence, in one tool call. Tags: python / node / bash / cli / library / dockerized / tested / packaged-pypi / agentculture-sibling. Markdown by default; --json for structured. Spec: docs/superpowers/specs/2026-05-16-seer-classify-design.md","code-lookup skill: companion to repo-map, houses the classify wrapper + SKILL.md (frontmatter enumerates output fields + token-math + when-NOT-to-use, per the PR #13 / Qodo lesson)"]}' \
  | python3 .claude/skills/version-bump/scripts/bump.py patch
```

Expected: `Updated CHANGELOG.md with [0.4.2]` and `0.4.1 -> 0.4.2`.

- [ ] **Step 2: Final lint + test gate**

Run: `uv run flake8 --config=.flake8 seer/ tests/ && uv run black --check seer/ tests/ && uv run isort --check seer/ tests/`

Expected: clean.

Run: `uv run pytest -n auto`

Expected: **219 passed** (or more, including the new render tests).

Run: `markdownlint-cli2 "CHANGELOG.md" ".claude/skills/code-lookup/SKILL.md"`

Expected: 0 errors.

- [ ] **Step 3: Commit the version bump**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore(release): v0.4.2 — seer classify + code-lookup skill

- seer (Claude)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 4: Push the branch**

```bash
git push -u origin feat/seer-classify
```

Expected: branch created on origin, no push errors. The PR-creation URL is printed.

- [ ] **Step 5: Open the PR**

```bash
gh pr create --repo agentculture/seer-cli --base main --head feat/seer-classify \
  --title "feat: seer classify verb + code-lookup skill (v0.4.2)" \
  --body "$(cat <<'EOF'
## Summary

- New `seer classify [path]` verb returning a deterministic project-type tag list with per-tag evidence, in one tool call (replaces ~5-7 Read/Bash steps to derive the same answer manually).
- New `.claude/skills/code-lookup/` skill — sibling of `repo-map`, frontmatter enumerates output fields + token-math + when-NOT-to-use per the PR #13 / Qodo lesson.
- Closes the Slice-1 portion of #11. AST-aware reshapes of `grep` + `recent` tracked in #14.

## Test plan

- [ ] `uv run pytest -n auto` (full suite green, was 192 → expected 219+).
- [ ] `bash .claude/skills/code-lookup/scripts/classify.sh /home/spark/git/agtag` — tag set sane.
- [ ] `seer classify . --json | jq '.data.tags | all(has("name") and has("evidence"))'` — `true`.
- [ ] SonarCloud Quality Gate green, 0 OPEN issues.
- [ ] markdownlint clean.

## Spec / plan

- Spec: `docs/superpowers/specs/2026-05-16-seer-classify-design.md` (committed in `d597904`)
- Implementation plan: `docs/superpowers/plans/2026-05-16-seer-classify.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)

- seer (Claude)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 6: Await CI gate**

Run: `bash .claude/skills/cicd/scripts/workflow.sh await <PR_NUMBER>`

Expected: all checks green; SonarCloud Quality Gate OK with 0 OPEN issues; no unresolved threads.

If lint / Sonar / Qodo flag anything, triage per the `cicd` skill's FIX/PUSHBACK rules and push fix-ups (do not amend; create new commits).

---

## Out of scope for this plan (deferred)

- Heuristic tags (`service`, `web-app`, `monorepo`) — explicit in spec.
- AST-aware reshape of `grep` / `recent` — issue #14.
- `outline` / `find-symbol` — future slices, separate specs.
- Language coverage beyond Python / Node / Bash — when there's demand.
