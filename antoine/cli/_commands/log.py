"""`kata log` verb: parent + tail/gc/grep subcommands.

Tail is implemented here. GC and grep land in Tasks 8 and 9; their
subparsers stay wired to the `_unimplemented` placeholder until then.
"""

from __future__ import annotations

import argparse
from collections import deque

from antoine.cli._errors import EXIT_ENV_ERROR, AntoineError
from antoine.cli._output import emit_result
from antoine.kata.log._store import LogStore


def _no_subcommand(args: argparse.Namespace) -> int:
    args._parent_parser.print_help()
    return 0


def _unimplemented(args: argparse.Namespace) -> int:
    raise NotImplementedError(f"kata log {args.log_command} is not implemented yet")


def _handle_tail(args: argparse.Namespace) -> int:
    store = LogStore()
    if not store.root.exists() or not any(store.root.glob("*.jsonl")):
        raise AntoineError(
            code=EXIT_ENV_ERROR,
            message=(
                "No capture data found in .antoine/log/. "
                "antoine has no observed tool calls to display."
            ),
            remediation=(
                "Run `kata learn` to see how to instrument your agent, "
                "then start a session and try `kata log tail` again."
            ),
        )

    n = max(1, int(args.n))
    last = deque(store.read_all(), maxlen=n)
    for entry in last:
        emit_result(entry.to_json_line().rstrip("\n"), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "log",
        help="raw access to the local capture log",
        description="Inspect, prune, or search the local kata capture log under ./.antoine/log/.",
    )
    parser.set_defaults(func=_no_subcommand, _parent_parser=parser)
    subsub = parser.add_subparsers(dest="log_command")

    tail = subsub.add_parser("tail", help="print the last N captured entries")
    tail.add_argument("-n", default=10, type=int, help="number of entries (default: 10)")
    tail.set_defaults(func=_handle_tail)

    gc_p = subsub.add_parser("gc", help="delete capture entries past TTL")
    gc_p.set_defaults(func=_unimplemented)

    grep_p = subsub.add_parser("grep", help="filter log entries by substring")
    grep_p.set_defaults(func=_unimplemented)
