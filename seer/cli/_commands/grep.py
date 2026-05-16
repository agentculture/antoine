"""``seer grep <pattern> [path]`` — AST-scope-augmented ripgrep search.

Runs ``rg --json <pattern> <path>`` and pairs every match with the enclosing
Python function or class name via the AST scope resolver.
"""

# pylint: disable=duplicate-code  # verb-registration boilerplate

from __future__ import annotations

import argparse
from pathlib import Path

from seer.cli._output import emit_result
from seer.lookup.grep_context import grep_with_context, render_grep_markdown


def cmd_grep(args: argparse.Namespace) -> int:
    """Handle the ``grep`` verb."""
    path = Path(args.path).resolve()
    data = grep_with_context(args.pattern, path)
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result(data, json_mode=True)
    else:
        emit_result(render_grep_markdown(data), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    """Register the ``grep`` sub-command on *sub*."""
    p = sub.add_parser(
        "grep",
        help="Search a codebase with rg and annotate each match with its AST scope.",
    )
    p.add_argument("pattern", help="Regex pattern to search for.")
    p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="File or directory to search (default: cwd).",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_grep)
