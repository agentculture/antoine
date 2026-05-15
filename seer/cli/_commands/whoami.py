"""``seer whoami`` — placeholder verb.

See :mod:`seer.cli._commands.learn` for why the verbs are stubs. ``whoami``
will eventually be the smallest identity / auth probe; today it prints an
honest "not yet implemented" line.
"""

from __future__ import annotations

import argparse

from seer import __version__
from seer.cli._output import emit_result

_TEXT = "seer — not yet implemented; seer is greenfield. See CLAUDE.md."


def _json_payload() -> dict[str, object]:
    return {
        "tool": "seer",
        "version": __version__,
        "status": "greenfield",
        "verb": "whoami",
        "message": _TEXT,
    }


def cmd_whoami(args: argparse.Namespace) -> int:
    """Handle the ``whoami`` verb — print status and return 0."""
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result(_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    """Register the ``whoami`` sub-command on *sub*."""
    p = sub.add_parser("whoami", help="Print seer's identity probe (stub).")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_whoami)
