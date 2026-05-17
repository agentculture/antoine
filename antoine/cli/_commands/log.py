"""`kata log` verb: parent + tail/gc/grep subcommands.

Subparsers for tail/gc/grep are registered here with placeholder handlers;
Tasks 7-9 of the kata-log-subsystem plan replace the bodies with the real
implementations. The placeholder raises NotImplementedError if anyone
invokes a subcommand before its task lands.
"""

from __future__ import annotations

import argparse


def _no_subcommand(args: argparse.Namespace) -> int:
    args._parent_parser.print_help()
    return 0


def _unimplemented(args: argparse.Namespace) -> int:
    raise NotImplementedError(f"kata log {args.log_command} is not implemented yet")


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "log",
        help="raw access to the local capture log",
        description="Inspect, prune, or search the local kata capture log under ./.antoine/log/.",
    )
    parser.set_defaults(func=_no_subcommand, _parent_parser=parser)
    subsub = parser.add_subparsers(dest="log_command")

    tail = subsub.add_parser("tail", help="print the last N captured entries")
    tail.set_defaults(func=_unimplemented)

    gc_p = subsub.add_parser("gc", help="delete capture entries past TTL")
    gc_p.set_defaults(func=_unimplemented)

    grep_p = subsub.add_parser("grep", help="filter log entries by substring")
    grep_p.set_defaults(func=_unimplemented)
