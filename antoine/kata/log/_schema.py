"""LogEntry — the JSONL row written by an adapter per captured tool call.

The schema is documented in:
  docs/kata/log-schema.md  (added in a later task in this plan)

This module is pure data + serialization; it owns no IO.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from typing import Any

_REQUIRED = ("ts", "session", "agent", "tool", "args_digest")


@dataclass(frozen=True)
class LogEntry:
    """One captured tool call.

    Required fields (always present): ts, session, agent, tool, args_digest.
    Optional fields (None if the adapter could not provide them):
    bash_argv0, tokens_in, tokens_out, duration_ms.
    """

    ts: str
    session: str
    agent: str
    tool: str
    args_digest: str
    bash_argv0: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.args_digest.startswith("sha256:"):
            raise ValueError(
                "args_digest must start with 'sha256:' " f"(got: {self.args_digest!r})"
            )

    def to_json_line(self) -> str:
        """Return a single newline-terminated JSON object."""
        payload = asdict(self)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    @classmethod
    def from_json_line(cls, line: str) -> "LogEntry":
        """Parse one JSONL row. Raises ValueError on missing required fields.

        Unknown fields in ``payload`` are silently dropped — adapters may emit
        future-evolved schemas, and tolerating that keeps log ingestion working
        instead of TypeError-ing through ``cls(**payload)``. Forward-compat is
        part of the "antoine never crashes" contract.
        """
        payload: dict[str, Any] = json.loads(line)
        for field_name in _REQUIRED:
            if field_name not in payload:
                raise ValueError(f"missing required field: {field_name!r}")
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in known})
