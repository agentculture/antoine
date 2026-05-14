"""``seer learn`` — placeholder verb.

seer is a greenfield AgentCulture sibling: the scaffold (package, CLI
chassis, CI, vendored skills) is in place but the codebase lookup and
indexing engine itself is not implemented yet. This verb prints an honest
status line so a probing agent or human gets a clear signal rather than a
misleading response.
"""

from __future__ import annotations

import argparse

from seer import __version__
from seer.cli._output import emit_result

_TEXT = (
    "seer — codebase lookup and indexing for agent skills. Not yet implemented; "
    "seer is a greenfield AgentCulture sibling. See CLAUDE.md."
)


def _json_payload() -> dict[str, object]:
    return {
        "tool": "seer",
        "version": __version__,
        "status": "greenfield",
        "verb": "learn",
        "message": _TEXT,
    }


def cmd_learn(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result(_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("learn", help="Print seer's self-teaching status line.")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
