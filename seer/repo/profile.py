"""Single-repo profiler.

Two depths:

  * shallow (default) — mechanical facts from pyproject.toml, on-disk layout,
    vendored-skill list, CITATION.md, CHANGELOG.md, CLAUDE.md status section.
  * deep — shallow + README intro, CLAUDE.md design sections, last 10
    commit subjects (added in :func:`profile_deep`, separate task).

Missing optional sources degrade silently to empty fields.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from seer.repo.detect import resolve_name
from seer.repo.manifest import read_pyproject


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


def _list_packages(path: Path) -> list[str]:
    """Return one-level Python packages at the repo root or under ``src/``."""
    exclude = {"tests", "docs", "scripts", "__pycache__"}
    out: list[str] = []
    for child in sorted(path.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name in exclude:
            continue
        if (child / "__init__.py").exists():
            out.append(child.name + "/")
    src = path / "src"
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                out.append(f"src/{child.name}/")
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
            out[parts[0]] = {
                "source": parts[1],
                "version": parts[2] if len(parts) >= 3 else "",
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
            if parts[0].lower() == "local":
                continue
            out.append(
                {
                    "local": parts[0],
                    "source_repo": parts[1],
                    "sha": parts[2],
                }
            )
    return out


def _read_changelog(path: Path, *, n: int) -> list[dict[str, str]]:
    """Return up to ``n`` recent entries from ``CHANGELOG.md`` (Keep-a-Changelog)."""
    f = path / "CHANGELOG.md"
    if not f.exists():
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    seen_summary = False
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
                if len(entries) >= n:
                    return entries
            current = _parse_changelog_heading(line)
            current["summary"] = ""
            seen_summary = False
            continue
        if current is None or seen_summary:
            continue
        body = line.strip()
        if not body or body.startswith("#") or body.startswith("###"):
            continue
        current["summary"] = body.lstrip("-").strip()
        seen_summary = True
    if current is not None and len(entries) < n:
        entries.append(current)
    return entries[:n]


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
