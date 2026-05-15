#!/usr/bin/env python3
"""PostToolUse hook: appends each subagent tool call to its raw JSONL.

Identifies the in-flight subagent by matching session_id against the
most-recent pre_tool record in the run's raw/ dir. If no pre_tool is
open (e.g. a top-level operator call), no-op.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable

from experiments.scripts_eval import _io

# Args-summary truncation limit (chars). Keeps logs readable; full args
# live in the transcript if a deep dive is needed.
ARGS_MAX_LEN = 200


def _summarise_args(tool_input: dict) -> str:
    """Compact one-line summary of a tool input dict."""
    if not isinstance(tool_input, dict):
        return ""
    # Common keys: command, file_path, pattern, prompt; fall back to repr.
    for key in ("command", "file_path", "pattern", "prompt", "url"):
        if key in tool_input and isinstance(tool_input[key], str):
            return tool_input[key][:ARGS_MAX_LEN]
    s = json.dumps(tool_input, separators=(",", ":"))
    return s[:ARGS_MAX_LEN]


def _find_open_subagent(run_id: str, session_id: str) -> Path | None:
    """Return the raw JSONL of the most-recent pre_tool with this session_id.

    Returns None if no match (this is a top-level call, not a subagent).
    """
    raw = _io.raw_dir(run_id)
    if not raw.exists():
        return None
    matches = []
    for fp in raw.glob("*.jsonl"):
        try:
            first = fp.read_text(encoding="utf-8").splitlines()[0]
            rec = json.loads(first)
        except (OSError, ValueError, IndexError):
            continue
        if rec.get("event") == "pre_tool" and rec.get("session_id") == session_id:
            matches.append((fp.stat().st_mtime, fp))
    if not matches:
        return None
    matches.sort()
    return matches[-1][1]


def run(payload: dict, now: Callable[[], float] = time.time) -> int:
    run_id = _io.eval_run_id()
    if not run_id:
        return 0
    session_id = payload.get("session_id")
    if not session_id:
        return 0
    fp = _find_open_subagent(run_id, session_id)
    if fp is None:
        return 0
    record = {
        "event": "post_tool",
        "tool_name": payload.get("tool_name"),
        "args_summary": _summarise_args(payload.get("tool_input", {})),
        "ts": now(),
    }
    with fp.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    return run(payload)


if __name__ == "__main__":
    sys.exit(main())
