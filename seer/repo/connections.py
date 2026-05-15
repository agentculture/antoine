"""BFS walker from a seed repo.

Edge types emitted:

  * ``import``  — from manifest deps_runtime
  * ``cite``    — from CITATION.md
  * ``vendor``  — from vendored_skills' ``source`` provenance

Each edge target name is resolved against repos discovered under
``roots`` via :func:`seer.repo.detect.find_repos`. Unresolvable target names
become "external" nodes (no path, no profile).

Per-node errors during the walk are collected in the result's
``walk_errors`` field; the walk continues unless ``strict=True``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from seer.cli._errors import SeerError
from seer.repo.detect import find_repos, resolve_name
from seer.repo.errors import invalid_depth, path_not_a_directory
from seer.repo.profile import profile_deep, profile_shallow


def _coerce_depth(depth: int | str | None) -> int | str:
    """Normalise *depth* to a non-negative ``int`` or the sentinel ``"all"``.

    Raises :func:`seer.repo.errors.invalid_depth` for any value that is
    neither a non-negative integer nor the string ``"all"``.
    """
    if depth is None:
        return 1
    if isinstance(depth, str):
        if depth == "all":
            return "all"
        try:
            n = int(depth)
        except ValueError as exc:
            raise invalid_depth(depth) from exc
    else:
        n = depth
    if n < 0:
        raise invalid_depth(str(n))
    return n


def _build_index(
    roots: list[Path],
    additional_markers: list[str] | None,
    skip_dirs: list[str] | None,
) -> dict[str, Path]:
    """Map every known repo name to its path (first-write wins on collisions)."""
    index: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for repo in find_repos(
            root,
            additional_markers=additional_markers,
            skip_dirs=skip_dirs,
        ):
            name = resolve_name(repo)
            index.setdefault(name, repo)
    return index


def _strip_version(spec: str) -> str:
    """Return the bare package name from a PEP 508 dependency specifier.

    Examples::

        "pkg[extra]>=1.0"  -> "pkg"
        "requests>=2,<3"   -> "requests"
        "mylib"            -> "mylib"
    """
    for sep in ("[", "(", ">=", "<=", ">", "<", "==", "!=", "~="):
        if sep in spec:
            spec = spec.split(sep, 1)[0]
    return spec.strip()


def _edges_from_profile(name: str, profile: dict[str, Any]) -> list[dict[str, str]]:
    """Build the outgoing edge list for *name* from its shallow profile dict."""
    edges: list[dict[str, str]] = []
    _collect_import_edges(edges, name, profile.get("deps_runtime") or [])
    _collect_cite_edges(edges, name, profile.get("citations") or [])
    _collect_vendor_edges(edges, name, profile.get("vendored_skills") or [])
    return edges


def _collect_import_edges(edges: list[dict[str, str]], name: str, deps: list[Any]) -> None:
    """Append ``import`` edges to *edges* for each runtime dependency."""
    for dep in deps:
        target = _strip_version(dep)
        if target:
            edges.append({"from": name, "to": target, "type": "import", "spec": dep})


def _collect_cite_edges(edges: list[dict[str, str]], name: str, citations: list[Any]) -> None:
    """Append ``cite`` edges to *edges* for each CITATION.md row."""
    for cit in citations:
        repo = cit.get("source_repo")
        if repo:
            edges.append(
                {
                    "from": name,
                    "to": str(repo),
                    "type": "cite",
                    "spec": str(cit.get("sha", "")),
                }
            )


def _collect_vendor_edges(edges: list[dict[str, str]], name: str, skills: list[Any]) -> None:
    """Append ``vendor`` edges to *edges* for each vendored skill with a source."""
    for skill in skills:
        source = skill.get("source")
        if source:
            edges.append(
                {
                    "from": name,
                    "to": str(source),
                    "type": "vendor",
                    "spec": str(skill.get("name", "")),
                }
            )


@dataclass
class _ProfileOpts:
    """Options that control how nodes are profiled during the BFS walk."""

    with_profile: bool = False
    depth_profile: str = "shallow"
    strict: bool = False


@dataclass
class _BfsState:
    """Mutable BFS accumulator: repo index, depth budget, queue, and results."""

    index: dict[str, Path]
    depth_n: int | str
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, str]] = field(default_factory=list)
    walk_errors: list[dict[str, str]] = field(default_factory=list)
    visited: set[str] = field(default_factory=set)
    queue: deque = field(default_factory=deque)


def _profile_node(path: Path, opts: _ProfileOpts) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(node_extra, shallow_profile)`` for an internal node."""
    p = profile_shallow(path)
    node_extra: dict[str, Any] = {"version": p.get("version", "")}
    if opts.with_profile:
        node_extra["profile"] = profile_deep(path) if opts.depth_profile == "deep" else p
    return node_extra, p


