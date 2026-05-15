#!/usr/bin/env python3
"""SubagentStop hook: finalises the subagent's raw JSONL.

Reads the transcript path from the payload, finds the assistant
message(s) belonging to this subagent (by start_time stamped in
pre_tool), extracts the last usage block, and appends one
'subagent_stop' record with duration, model, usage, final_text.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable

from experiments.scripts_eval import _io


def _find_pre_record(run_id: str, session_id: str) -> tuple[Path, dict] | None:
    """Locate this subagent's raw JSONL + its pre_tool record."""
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
            matches.append((fp.stat().st_mtime, fp, rec))
    if not matches:
        return None
    matches.sort()
    _, fp, rec = matches[-1]
    return fp, rec


def _last_assistant_after(transcript_path: Path, start_time: float) -> dict | None:
    """Return the last assistant message with ts > start_time, or None."""
    if not transcript_path.exists():
        return None
    last = None
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        ts = entry.get("ts")
        if ts is None or ts <= start_time:
            continue
        last = entry
    return last


def run(payload: dict, now: Callable[[], float] = time.time) -> int:
    run_id = _io.eval_run_id()
    if not run_id:
        return 0
    session_id = payload.get("session_id")
    transcript_path = Path(payload.get("transcript_path") or "")
    if not session_id or not str(transcript_path):
        return 0
    found = _find_pre_record(run_id, session_id)
    if found is None:
        return 0
    fp, pre = found
    start_time = float(pre.get("start_time", 0.0))
    end_time = now()
    last = _last_assistant_after(transcript_path, start_time)
    record = {
        "event": "subagent_stop",
        "end_time": end_time,
        "duration_seconds": round(end_time - start_time, 3),
        "model": (last or {}).get("model"),
        "usage": (last or {}).get("usage", {}),
        "final_text": (last or {}).get("content", ""),
    }
    with fp.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    return run(payload)


if __name__ == "__main__":
    sys.exit(main())
