"""Single-repo profiler.

Two depths:

  * shallow (default) — mechanical facts from pyproject.toml, on-disk layout,
    vendored-skill list, CITATION.md, CHANGELOG.md, CLAUDE.md status section.
  * deep — shallow + README intro, CLAUDE.md design sections, last 10
    commit subjects (added in :func:`profile_deep`, separate task).

Missing optional sources degrade silently to empty fields.
"""

from __future__ import annotations

import ast
import re
import subprocess  # noqa: S404  # nosec B404
import tomllib
from pathlib import Path

import yaml

from seer.repo.detect import resolve_name
from seer.repo.manifest import read_pyproject

_WORKFLOW_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_REMOTE_RE = re.compile(r"^(?:git@|https?://)([^:/]+)[:/](.+?)(?:\.git)?/?$")


def profile_shallow(path: Path) -> dict[str, object]:
    """Return a shallow profile dict for the repo at ``path``.

    Reads from multiple optional sources (pyproject.toml, CLAUDE.md,
    CHANGELOG.md, CITATION.md, .claude/skills/, culture.yaml) and degrades
    silently when any source is missing.
    """
    has_pyproject = (path / "pyproject.toml").exists()
    if has_pyproject:
        m = read_pyproject(path)
        language = "python"
        manifest: str | None = "pyproject.toml"
        try:
            raw_pyproject: dict | None = tomllib.loads(
                (path / "pyproject.toml").read_text(encoding="utf-8")
            )
        except (tomllib.TOMLDecodeError, OSError):
            raw_pyproject = None
    else:
        m = {
            "name": resolve_name(path),
            "version": "",
            "entry_points": {},
            "deps_runtime": [],
            "deps_dev": [],
        }
        language = "unknown"
        manifest = None
        raw_pyproject = None
    package_tree = _package_tree(path)
    profile: dict[str, object] = {
        "path": str(path),
        "name": m["name"],
        "version": m["version"],
        "language": language,
        "manifest": manifest,
        "entry_points": m["entry_points"],
        "deps_runtime": m["deps_runtime"],
        "deps_dev": m["deps_dev"],
        "package_layout": _list_packages(path),
        "package_tree": package_tree,
        "build_test": _build_test(raw_pyproject),
        "ci_workflows": _ci_workflows(path),
        "publish_target": _publish_target(path),
        "git_remote": _git_remote(path),
        "module_summaries": _module_docs(path, package_tree),
        "vendored_skills": _list_vendored_skills(path),
        "citations": _read_citations(path),
        "changelog_recent": _read_changelog(path, n=3),
        "claude_md_status": _read_claude_md_section(path, "## Project Status"),
        "extra": {},
    }
    nick = _read_culture_nick(path)
    if nick:
        profile["extra"]["culture_nick"] = nick  # type: ignore[index]
    return profile


_PKG_EXCLUDE = {"tests", "docs", "scripts", "__pycache__"}
_INIT_PY = "__init__.py"


def _is_candidate_pkg_dir(child: Path) -> bool:
    """True if *child* is a non-hidden, non-excluded directory worth scanning."""
    return child.is_dir() and not child.name.startswith(".") and child.name not in _PKG_EXCLUDE


def _list_packages(path: Path) -> list[str]:
    """Return one-level Python packages at the repo root or under ``src/``."""
    out: list[str] = []
    for child in sorted(path.iterdir()):
        if not _is_candidate_pkg_dir(child):
            continue
        if (child / _INIT_PY).exists():
            out.append(child.name + "/")
    src = path / "src"
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if not _is_candidate_pkg_dir(child):
                continue
            if (child / _INIT_PY).exists():
                out.append(f"src/{child.name}/")
    return out


def _package_node(pkg_dir: Path, *, remaining_depth: int) -> dict[str, object]:
    """Build one tree node for *pkg_dir*; recurse into subpackages until depth exhausted."""
    modules: list[str] = []
    subpackages: list[dict[str, object]] = []
    for child in sorted(pkg_dir.iterdir()):
        if child.name.startswith(".") or child.name in _PKG_EXCLUDE:
            continue
        if child.is_file() and child.suffix == ".py":
            modules.append(child.name)
            continue
        if child.is_dir() and (child / _INIT_PY).exists() and remaining_depth > 0:
            subpackages.append(_package_node(child, remaining_depth=remaining_depth - 1))
    return {"name": pkg_dir.name, "modules": modules, "subpackages": subpackages}


