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


def _is_closed(fp: Path) -> bool:
    """True if the JSONL's last record is a ``subagent_stop`` event.

    A subagent's JSONL is considered closed once SubagentStop has appended
    its terminal record. PostToolUse must not append further events to a
    closed file — otherwise unrelated tool calls in the same Claude Code
    session leak into the completed subagent's log.
    """
    try:
        lines = fp.read_text(encoding="utf-8").splitlines()
    except OSError:
        return True  # unreadable -> treat as closed; don't append.
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            return True  # malformed tail -> don't append more.
        return rec.get("event") == "subagent_stop"
    return False  # empty file (shouldn't happen) -> not closed.


def _find_open_subagent(run_id: str, session_id: str) -> Path | None:
    """Return the raw JSONL of the most-recent *open* pre_tool for this session.

    Skips files that are already closed (their last record is
    ``subagent_stop``). Returns None if no open match (e.g. a top-level
    operator call, or all matching subagents have completed).
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
        if rec.get("event") != "pre_tool":
            continue
        if rec.get("session_id") != session_id:
            continue
        if _is_closed(fp):
            continue
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
