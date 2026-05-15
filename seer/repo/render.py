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


def _section_break(lines: list[str]) -> None:
    """Emit a blank line + horizontal rule before a new section heading.

    Gives top-level ``##`` sections a strong visual anchor — readers (human
    or LLM) can scan the report and immediately see section boundaries even
    when individual sections contain dense prose-filled tables.
    """
    lines.append("")
    lines.append("---")


def _append_skill_table(lines: list[str], skills: list[dict]) -> None:
    """Append the vendored-skills table section to *lines*."""
    _section_break(lines)
    lines.append(f"## Vendored skills ({len(skills)})")
    lines.append("| Skill | Source | Version |")
    lines.append("|---|---|---|")
    for s in skills:
        lines.append(f"| {s.get('name', '')} | {s.get('source', '')} | {s.get('version', '')} |")


def _append_citation_table(lines: list[str], citations: list[dict]) -> None:
    """Append the citations table section to *lines*."""
    _section_break(lines)
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
    _section_break(lines)
    lines.append("## Recent changelog")
    for entry in changelog:
        lines.append(_changelog_line(entry))


def _append_deps_runtime(lines: list[str], deps: list[str]) -> None:
    """Append the `## Runtime dependencies` block."""
    _section_break(lines)
    lines.append(f"## Runtime dependencies ({len(deps)})")
    for d in deps:
        lines.append(f"- {d}")


def _append_tree_node(lines: list[str], node: dict[str, Any], indent: int) -> None:
    """Render one ``package_tree`` node and recurse into its subpackages."""
    pad = "  " * indent
    lines.append(f"{pad}- **{node.get('name', '')}/**")
    modules = node.get("modules") or []
    if modules:
        module_pad = "  " * (indent + 1)
        joined = ", ".join(f"`{m}`" for m in modules)
        lines.append(f"{module_pad}- {joined}")
    for sub in node.get("subpackages") or []:
        _append_tree_node(lines, sub, indent + 1)


def _append_package_layout(
    lines: list[str], layout: list[str], tree: list[dict[str, Any]] | None
) -> None:
    """Append the `## Package layout` block — nested tree if available, flat list otherwise."""
    _section_break(lines)
    lines.append("## Package layout")
    if tree:
        for node in tree:
            _append_tree_node(lines, node, indent=0)
        return
    for item in layout:
        lines.append(f"- {item}")


def _append_project_status(lines: list[str], status: str) -> None:
    """Append the `## Project status` block."""
    _section_break(lines)
    lines.append("## Project status")
    lines.append(status)


def _append_extra(lines: list[str], extra: dict[str, Any]) -> None:
    """Append the `## Extra` key/value block."""
    _section_break(lines)
    lines.append("## Extra")
    for k, v in extra.items():
        lines.append(f"- **{k}:** {v}")


def _append_shallow_sections(lines: list[str], profile: dict[str, Any]) -> None:
    """Append every populated shallow-profile section to *lines*.

    The body is a flat sequence of "if this section has content, render it"
    calls; each per-section appender keeps its own complexity small.
    """
    if deps := profile.get("deps_runtime") or []:
        _append_deps_runtime(lines, deps)
    layout = profile.get("package_layout") or []
    tree = profile.get("package_tree") or []
    if layout or tree:
        _append_package_layout(lines, layout, tree)
    if skills := profile.get("vendored_skills") or []:
        _append_skill_table(lines, skills)
    if citations := profile.get("citations") or []:
        _append_citation_table(lines, citations)
    if changelog := profile.get("changelog_recent") or []:
        _append_changelog(lines, changelog)
    if status := profile.get("claude_md_status") or "":
        _append_project_status(lines, status)
    if extra := profile.get("extra") or {}:
        _append_extra(lines, extra)


def _append_deep_sections(lines: list[str], profile: dict[str, Any]) -> None:
    """Append deep-only sections (readme intro, CLAUDE.md content, commits)."""
    readme = profile.get("readme_intro") or ""
    if readme:
        _section_break(lines)
        lines.append("## Readme intro")
        lines.append(readme)

    md_sections = profile.get("claude_md_sections") or ""
    if md_sections:
        _section_break(lines)
        lines.append(md_sections)

    commits = profile.get("commits_recent") or []
    if commits:
        _section_break(lines)
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
        _section_break(lines)
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


def _append_edge_section(
    lines: list[str],
    label: str,
    es: list[dict[str, str]],
    nodes_by_id: dict[str, Any],
) -> None:
    """Append one typed edge group (imports / citations / vendored) to *lines*."""
    lines.append("")
    lines.append(f"## {label} ({len(es)})")
    for edge in es:
        target = edge["to"]
        node = nodes_by_id.get(target, {})
        loc = node.get("path")
        tag = f"({loc})" if loc else "(external)"
        spec = edge.get("spec") or ""
        spec_suffix = f" {spec}" if spec else ""
        lines.append(f"- {target} {tag}{spec_suffix}")