def _package_tree(path: Path, *, max_depth: int = 2) -> list[dict[str, object]]:
    """Return one node per top-level package with up to ``max_depth`` levels of subpackages.

    Walks the same roots as :func:`_list_packages` (repo root + ``src/``) and
    honors the same exclude set, so callers that consume both the flat
    ``package_layout`` and the nested ``package_tree`` see consistent contents.

    ``max_depth=2`` means: top-level package (e.g. ``demo/``) plus up to two
    nested levels of subpackages (e.g. ``demo/cli/`` and ``demo/cli/_commands/``).
    """
    out: list[dict[str, object]] = []
    for child in sorted(path.iterdir()):
        if not _is_candidate_pkg_dir(child):
            continue
        if (child / _INIT_PY).exists():
            out.append(_package_node(child, remaining_depth=max_depth))
    src = path / "src"
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if not _is_candidate_pkg_dir(child):
                continue
            if (child / _INIT_PY).exists():
                out.append(_package_node(child, remaining_depth=max_depth))
    return out


def _list_vendored_skills(path: Path) -> list[dict[str, str]]:
    """Return ``.claude/skills/*`` entries, augmented with provenance when present."""
    skills_dir = path / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    skills: list[dict[str, str]] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if skill_dir.is_dir():
            skills.append(
                {
                    "name": skill_dir.name,
                    "path": f".claude/skills/{skill_dir.name}/",
                }
            )
    provenance = _read_skill_sources(path)
    for skill in skills:
        if skill["name"] in provenance:
            skill.update(provenance[skill["name"]])
    return skills


def _unwrap_backticks(val: str) -> str:
    """Strip a *fully balanced* ```…``` pair from *val* and trim whitespace.

    Cells with internal ```…``` spans (e.g.
    ```agentculture/steward` (`.claude/skills/cicd/`)``)
    are left intact so the rendered markdown stays valid.
    """
    v = val.strip()
    if len(v) >= 2 and v.startswith("`") and v.endswith("`"):
        return v[1:-1].strip()
    return v


def _read_skill_sources(path: Path) -> dict[str, dict[str, str]]:
    """Parse ``docs/skill-sources.md`` table rows into ``{name: {source, version}}``."""
    f = path / "docs" / "skill-sources.md"
    if not f.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        parts = [p.strip() for p in s.strip("|").split("|")]
        if len(parts) >= 2 and parts[0] and parts[1] and parts[0] not in {"name", "Skill"}:
            key = _unwrap_backticks(parts[0])
            if key.lower() in {"name", "skill"}:
                continue
            out[key] = {
                "source": _unwrap_backticks(parts[1]),
                "version": _unwrap_backticks(parts[2]) if len(parts) >= 3 else "",
            }
    return out


def _read_citations(path: Path) -> list[dict[str, str]]:
    """Parse ``CITATION.md`` rows into ``[{local, source_repo, sha}]``."""
    f = path / "CITATION.md"
    if not f.exists():
        return []
    out: list[dict[str, str]] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or "---" in s:
            continue
        parts = [p.strip() for p in s.strip("|").split("|")]
        if len(parts) >= 3 and parts[0] and parts[1] and parts[2]:
            first = _unwrap_backticks(parts[0]).lower()
            if first.startswith("local") or first in {"path", "file"}:
                continue
            out.append(
                {
                    "local": _unwrap_backticks(parts[0]),
                    "source_repo": _unwrap_backticks(parts[1]),
                    "sha": _unwrap_backticks(parts[2]),
                }
            )
    return out


def _is_changelog_summary_line(line: str) -> bool:
    """True when *line* is the first body line that should become an entry summary."""
    body = line.strip()
    if not body:
        return False
    return not body.startswith("#")


def _first_changelog_summary(body_lines: list[str]) -> str:
    """Return the first viable summary line from a slice of body lines, else ``""``."""
    for line in body_lines:
        if _is_changelog_summary_line(line):
            return line.strip().lstrip("-").strip()
    return ""


def _read_changelog(path: Path, *, n: int) -> list[dict[str, str]]:
    """Return up to ``n`` recent entries from ``CHANGELOG.md`` (Keep-a-Changelog).

    Two-pass: collect heading indices first, then extract one summary line
    per heading from the body slice between it and the next heading. This
    keeps the per-function cognitive complexity small.
    """
    f = path / "CHANGELOG.md"
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8").splitlines()
    heading_positions = [(i, line) for i, line in enumerate(lines) if line.startswith("## ")][:n]
    entries: list[dict[str, str]] = []
    for idx, (start, heading_line) in enumerate(heading_positions):
        entry = _parse_changelog_heading(heading_line)
        next_heading = (
            heading_positions[idx + 1][0] if idx + 1 < len(heading_positions) else len(lines)
        )
        entry["summary"] = _first_changelog_summary(lines[start + 1 : next_heading])
        entries.append(entry)
    return entries


