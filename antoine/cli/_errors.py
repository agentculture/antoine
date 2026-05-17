"""AntoineError and exit-code policy.

Every failure inside antoine raises :class:`AntoineError`. The top-level
``main()`` catches it, formats via :mod:`antoine.cli._output`, and exits with
:attr:`AntoineError.code`. This centralises the exit-code policy and guarantees
no Python traceback leaks to stderr.
"""

from __future__ import annotations

from dataclasses import dataclass

# Exit-code policy:
#   0  = success
#   1  = user-input error (bad flag, missing required arg, unknown path)
#   2  = environment / setup error (tool not installed, file unreadable)
#   3  = internal bug (uncaught exception wrapped by _dispatch)
#   4+ = reserved for future categorisation
EXIT_SUCCESS = 0
EXIT_USER_ERROR = 1
EXIT_ENV_ERROR = 2
EXIT_INTERNAL = 3


@dataclass
class AntoineError(Exception):
    """Structured error raised within antoine.

    Fields:
      code:        exit code (see constants above)
      message:     one-sentence plain-English description of what went wrong
      remediation: optional concrete next step for the user/agent
      reason:      optional root-cause sentence (what was tried, why it failed)
      kind:        optional short tag — "user_error" | "env_error" | "bug"

    Renderers (:func:`antoine.cli._output.emit_error`) skip empty optional
    fields so older call sites that only set code+message+remediation keep
    producing the same output.
    """

    code: int
    message: str
    remediation: str = ""
    reason: str = ""
    kind: str = ""

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, object]:
        """Serialise to a plain dict suitable for JSON output."""
        out: dict[str, object] = {"code": self.code, "message": self.message}
        if self.kind:
            out["kind"] = self.kind
        if self.reason:
            out["reason"] = self.reason
        if self.remediation:
            out["remediation"] = self.remediation
        return out