def _enqueue_targets(
    outgoing: list[dict[str, str]],
    state: _BfsState,
    current_hop: int,
) -> None:
    """Push unvisited edge targets onto *state.queue* when the depth budget allows."""
    within_budget = state.depth_n == "all" or current_hop < int(
        state.depth_n
    )  # type: ignore[arg-type]
    if not within_budget:
        return
    for edge in outgoing:
        target = edge["to"]
        if target not in state.visited:
            state.visited.add(target)
            state.queue.append((target, current_hop + 1))


def _expand_node(
    current_name: str,
    path: Path,
    current_hop: int,
    state: _BfsState,
    opts: _ProfileOpts,
) -> dict[str, Any]:
    """Profile *path*, collect edges, enqueue targets; return the node dict."""
    node: dict[str, Any] = {"id": current_name, "path": str(path), "external": False}
    try:
        node_extra, shallow = _profile_node(path, opts)
        node.update(node_extra)
        outgoing = _edges_from_profile(current_name, shallow)
        state.edges.extend(outgoing)
        _enqueue_targets(outgoing, state, current_hop)
    except SeerError as err:
        if opts.strict:
            raise
        state.walk_errors.append(
            {
                "node": f"{current_name} ({path})",
                "reason": err.reason or err.message,
                "remediation": err.remediation,
            }
        )
    return node


def _run_bfs(
    seed_name: str,
    index: dict[str, Path],
    depth_n: int | str,
    opts: _ProfileOpts,
) -> _BfsState:
    """Execute the BFS from *seed_name* and return the populated state."""
    state = _BfsState(index=index, depth_n=depth_n)
    state.visited.add(seed_name)
    state.queue.append((seed_name, 0))

    while state.queue:
        current_name, current_hop = state.queue.popleft()
        path = state.index.get(current_name)
        if path is not None:
            node = _expand_node(current_name, path, current_hop, state, opts)
        else:
            node = {"id": current_name, "path": None, "external": True}
        state.nodes.append(node)

    return state


def walk(  # pylint: disable=too-many-arguments
    *,
    seed: Path,
    roots: list[Path],
    depth: int | str = 1,
    with_profile: bool = False,
    depth_profile: str = "shallow",
    additional_markers: list[str] | None = None,
    skip_dirs: list[str] | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """BFS-walk from *seed* outward, emitting nodes + typed edges.

    Parameters
    ----------
    seed:
        The root repo to start from (must be an existing directory).
    roots:
        Workspace roots scanned by :func:`seer.repo.detect.find_repos` to
        resolve edge targets to local paths.
    depth:
        How many hops to follow.  ``1`` visits direct neighbours only;
        ``"all"`` walks the full connected component.
    with_profile:
        When *True*, attach a ``"profile"`` key to each internal node.
    depth_profile:
        ``"shallow"`` (default) or ``"deep"``; controls which profiler is
        used when *with_profile* is *True*.
    additional_markers:
        Extra filenames treated as repo markers during discovery.
    skip_dirs:
        Directory names skipped during discovery.
    strict:
        When *True*, a per-node :class:`SeerError` re-raises immediately
        instead of being collected in ``walk_errors``.

    Returns
    -------
    dict with keys:
        ``seed``, ``seed_name``, ``depth``, ``nodes``, ``edges``,
        ``walk_errors``.
    """
    if not seed.is_dir():
        raise path_not_a_directory(seed)
    depth_n = _coerce_depth(depth)

    index = _build_index(roots, additional_markers, skip_dirs)
    seed_name = resolve_name(seed)
    index.setdefault(seed_name, seed)

    opts = _ProfileOpts(
        with_profile=with_profile,
        depth_profile=depth_profile,
        strict=strict,
    )
    accum = _run_bfs(seed_name, index, depth_n, opts)

    return {
        "seed": str(seed),
        "seed_name": seed_name,
        "depth": depth_n,
        "nodes": accum.nodes,
        "edges": accum.edges,
        "walk_errors": accum.walk_errors,
    }
