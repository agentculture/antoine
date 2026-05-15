"""Markdown emitters for seer.repo.

Each ``render_*_markdown`` function takes a plain dict (the shape produced
by :mod:`seer.repo.profile`, and later :mod:`seer.repo.connections` /
:mod:`seer.repo.graph`) and returns a string.

The matching JSON envelopes are produced by callers via
:func:`seer.cli._output.emit_result` with ``json_mode=True``; render.py
does not duplicate that.
"""

from __future__ import annotations

from typing import Any

from seer.cli._errors import EXIT_ENV_ERROR, EXIT_INTERNAL, EXIT_USER_ERROR, SeerError

_KIND_LABEL = {
    EXIT_USER_ERROR: "user error",
    EXIT_ENV_ERROR: "environment error",
    EXIT_INTERNAL: "internal bug",
}


def _append_skill_table(lines: list[str], skills: list[dict]) -> None:
    """Append the vendored-skills table section to *lines*."""
    lines.append("")
    lines.append(f"## Vendored skills ({len(skills)})")
    lines.append("| Skill | Source | Version |")
    lines.append("|---|---|---|")
    for s in skills:
        lines.append(f"| {s.get('name', '')} | {s.get('source', '')} | {s.get('version', '')} |")


def _append_citation_table(lines: list[str], citations: list[dict]) -> None:
    """Append the citations table section to *lines*."""
    lines.append("")
    lines.append(f"## Citations ({len(citations)})")
    lines.append("| Local | Source repo | SHA |")
    lines.append("|---|---|---|")
    for c in citations:
        lines.append(f"| {c.get('local', '')} | {c.get('source_repo', '')} | {c.get('sha', '')} |")


def _changelog_line(entry: dict) -> str:
    """Format a single changelog entry as a markdown list item."""
    v = entry.get("version", "")
    d = entry.get("date", "")
    s = entry.get("summary", "")
    date_suffix = f" ({d})" if d else ""
    return f"- **{v}**{date_suffix} — {s}"


def _append_changelog(lines: list[str], changelog: list[dict]) -> None:
    """Append the recent-changelog section to *lines*."""
    lines.append("")
    lines.append("## Recent changelog")
    for entry in changelog:
        lines.append(_changelog_line(entry))


def _append_shallow_sections(lines: list[str], profile: dict[str, Any]) -> None:
    """Append all shallow-profile sections (deps, layout, skills, citations, etc.)."""
    deps = profile.get("deps_runtime") or []
    if deps:
        lines.append("")
        lines.append(f"## Runtime dependencies ({len(deps)})")
        for d in deps:
            lines.append(f"- {d}")

    layout = profile.get("package_layout") or []
    if layout:
        lines.append("")
        lines.append("## Package layout")
        for item in layout:
            lines.append(f"- {item}")

    skills = profile.get("vendored_skills") or []
    if skills:
        _append_skill_table(lines, skills)

    citations = profile.get("citations") or []
    if citations:
        _append_citation_table(lines, citations)

    changelog = profile.get("changelog_recent") or []
    if changelog:
        _append_changelog(lines, changelog)

    status = profile.get("claude_md_status") or ""
    if status:
        lines.append("")
        lines.append("## Project status")
        lines.append(status)

    extra = profile.get("extra") or {}
    if extra:
        lines.append("")
        lines.append("## Extra")
        for k, v in extra.items():
            lines.append(f"- **{k}:** {v}")


def _append_deep_sections(lines: list[str], profile: dict[str, Any]) -> None:
    """Append deep-only sections (readme intro, CLAUDE.md content, commits)."""
    readme = profile.get("readme_intro") or ""
    if readme:
        lines.append("")
        lines.append("## Readme intro")
        lines.append(readme)

    md_sections = profile.get("claude_md_sections") or ""
    if md_sections:
        lines.append("")
        lines.append(md_sections)

    commits = profile.get("commits_recent") or []
    if commits:
        lines.append("")
        lines.append("## Recent commits")
        for c in commits:
            lines.append(f"- {c}")


def render_profile_markdown(profile: dict[str, Any]) -> str:
    """Render a profile dict (shallow or deep) as a markdown report."""
    lines: list[str] = []
    name = profile.get("name") or "(unknown)"
    lines.append(f"# {name}")

    version = profile.get("version") or ""
    if version:
        lines.append(f"- **Version:** {version}")

    manifest = profile.get("manifest")
    language = profile.get("language") or "unknown"
    if manifest:
        lines.append(f"- **Manifest:** {manifest} ({language})")
    else:
        lines.append(f"- **Manifest:** none ({language})")

    path = profile.get("path") or ""
    if path:
        lines.append(f"- **Path:** {path}")

    entry_points = profile.get("entry_points") or {}
    if entry_points:
        lines.append("")
        lines.append("## Entry points")
        for k, v in entry_points.items():
            lines.append(f"- `{k}` → `{v}`")

    _append_shallow_sections(lines, profile)
    _append_deep_sections(lines, profile)

    return "\n".join(lines) + "\n"


def render_error_markdown(err: SeerError) -> str:
    """Render a :class:`SeerError` as a markdown error block (for stderr)."""
    label = _KIND_LABEL.get(err.code, "error")
    lines: list[str] = []
    lines.append(f"**Error:** {err.message}")
    if err.reason:
        lines.append("")
        lines.append(f"**Reason:** {err.reason}")
    if err.remediation:
        lines.append("")
        lines.append(f"**Remediation:** {err.remediation}")
    lines.append("")
    lines.append(f"Exit code: {err.code} ({label})")
    return "\n".join(lines) + "\n"