def _parse_changelog_heading(line: str) -> dict[str, str]:
    """Extract version and date from a Keep-a-Changelog heading line."""
    text = line[3:].strip()
    if text.startswith("[") and "]" in text:
        version = text[1 : text.index("]")]
        rest = text[text.index("]") + 1 :].lstrip(" -")
        return {"version": version, "date": rest.strip()}
    parts = text.split()
    version = parts[0] if parts else ""
    date = parts[-1].strip("()") if len(parts) > 1 else ""
    return {"version": version, "date": date}


def _read_claude_md_section(path: Path, heading: str) -> str:
    """Return the body of a ``## Heading`` section from CLAUDE.md, stripped."""
    f = path / "CLAUDE.md"
    if not f.exists():
        return ""
    inside = False
    out: list[str] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip() == heading:
            inside = True
            continue
        if inside:
            if line.startswith("## "):
                break
            out.append(line)
    return "\n".join(out).strip()


def _read_culture_nick(path: Path) -> str:
    """Return ``agents[0].suffix`` (or ``.nick``) from ``culture.yaml`` if present."""
    f = path / "culture.yaml"
    if not f.exists():
        return ""
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ""
    agents = data.get("agents", [])
    if not agents or not isinstance(agents[0], dict):
        return ""
    return str(agents[0].get("suffix") or agents[0].get("nick") or "")


def _build_test(pyproject: dict | None) -> dict | None:
    """Extract test/coverage/python metadata from a raw pyproject dict.

    Returns a dict with some subset of ``test_command``, ``test_addopts``,
    ``coverage_fail_under``, and ``python_requires``.  Keys whose value is
    None are dropped.  Returns None when *pyproject* is None.
    """
    if pyproject is None:
        return None
    pytest_opts = pyproject.get("tool") or {}
    pytest_addopts = ((pytest_opts.get("pytest") or {}).get("ini_options") or {}).get("addopts")
    coverage_fail = ((pytest_opts.get("coverage") or {}).get("report") or {}).get("fail_under")
    python_requires = (pyproject.get("project") or {}).get("requires-python")
    result: dict = {"test_command": "pytest"}
    if pytest_addopts is not None:
        result["test_addopts"] = pytest_addopts
    if coverage_fail is not None:
        result["coverage_fail_under"] = coverage_fail
    if python_requires is not None:
        result["python_requires"] = python_requires
    return result


def _ci_workflows(path: Path) -> list[dict[str, str]]:
    """Scan ``.github/workflows/*.{yml,yaml}`` and return name + filename entries."""
    workflows_dir = path / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []
    out: list[dict[str, str]] = []
    for wf_file in sorted(workflows_dir.iterdir()):
        if wf_file.suffix not in {".yml", ".yaml"}:
            continue
        try:
            text = wf_file.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _WORKFLOW_NAME_RE.search(text)
        if m:
            raw_name = m.group(1).strip()
            # strip enclosing quotes
            if len(raw_name) >= 2 and raw_name[0] in ('"', "'") and raw_name[-1] == raw_name[0]:
                raw_name = raw_name[1:-1]
            name = raw_name
        else:
            name = ""
        out.append({"file": wf_file.name, "name": name})
    return out


def _summarize_on_block(text: str) -> str:
    """Coarse classifier for the ``on:`` block in a workflow file."""
    # Find lines after "on:" until the next top-level key
    on_block_re = re.compile(r"^on:\s*\n((?:[ \t]+.*\n?)*)", re.MULTILINE)
    m = on_block_re.search(text)
    if not m:
        # on: might be inline like "on: [push]" or just a single word
        inline_re = re.compile(r"^on:\s*(.+)$", re.MULTILINE)
        im = inline_re.search(text)
        if im:
            val = im.group(1).strip().lower()
            if "release" in val:
                return "release"
            if "workflow_dispatch" in val:
                return "workflow_dispatch"
            if "schedule" in val:
                return "schedule"
            if "pull_request" in val:
                return "pull_request"
            if "push" in val:
                return "push: branches"
        return "unknown"
    block = m.group(0)
    if "tags:" in block:
        return "push: tags"
    if "release" in block:
        return "release"
    if "workflow_dispatch" in block:
        return "workflow_dispatch"
    if "schedule" in block:
        return "schedule"
    if "pull_request" in block:
        return "pull_request"
    if "branches:" in block:
        return "push: branches"
    return "unknown"


def _publish_target(path: Path) -> dict | None:
    """Detect the first PyPI/GHCR publish workflow; return kind/workflow/trigger or None."""
    workflows_dir = path / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return None
    for wf_file in sorted(workflows_dir.iterdir()):
        if wf_file.suffix not in {".yml", ".yaml"}:
            continue
        try:
            text = wf_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if "pypa/gh-action-pypi-publish" in text or "pypi.org" in text:
            kind = "pypi"
        elif "ghcr.io" in text:
            kind = "ghcr"
        else:
            continue
        return {
            "kind": kind,
            "workflow": wf_file.name,
            "trigger": _summarize_on_block(text),
        }
    return None


