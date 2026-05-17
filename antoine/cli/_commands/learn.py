"""``antoine learn`` — placeholder verb.

antoine is a greenfield AgentCulture sibling: the scaffold (package, CLI
chassis, CI, vendored skills) is in place but the codebase lookup and
indexing engine itself is not implemented yet. This verb prints an honest
status line so a probing agent or human gets a clear signal rather than a
misleading response.
"""

# pylint: disable=duplicate-code  # intentional: three stub verbs share the same structure

from __future__ import annotations

import argparse

from antoine import __version__
from antoine.cli._output import emit_result

_TEXT = (
    "antoine — codebase lookup and indexing for agent skills. Not yet implemented; "
    "antoine is a greenfield AgentCulture sibling. See CLAUDE.md."
)


def _json_payload() -> dict[str, object]:
    return {
        "tool": "antoine",
        "version": __version__,
        "status": "greenfield",
        "verb": "learn",
        "message": _TEXT,
    }


def cmd_learn(args: argparse.Namespace) -> int:
    """Handle the ``learn`` verb — print status and return 0."""
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result(_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:  # pylint: disable=duplicate-code
    """Register the ``learn`` sub-command on *sub*."""
    p = sub.add_parser("learn", help="Print antoine's self-teaching status line.")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
