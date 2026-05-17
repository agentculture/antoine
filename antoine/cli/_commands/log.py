"""`kata log` verb: parent + tail/gc/grep subcommands."""

from __future__ import annotations

import argparse
from collections import deque

from antoine.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, AntoineError
from antoine.cli._output import emit_result
from antoine.kata.log._gc import gc as _gc_run
from antoine.kata.log._store import LogStore


def _no_subcommand(args: argparse.Namespace) -> int:
    args._parent_parser.print_help()
    return 0


def _handle_grep(args: argparse.Namespace) -> int:
    store = LogStore()
    if not store.root.exists() or not any(store.root.glob("*.jsonl")):
        raise AntoineError(
            code=EXIT_ENV_ERROR,
            message="No capture data found in .antoine/log/. antoine has nothing to grep.",
            remediation=(
                "Run `kata learn` to see how to instrument your agent, "
                "then start a session before grepping the log."
            ),
        )

    needle = args.pattern
    for entry in store.read_all():
        haystack = " ".join(
            v for v in (entry.tool, entry.bash_argv0 or "", entry.agent, entry.session) if v
        )
        if needle in haystack:
            emit_result(entry.to_json_line().rstrip("\n"), json_mode=False)
    return 0


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


def _handle_gc(args: argparse.Namespace) -> int:
    if args.ttl_days < 0:
        raise AntoineError(
            code=EXIT_USER_ERROR,
            message=(
                f"--ttl-days must be >= 0 (got {args.ttl_days}). "
                "A negative TTL would classify every log file as stale and "
                "delete the entire log."
            ),
            remediation="Re-run with a non-negative value, e.g. `kata log gc --ttl-days 7`.",
        )

    store = LogStore()
    if not store.root.exists():
        message = "deleted 0 shape files, 0 args files (no log present)"
    else:
        try:
            result = _gc_run(root=store.root, ttl_days=args.ttl_days)
        except PermissionError as exc:
            raise AntoineError(
                code=EXIT_ENV_ERROR,
                message=(
                    f"GC could not delete files past TTL: {exc}. "
                    "The privacy invariant requires expired data to be removed."
                ),
                remediation=(
                    "Check filesystem permissions on .antoine/log/ "
                    "(needs delete access for the user running antoine), then retry."
                ),
            ) from exc
        message = (
            f"deleted {len(result.deleted_shape)} shape files, "
            f"{len(result.deleted_args)} args files"
        )

    emit_result(message, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "log",
        help="raw access to the local capture log",
        description="Inspect, prune, or search the local kata capture log under ./.antoine/log/.",
    )
    parser.set_defaults(func=_no_subcommand, _parent_parser=parser)
    # Nested parsers MUST share the structured-error wrapper used by the top
    # level — otherwise `kata log tail --bogus` exits 2 via default argparse,
    # bypassing the "antoine never crashes" contract. (Qodo #25 bug 1.)
    subsub = parser.add_subparsers(dest="log_command", parser_class=type(parser))

    tail = subsub.add_parser("tail", help="print the last N captured entries")
    tail.add_argument("-n", default=10, type=int, help="number of entries (default: 10)")
    tail.set_defaults(func=_handle_tail)

    gc_p = subsub.add_parser("gc", help="delete capture entries past TTL")
    gc_p.add_argument(
        "--ttl-days",
        type=int,
        default=7,
        help="retention window in days (default: 7)",
    )
    gc_p.set_defaults(func=_handle_gc)

    grep_p = subsub.add_parser("grep", help="filter log entries by substring")
    grep_p.add_argument("pattern", help="substring matched against tool/bash_argv0/agent/session")
    grep_p.set_defaults(func=_handle_grep)
