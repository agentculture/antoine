"""``antoine classify [path]`` — project-type classifier.

Returns a deterministic list of tags describing what kind of project the
repo at *path* is (cli / library / dockerized / tested / packaged-pypi / …),
each paired with concrete file-grounded evidence.
"""

# pylint: disable=duplicate-code  # verb-registration boilerplate

from __future__ import annotations

import argparse
from pathlib import Path

from antoine.cli._output import emit_result
from antoine.lookup.classify import classify
from antoine.lookup.render import render_classify_markdown


def cmd_classify(args: argparse.Namespace) -> int:
    """Handle the ``classify`` verb."""
    path = Path(args.path).resolve()
    data = classify(path)
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result({"ok": True, "data": data}, json_mode=True)
    else:
        emit_result(render_classify_markdown(data), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    """Register the ``classify`` sub-command on *sub*."""
    p = sub.add_parser(
        "classify",
        help="Classify a repo by project-type tags (cli / library / dockerized / …).",
    )
    p.add_argument("path", nargs="?", default=".", help="Path to the repo (default: cwd).")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_classify)
