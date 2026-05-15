"""Multi-root workspace view: every repo found + every edge between them.

This is the "show me what's in this workspace" verb, distinct from
:func:`seer.repo.connections.walk` which traverses outward from a single seed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from seer.repo.connections import _edges_from_profile
from seer.repo.detect import find_repos, resolve_name
from seer.repo.profile import profile_shallow


def build_graph(
    roots: list[Path],
    *,
    additional_markers: list[str] | None = None,
    skip_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """Build a workspace graph over the given roots.

    Parameters
    ----------
    roots:
        One or more workspace root directories.  Each is scanned with
        :func:`seer.repo.detect.find_repos`; results are unioned.
    additional_markers:
        Extra filenames treated as repo markers during discovery.
    skip_dirs:
        Directory names skipped during discovery.

    Returns
    -------
    dict with keys:
        ``roots``, ``nodes``, ``edges``, ``mermaid``.
    """
    name_to_path: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for repo in find_repos(
            root,
            additional_markers=additional_markers,
            skip_dirs=skip_dirs,
        ):
            name_to_path.setdefault(resolve_name(repo), repo)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    external_seen: set[str] = set()

    for name, path in sorted(name_to_path.items()):
        try:
            p = profile_shallow(path)
        except Exception:  # pylint: disable=broad-exception-caught  # workspace view never aborts
            p = {}
        nodes.append(
            {
                "id": name,
                "path": str(path),
                "external": False,
                "version": p.get("version", ""),
            }
        )
        for edge in _edges_from_profile(name, p):
            edges.append(edge)
            target = edge["to"]
            if target not in name_to_path and target not in external_seen:
                external_seen.add(target)

    for ext in sorted(external_seen):
        nodes.append({"id": ext, "path": None, "external": True})

    return {
        "roots": [str(r) for r in roots],
        "nodes": nodes,
        "edges": edges,
        "mermaid": _render_mermaid(nodes, edges),
    }


def _render_mermaid(
    _nodes: list[dict[str, Any]],
    edges: list[dict[str, str]],
) -> str:
    """Return a Mermaid ``graph TD`` source for the workspace."""
    lines = ["graph TD"]
    for edge in edges:
        spec = edge.get("spec") or ""
        edge_type = edge.get("type") or ""
        if edge_type:
            label = f"|{edge_type}{(' ' + spec) if spec else ''}|"
        else:
            label = ""
        lines.append(f"  {_safe(edge['from'])} -->{label} {_safe(edge['to'])}")
    return "\n".join(lines) + "\n"


def _safe(name: str) -> str:
    """Return a Mermaid-safe node id (replaces ``-`` and ``.`` with ``_``)."""
    return name.replace("-", "_").replace(".", "_")
