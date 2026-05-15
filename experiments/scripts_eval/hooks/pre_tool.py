#!/usr/bin/env python3
"""PreToolUse hook: stamps Agent dispatches into the run's raw/ JSONL.

No-op when SEER_EVAL_RUN_ID is unset, so day-to-day seer-cli sessions
are unaffected. Each Agent dispatch becomes one JSONL file under
results/<run_id>/raw/<subagent_id>.jsonl with a single 'pre_tool' line;
PostToolUse and SubagentStop append to the same file.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Callable

from experiments.scripts_eval import _io


def _subagent_id(run_id: str, arm: str) -> str:
    """Synthesise a unique id for this subagent dispatch."""
    return f"{run_id}-{arm}-{uuid.uuid4().hex[:8]}"


def run(payload: dict, now: Callable[[], float] = time.time) -> int:
    run_id = _io.eval_run_id()
    if not run_id:
        return 0
    if payload.get("tool_name") != "Agent":
        return 0
    tool_input = payload.get("tool_input", {}) or {}
    description = tool_input.get("description") or ""
    # Skip judge subagent dispatches so they don't pollute raw/ — capture.py
    # picks the oldest-mtime *.jsonl regardless of origin, and an orphan
    # judge file would risk being consumed as the wrong tester cell.
    if description.startswith("scripts_eval judge:"):
        return 0
    arm = _io.eval_arm()
    if arm is None:
        print(
            "scripts-eval pre_tool: SEER_EVAL_RUN_ID is set but SEER_EVAL_ARM is not; "
            "skipping (export SEER_EVAL_ARM=A or C)",
            file=sys.stderr,
        )
        return 0
    sid = _subagent_id(run_id, arm)
    record = {
        "event": "pre_tool",
        "subagent_id": sid,
        "run_id": run_id,
        "arm": arm,
        "session_id": payload.get("session_id"),
        "transcript_path": payload.get("transcript_path"),
        "agent_type": tool_input.get("subagent_type"),
        "description": tool_input.get("description"),
        "prompt": tool_input.get("prompt"),
        "start_time": now(),
    }
    out_path = _io.raw_dir(run_id) / f"{sid}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record) + "\n")
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    return run(payload)


if __name__ == "__main__":
    sys.exit(main())
