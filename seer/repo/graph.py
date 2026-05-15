"""Multi-root workspace view: every repo found + every edge between them.

This is the "show me what's in this workspace" verb, distinct from
:func:`seer.repo.connections.walk` which traverses outward from a single seed.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from seer.cli._errors import SeerError
from seer.repo.connections import _edges_from_profile
from seer.repo.detect import find_repos, resolve_name
from seer.repo.profile import profile_shallow

_SAFE_RE = re.compile(r"[^A-Za-z0-9_]")


def build_graph(  # pylint: disable=too-many-locals
    roots: list[Path],
    *,
    additional_markers: list[str] | None = None,
    skip_dirs: list[str] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Build a workspace graph over the given roots.

    Per-node profiling errors are collected in ``walk_errors``; the build
    continues unless ``strict=True``.

    Parameters
    ----------
    roots:
        One or more workspace root directories.  Each is scanned with
        :func:`seer.repo.detect.find_repos`; results are unioned.
    additional_markers:
        Extra filenames treated as repo markers during discovery.
    skip_dirs:
        Directory names skipped during discovery.
    strict:
        When ``True``, re-raise the first per-node :class:`SeerError`
        instead of inlining it into ``walk_errors``.

    Returns
    -------
    dict with keys:
        ``roots``, ``nodes``, ``edges``, ``walk_errors``, ``mermaid``.
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
    walk_errors: list[dict[str, str]] = []

    for name, path in sorted(name_to_path.items()):
        try:
            p = profile_shallow(path)
        except SeerError as err:
            if strict:
                raise
            walk_errors.append(
                {
                    "node": f"{name} ({path})",
                    "reason": err.reason or err.message,
                    "remediation": err.remediation,
                }
            )
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
        "walk_errors": walk_errors,
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
    """Return a Mermaid-safe node id for ``name``.

    Mermaid identifiers must match ``[A-Za-z_][A-Za-z0-9_]*``. This
    helper:

    * Replaces every character outside ``[A-Za-z0-9_]`` with ``_``.
    * Prepends ``n_`` when the sanitised value is empty or starts with
      a digit (Mermaid forbids digit-leading identifiers).
    * Appends a short stable hash of the original string whenever
      sanitisation actually changed the value, so two distinct inputs
      that would otherwise collapse to the same id (e.g. ``a-b`` and
      ``a_b``, or ``foo bar`` and ``foo/bar``) stay distinct in the
      generated diagram.
    """
    if not name:
        return "n_"
    sanitised = _SAFE_RE.sub("_", name)
    if sanitised != name:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
        sanitised = f"{sanitised}_{digest}"
    if sanitised[0].isdigit():
        sanitised = "n_" + sanitised
    return sanitised