def _append_walk_errors(lines: list[str], errors: list[dict[str, str]]) -> None:
    """Append the walk-errors section to *lines*."""
    lines.append("")
    lines.append(f"## Errors during walk ({len(errors)})")
    for err in errors:
        lines.append("")
        lines.append(f"**{err.get('node', '')}**")
        if err.get("reason"):
            lines.append(f"- Reason: {err['reason']}")
        if err.get("remediation"):
            lines.append(f"- Remediation: {err['remediation']}")


def _append_node_list(lines: list[str], nodes: list[dict[str, Any]]) -> None:
    """Append internal repo list items to *lines*."""
    for node in nodes:
        v = node.get("version") or ""
        v_suffix = f" — {v}" if v else ""
        lines.append(f"- **{node['id']}** ({node.get('path', '')}){v_suffix}")


def _append_external_list(lines: list[str], nodes: list[dict[str, Any]]) -> None:
    """Append external target list items to *lines*."""
    for node in nodes:
        lines.append(f"- {node['id']}")


def _append_graph_edges(
    lines: list[str],
    by_type: dict[str, list[dict[str, str]]],
) -> None:
    """Append typed edge sections to *lines*."""
    for kind, label in [
        ("import", "Import edges"),
        ("cite", "Citation edges"),
        ("vendor", "Vendor edges"),
    ]:
        es = by_type.get(kind)
        if not es:
            continue
        lines.append("")
        lines.append(f"## {label} ({len(es)})")
        for edge in es:
            spec = edge.get("spec") or ""
            spec_suffix = f" {spec}" if spec else ""
            lines.append(f"- {edge['from']} → {edge['to']}{spec_suffix}")


def render_graph_markdown(graph: dict[str, Any]) -> str:
    """Render a workspace-graph dict as a markdown report including mermaid."""
    lines: list[str] = []
    roots = graph.get("roots") or []
    lines.append("# Workspace graph")
    if roots:
        lines.append("Roots: " + ", ".join(roots))

    nodes = graph.get("nodes") or []
    internal = [n for n in nodes if not n.get("external")]
    external = [n for n in nodes if n.get("external")]

    if internal:
        lines.append("")
        lines.append(f"## Repos ({len(internal)})")
        _append_node_list(lines, internal)

    if external:
        lines.append("")
        lines.append(f"## External targets ({len(external)})")
        _append_external_list(lines, external)

    edges = graph.get("edges") or []
    by_type: dict[str, list[dict[str, str]]] = {}
    for edge in edges:
        by_type.setdefault(edge["type"], []).append(edge)
    _append_graph_edges(lines, by_type)

    walk_errors = graph.get("walk_errors") or []
    if walk_errors:
        _append_walk_errors(lines, walk_errors)

    mermaid = graph.get("mermaid") or ""
    if mermaid:
        lines.append("")
        lines.append("## Mermaid")
        lines.append("```mermaid")
        lines.append(mermaid.rstrip())
        lines.append("```")

    return "\n".join(lines) + "\n"


def render_connections_markdown(walk: dict[str, Any]) -> str:
    """Render a connections-walk dict as a markdown report."""
    name = walk.get("seed_name") or "(unknown)"
    depth = walk.get("depth")
    lines: list[str] = []
    lines.append(f"# {name} — connections (depth {depth})")
    seed_path = walk.get("seed")
    if seed_path:
        lines.append(f"Seed: {seed_path}")

    edges = walk.get("edges") or []
    nodes_by_id: dict[str, Any] = {n["id"]: n for n in (walk.get("nodes") or [])}

    by_type: dict[str, list[dict[str, str]]] = {}
    for edge in edges:
        by_type.setdefault(edge["type"], []).append(edge)

    for kind, label in [
        ("import", "Imports"),
        ("cite", "Citations"),
        ("vendor", "Vendored skills"),
    ]:
        edge_group = by_type.get(kind)
        if edge_group:
            _append_edge_section(lines, label, edge_group, nodes_by_id)

    errors = walk.get("walk_errors") or []
    if errors:
        _append_walk_errors(lines, errors)

    internal = sum(1 for n in nodes_by_id.values() if not n.get("external"))
    external = sum(1 for n in nodes_by_id.values() if n.get("external"))
    lines.append("")
    lines.append("## Summary")
    lines.append(f"{internal} internal node(s), {external} external; {len(edges)} edge(s) total.")

    return "\n".join(lines) + "\n"
