"""Single-repo profiler.

Two depths:

  * shallow (default) — mechanical facts from pyproject.toml, on-disk layout,
    vendored-skill list, CITATION.md, CHANGELOG.md, CLAUDE.md status section.
  * deep — shallow + README intro, CLAUDE.md design sections, last 10
    commit subjects (added in :func:`profile_deep`, separate task).

Missing optional sources degrade silently to empty fields.
"""

from __future__ import annotations

import subprocess  # noqa: S404  # nosec B404
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
            key = parts[0].strip("` ").strip()
            if key.lower() in {"name", "skill"}:
                continue
            out[key] = {
                "source": parts[1].strip("` ").strip(),
                "version": parts[2].strip("` ").strip() if len(parts) >= 3 else "",
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
            first = parts[0].lower().strip("` ").strip()
            if first.startswith("local") or first in {"path", "file"}:
                continue
            out.append(
                {
                    "local": parts[0].strip("` ").strip(),
                    "source_repo": parts[1].strip("` ").strip(),
                    "sha": parts[2].strip("` ").strip(),
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