def _git_remote(path: Path) -> dict | None:
    """Return parsed ``origin`` remote info from git, or None on failure."""
    try:
        result = subprocess.run(  # noqa: S603,S607  # nosec B603 B607
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    raw_url = result.stdout.strip()
    m = _REMOTE_RE.match(raw_url)
    if not m:
        return {"url": raw_url, "ref": "origin"}
    host = m.group(1)
    path_part = m.group(2)
    parts = path_part.split("/", 1)
    owner = parts[0] if len(parts) >= 1 else ""
    repo_name = parts[1] if len(parts) >= 2 else ""
    return {"host": host, "owner": owner, "repo": repo_name, "url": raw_url, "ref": "origin"}


def _collect_module_files(node: dict, base_path: Path, pkg_path: Path) -> list[tuple[str, Path]]:
    """Recursively collect (relative_path_str, abs_path) pairs from a package_tree node."""
    results: list[tuple[str, Path]] = []
    for mod in node.get("modules") or []:
        rel = pkg_path / mod
        abs_path = base_path / rel
        results.append((str(rel), abs_path))
    for sub in node.get("subpackages") or []:
        sub_pkg_path = pkg_path / sub["name"]
        results.extend(_collect_module_files(sub, base_path, sub_pkg_path))
    return results


def _module_docs(path: Path, package_tree: list[dict]) -> list[dict]:
    """Return first-docstring-line summaries for modules in the package tree."""
    out: list[dict] = []
    for node in package_tree:
        pkg_root = Path(node["name"])
        # Check if this package lives under src/
        candidate_src = path / "src" / node["name"]
        if candidate_src.is_dir():
            base_path = path / "src"
        else:
            base_path = path
        pkg_path = pkg_root
        for rel_str, abs_path in _collect_module_files(node, base_path, pkg_path):
            try:
                source = abs_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            docstring = ast.get_docstring(tree)
            if not docstring:
                continue
            first_line = docstring.strip().splitlines()[0].strip()
            if not first_line:
                continue
            out.append({"module": rel_str, "summary": first_line[:120]})
    out.sort(key=lambda x: x["module"])
    return out


_DEEP_HEADINGS = ("## Project Status", "## Architecture")
_DEEP_KEYWORDS = ("invariant", "rule", "contract")


def profile_deep(path: Path) -> dict[str, object]:
    """Shallow profile + readme intro, design-section text, recent commits."""
    p = profile_shallow(path)
    p["readme_intro"] = _read_readme_intro(path)
    p["claude_md_sections"] = _read_claude_md_design_sections(path)
    p["commits_recent"] = _read_recent_commits(path, n=10)
    return p


def _read_readme_intro(path: Path) -> str:
    """Return the first non-heading paragraph of ``README.md``."""
    f = path / "README.md"
    if not f.exists():
        return ""
    out: list[str] = []
    saw_content = False
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            if saw_content:
                break
            continue
        if not line.strip():
            if saw_content:
                break
            continue
        saw_content = True
        out.append(line.rstrip())
    return "\n".join(out).strip()


def _read_claude_md_design_sections(path: Path) -> str:
    """Return concatenated text of design-related ``## ...`` sections in CLAUDE.md."""
    f = path / "CLAUDE.md"
    if not f.exists():
        return ""
    chunks: list[str] = []
    current_heading: str | None = None
    current_body: list[str] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if current_heading and _heading_is_design(current_heading):
                chunks.append(current_heading + "\n" + "\n".join(current_body).rstrip())
            current_heading = line.strip()
            current_body = []
            continue
        current_body.append(line)
    if current_heading and _heading_is_design(current_heading):
        chunks.append(current_heading + "\n" + "\n".join(current_body).rstrip())
    return "\n\n".join(chunks).strip()


def _heading_is_design(heading: str) -> bool:
    """Return True for headings that capture design intent (status/architecture/invariants/etc.)."""
    if heading in _DEEP_HEADINGS:
        return True
    low = heading.lower()
    return any(k in low for k in _DEEP_KEYWORDS)


def _read_recent_commits(path: Path, *, n: int) -> list[str]:
    """Return up to ``n`` recent commit subjects via ``git log`` (empty list if no git)."""
    if not (path / ".git").exists():
        return []
    try:
        result = subprocess.run(  # noqa: S603,S607  # nosec B603 B607
            ["git", "-C", str(path), "log", f"-{n}", "--pretty=format:%s"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]
