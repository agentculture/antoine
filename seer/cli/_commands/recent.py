"""``seer recent [path] [-n N]`` — git commit log paired with AST symbol diffs.

Runs ``git log -n N`` in *path*, and for each commit pairs every changed file
with a structural symbol-diff at the AST level (functions/classes added /
removed / modified).
"""

# pylint: disable=duplicate-code  # verb-registration boilerplate

from __future__ import annotations

import argparse
from pathlib import Path

from seer.cli._output import emit_result
from seer.lookup.recent_outline import recent_with_outline, render_recent_markdown


def cmd_recent(args: argparse.Namespace) -> int:
    """Handle the ``recent`` verb."""
    path = Path(args.path).resolve()
    data = recent_with_outline(n=args.count, path=path)
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result(data, json_mode=True)
    else:
        emit_result(render_recent_markdown(data), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    """Register the ``recent`` sub-command on *sub*."""
    p = sub.add_parser(
        "recent",
        help="Show recent git commits paired with AST symbol diffs per file.",
    )
    p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the git repository (default: cwd).",
    )
    p.add_argument(
        "-n",
        "--count",
        type=int,
        default=20,
        metavar="N",
        help="Number of commits to show (default: 20).",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_recent)
