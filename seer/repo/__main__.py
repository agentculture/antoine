"""argparse dispatch for ``python -m seer.repo``.

Verbs:

  profile <path> [--depth shallow|deep] [--json]
  connections <path> [--depth N|all] [--profile] [--depth-profile shallow|deep]
              [--root PATH ...] [--marker FILE ...] [--strict] [--json]
  graph [<root>...] [--marker FILE ...] [--json]

Output: markdown by default; JSON when ``--json`` is passed.
Errors: routed through :func:`seer.cli._output.emit_error`; partial-failure
inlining for walks lives inside :func:`seer.repo.connections.walk`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from seer.cli._errors import EXIT_INTERNAL, EXIT_USER_ERROR, SeerError
from seer.cli._output import emit_error, emit_result
from seer.repo.config import RepoMapConfig, load_config
from seer.repo.connections import walk
from seer.repo.errors import path_not_a_directory
from seer.repo.graph import build_graph
from seer.repo.profile import profile_deep, profile_shallow
from seer.repo.render import (
    render_connections_markdown,
    render_graph_markdown,
    render_profile_markdown,
)


def _profile(args: argparse.Namespace) -> int:
    """Handle the ``profile`` verb."""
    path = Path(args.path)
    if not path.is_dir():
        raise path_not_a_directory(path)
    data = profile_deep(path) if args.depth == "deep" else profile_shallow(path)
    if args.json:
        emit_result({"ok": True, "data": data}, json_mode=True)
    else:
        emit_result(render_profile_markdown(data), json_mode=False)
    return 0


def _connections(args: argparse.Namespace, cfg: RepoMapConfig) -> int:
    """Handle the ``connections`` verb."""
    seed = Path(args.path)
    if not seed.is_dir():
        raise path_not_a_directory(seed)
    roots = [Path(r) for r in (args.root or [str(p) for p in cfg.roots])]
    result = walk(
        seed=seed,
        roots=roots,
        depth=args.depth,
        with_profile=args.profile,
        depth_profile=args.depth_profile,
        additional_markers=(args.marker or cfg.additional_markers),
        skip_dirs=cfg.skip_dirs,
        strict=args.strict,
    )
    if args.json:
        emit_result({"ok": True, "data": result}, json_mode=True)
    else:
        emit_result(render_connections_markdown(result), json_mode=False)
    return 0


def _graph(args: argparse.Namespace, cfg: RepoMapConfig) -> int:
    """Handle the ``graph`` verb."""
    roots = [Path(r) for r in (args.roots or [str(p) for p in cfg.roots])]
    result = build_graph(
        roots,
        additional_markers=(args.marker or cfg.additional_markers),
        skip_dirs=cfg.skip_dirs,
    )
    if args.json:
        emit_result({"ok": True, "data": result}, json_mode=True)
    else:
        emit_result(render_graph_markdown(result), json_mode=False)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argparse parser for ``python -m seer.repo``."""
    parser = argparse.ArgumentParser(
        prog="seer.repo",
        description="repo-map engine: profile / connections / graph.",
    )
    sub = parser.add_subparsers(dest="verb")

    pp = sub.add_parser("profile", help="Profile one repo.")
    pp.add_argument("path")
    pp.add_argument("--depth", choices=["shallow", "deep"], default="shallow")
    pp.add_argument("--json", action="store_true")

    pc = sub.add_parser("connections", help="Walk outward from a seed repo.")
    pc.add_argument("path")
    pc.add_argument(
        "--depth",
        default="1",
        help="non-negative int or 'all' (default: 1)",
    )
    pc.add_argument(
        "--profile",
        action="store_true",
        help="include each internal node's profile",
    )
    pc.add_argument(
        "--depth-profile",
        choices=["shallow", "deep"],
        default="shallow",
        dest="depth_profile",
    )
    pc.add_argument(
        "--root",
        action="append",
        default=None,
        help="root to search for connected repos (repeatable)",
    )
    pc.add_argument(
        "--marker",
        action="append",
        default=None,
        help="additional marker filename (repeatable)",
    )
    pc.add_argument(
        "--strict",
        action="store_true",
        help="fail on any per-node error",
    )
    pc.add_argument("--json", action="store_true")

    pg = sub.add_parser("graph", help="Multi-root workspace view.")
    pg.add_argument("roots", nargs="*")
    pg.add_argument("--marker", action="append", default=None)
    pg.add_argument("--json", action="store_true")

    return parser


def _dispatch_verb(args: argparse.Namespace, cfg: RepoMapConfig) -> int:
    """Route *args.verb* to the correct handler and return its exit code."""
    if args.verb == "profile":
        return _profile(args)
    if args.verb == "connections":
        return _connections(args, cfg)
    if args.verb == "graph":
        return _graph(args, cfg)
    return EXIT_USER_ERROR


def main(argv: list[str] | None = None) -> int:
    """argparse entry point for ``python -m seer.repo``."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.verb is None:
        parser.print_help()
        return 0
    json_mode = bool(getattr(args, "json", False))
    cfg = load_config()
    try:
        return _dispatch_verb(args, cfg)
    except SeerError as err:
        emit_error(err, json_mode=json_mode)
        return err.code
    except Exception as err:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        wrapped = SeerError(
            code=EXIT_INTERNAL,
            kind="bug",
            message=f"unexpected: {err.__class__.__name__}: {err}",
            reason="An unhandled exception escaped a seer.repo verb.",
            remediation=("file a bug at https://github.com/agentculture/seer-cli/issues"),
        )
        emit_error(wrapped, json_mode=json_mode)
        return wrapped.code


if __name__ == "__main__":
    sys.exit(main())
