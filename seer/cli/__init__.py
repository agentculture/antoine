"""Unified CLI entry point for seer.

Error-propagation contract: every handler raises
:class:`seer.cli._errors.SeerError` on failure; ``main()`` catches it via
:func:`_dispatch` and routes through :mod:`seer.cli._output`. Unknown
exceptions are wrapped into a ``SeerError`` so no Python traceback leaks.

Argparse errors (unknown verb, missing required arg) also route through the
structured format — :class:`_SeerArgumentParser` overrides ``.error()``.
Whether errors render as text or JSON depends on whether ``--json`` appears in
the raw argv (:func:`main` sets ``_SeerArgumentParser._json_hint`` before
``parse_args``).
"""

# pylint: disable=duplicate-code  # _dispatch mirrors seer.repo.__main__ by design

from __future__ import annotations

import argparse
import sys

from seer import __version__
from seer.cli._errors import EXIT_USER_ERROR, SeerError
from seer.cli._output import emit_error


class _SeerArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that routes errors through :func:`emit_error`."""

    _json_hint: bool = False

    def error(self, message: str) -> None:  # type: ignore[override]
        err = SeerError(
            code=EXIT_USER_ERROR,
            message=message,
            remediation=f"run '{self.prog} --help' to see valid arguments",
        )
        emit_error(err, json_mode=type(self)._json_hint)
        raise SystemExit(err.code)


def _argv_has_json(argv: list[str] | None) -> bool:
    tokens = argv if argv is not None else sys.argv[1:]
    return any(t == "--json" or t.startswith("--json=") for t in tokens)


def _build_parser() -> argparse.ArgumentParser:
    parser = _SeerArgumentParser(
        prog="seer",
        description="seer — codebase lookup and indexing for agent skills (greenfield).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", parser_class=_SeerArgumentParser)

    # pylint: disable=import-outside-toplevel
    from seer.cli._commands import classify as _classify_cmd
    from seer.cli._commands import explain as _explain_cmd
    from seer.cli._commands import grep as _grep_cmd
    from seer.cli._commands import learn as _learn_cmd
    from seer.cli._commands import recent as _recent_cmd
    from seer.cli._commands import whoami as _whoami_cmd

    # pylint: enable=import-outside-toplevel

    _learn_cmd.register(sub)
    _explain_cmd.register(sub)
    _whoami_cmd.register(sub)
    _classify_cmd.register(sub)
    _grep_cmd.register(sub)
    _recent_cmd.register(sub)

    return parser


def _dispatch(args: argparse.Namespace) -> int:  # pylint: disable=duplicate-code
    """Invoke the registered handler and translate exceptions to exit codes.

    A handler may return ``None`` (treated as success, exit 0) or an ``int``
    used directly as the exit code. Failures MUST raise :class:`SeerError`;
    any other exception is wrapped so no Python traceback leaks.
    """
    json_mode = bool(getattr(args, "json", False))
    try:
        rc = args.func(args)
    except SeerError as err:
        emit_error(err, json_mode=json_mode)
        return err.code
    except Exception as err:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        wrapped = SeerError(
            code=EXIT_USER_ERROR,
            message=f"unexpected: {err.__class__.__name__}: {err}",
            remediation="file a bug at https://github.com/agentculture/seer-cli/issues",
        )
        emit_error(wrapped, json_mode=json_mode)
        return wrapped.code
    return rc if rc is not None else 0


def main(argv: list[str] | None = None) -> int:
    """Parse *argv* (defaults to ``sys.argv[1:]``) and dispatch to a verb handler."""
    _SeerArgumentParser._json_hint = _argv_has_json(argv)  # pylint: disable=protected-access
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    return _dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
