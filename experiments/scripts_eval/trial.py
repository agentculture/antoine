"""trial.py — operator-driven per-trial bookkeeping.

Replaces capture.py and the SubagentStop hook. Operator calls
``trial start`` before dispatching the Agent, then ``trial end`` after
the Agent's final-text result returns:

  python -m experiments.scripts_eval.trial start \\
      --run <id> --arm <A|C> --target <id> --question <qid> --trial <n>

  python -m experiments.scripts_eval.trial end --trial-id <id>

``start`` reads ``CLAUDE_CODE_SESSION_ID`` from env, records
``start_time`` and ``session_id`` to
``results/<run>/.in_flight/<arm>-<slug>.json``, and prints the
``trial_id`` (of the form ``<run>/<arm>/<slug>``) to stdout. The arm
is embedded in the in-flight filename so the same ``(target,
question, trial)`` triple can be in flight under both arms
simultaneously without colliding.

``end`` reads the in-flight record; finds the newest ``agent-*.jsonl``
under ``<CLAUDE_PROJECTS_DIR>/<encoded_cwd>/<session_id>/subagents/``
with mtime greater than ``start_time``; extracts model, usage,
``tools_used``, duration, and ``answer_text`` from it; writes the cell
JSON to ``results/<run>/arm-<arm>/<slug>.json``; and removes the
in-flight record.

The cell schema matches what the prior ``capture.py`` produced; downstream
``validate.py``, ``judge.py``, and ``summarize.py`` consume cells unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from experiments.scripts_eval import _io

# --- env-var indirection (tests override via CLAUDE_PROJECTS_DIR) ---


def _projects_root() -> Path:
    """CC's projects root directory; tests override via CLAUDE_PROJECTS_DIR."""
    val = os.environ.get("CLAUDE_PROJECTS_DIR")
    if val:
        return Path(val)
    return Path.home() / ".claude" / "projects"


def _encode_cwd(path: Path) -> str:
    """Encode an absolute path the way CC encodes projects subdirs: /a/b → -a-b."""
    return str(path).replace("/", "-")


def _session_id() -> str | None:
    """Return the operator's CC session id from env, or None if unset."""
    val = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return val if val else None


# --- path helpers ---


def _trial_slug(target: str | None, question: str, trial_n: int) -> str:
    """Filesystem-safe slug for a (target, question, trial) triple."""
    suffix = target or "_workspace_"
    return f"{suffix}-{question}-t{trial_n}"


def _trial_id(run_id: str, arm: str, slug: str) -> str:
    """Composite id passed to ``trial end`` to identify an in-flight trial."""
    return f"{run_id}/{arm}/{slug}"


def _in_flight_dir(run_id: str) -> Path:
    return _io.run_dir(run_id) / ".in_flight"


def _in_flight_path(run_id: str, arm: str, slug: str) -> Path:
    """In-flight record path. The arm is part of the filename so that
    starting the same ``(target, question, trial)`` under both arms
    yields two distinct records."""
    return _in_flight_dir(run_id) / f"{arm}-{slug}.json"


def _sidechain_dir(session_id: str) -> Path:
    """Path to the CC subagents/ directory for this operator's session."""
    encoded = _encode_cwd(_io.REPO_ROOT)
    return _projects_root() / encoded / session_id / "subagents"


# --- start ---


def cmd_start(args) -> int:
    session_id = _session_id()
    if not session_id:
        print(
            "trial start: CLAUDE_CODE_SESSION_ID env var not set; "
            "trial start must run inside a Claude Code session.",
            file=sys.stderr,
        )
        return 2
    slug = _trial_slug(args.target, args.question, args.trial)
    fp = _in_flight_path(args.run, args.arm, slug)
    if fp.exists():
        # Idempotent re-call: keep the existing record (preserve start_time).
        # The path already encodes arm + slug, so the only way a mismatch
        # surfaces here is via a hand-edited / corrupted record — refuse
        # rather than silently overwrite.
        record = json.loads(fp.read_text(encoding="utf-8"))
        expected = {
            "run_id": args.run,
            "arm": args.arm,
            "repo_id": args.target,
            "question_id": args.question,
            "trial": args.trial,
        }
        for k, v in expected.items():
            if record.get(k) != v:
                print(
                    f"trial start: in-flight record at {fp} has {k}={record.get(k)!r}, "
                    f"but args have {k}={v!r}. Remove the stale record before retrying.",
                    file=sys.stderr,
                )
                return 2
    else:
        record = {
            "trial_id": _trial_id(args.run, args.arm, slug),
            "run_id": args.run,
            "arm": args.arm,
            "repo_id": args.target,
            "question_id": args.question,
            "trial": args.trial,
            "session_id": session_id,
            "start_time": time.time(),
        }
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(record["trial_id"])
    return 0


# --- extraction (pure; shared with backfill.py) ---


def _iso_to_epoch(s: str) -> float:
    """ISO 8601 → epoch float. Accepts trailing 'Z'."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def _extract_cell_from_sidechain(sidechain: Path, *, in_flight: dict) -> dict:
    """Read a sidechain JSONL, return a cell dict matching capture.py's schema.

    Pure function (no I/O writes). Shared with ``backfill.py``.
    """
    assistants: list[dict] = []
    for line in sidechain.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if entry.get("type") == "assistant":
            assistants.append(entry)
    if not assistants:
        raise ValueError(f"no assistant entries in {sidechain}")

    last = assistants[-1]
    msg = last.get("message", {}) or {}

    # Model: last assistant's model
    model = msg.get("model")

    # Usage: sum across all assistant turns. Subagents can be cache hits
    # at startup; later turns may have zero input but non-zero output.
    sums = {k: 0 for k in _USAGE_KEYS}
    for a in assistants:
        u = (a.get("message", {}) or {}).get("usage", {}) or {}
        for k in _USAGE_KEYS:
            v = u.get(k)
            if isinstance(v, int):
                sums[k] += v
    tokens = {
        "input": sums["input_tokens"],
        "output": sums["output_tokens"],
        "cache_read": sums["cache_read_input_tokens"],
        "cache_creation": sums["cache_creation_input_tokens"],
    }

    # Duration: last assistant timestamp − in_flight.start_time
    duration: float | None = None
    last_ts = last.get("timestamp")
    start = in_flight.get("start_time")
    if last_ts and isinstance(start, (int, float)):
        try:
            duration = round(_iso_to_epoch(last_ts) - float(start), 3)
        except (ValueError, TypeError):
            duration = None

    # answer_text: last text block in the final assistant's content
    answer_text = ""
    for block in reversed(msg.get("content", []) or []):
        if block.get("type") == "text" and block.get("text"):
            answer_text = block["text"]
            break

    # tools_used: count tool_use blocks; record per-tool patterns (first
    # useful input string, capped at 200 chars and 10 patterns/tool).
    tool_counts: Counter = Counter()
    tool_patterns: dict[str, list[str]] = {}
    for a in assistants:
        for block in (a.get("message", {}) or {}).get("content", []) or []:
            if block.get("type") != "tool_use":
                continue
            name = block.get("name") or "Unknown"
            tool_counts[name] += 1
            inp = block.get("input", {}) or {}
            for key in ("command", "file_path", "pattern", "prompt", "url"):
                v = inp.get(key)
                if isinstance(v, str):
                    tool_patterns.setdefault(name, []).append(v[:200])
                    break
    tools_used = [
        {
            "name": name,
            "count": count,
            "patterns": tool_patterns.get(name, [])[:10],
        }
        for name, count in sorted(tool_counts.items())
    ]

    return {
        "run_id": in_flight["run_id"],
        "arm": in_flight["arm"],
        "repo_id": in_flight.get("repo_id"),
        "question_id": in_flight["question_id"],
        "trial": in_flight["trial"],
        "subagent": {
            "agent_type": in_flight.get("agent_type", "Explore"),
            "model": model,
            "duration_seconds": duration,
            "tokens": tokens,
            "tools_used": tools_used,
        },
        "question_text": in_flight.get("question_text", ""),
        "answer_text": answer_text,
        "validation": None,
        "judge": None,
    }


def _find_sidechain(in_flight: dict) -> Path | None:
    """Find the newest agent-*.jsonl with mtime > in_flight['start_time']."""
    sub_dir = _sidechain_dir(in_flight["session_id"])
    if not sub_dir.exists():
        return None
    start = float(in_flight["start_time"])
    candidates: list[tuple[float, Path]] = []
    for fp in sub_dir.glob("agent-*.jsonl"):
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            continue
        if mtime <= start:
            continue
        candidates.append((mtime, fp))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


# --- end ---


def cmd_end(args) -> int:
    parts = args.trial_id.split("/", 2)
    if len(parts) != 3:
        print(
            f"trial end: invalid trial_id {args.trial_id!r}; " "expected <run>/<arm>/<slug>",
            file=sys.stderr,
        )
        return 2
    run_id, arm, slug = parts
    fp = _in_flight_path(run_id, arm, slug)
    if not fp.exists():
        print(f"trial end: no in-flight record at {fp}", file=sys.stderr)
        return 1
    in_flight = json.loads(fp.read_text(encoding="utf-8"))

    # Defensive: the filename already pins arm, but a hand-edited record
    # could disagree with its container. Refuse rather than misfile.
    if in_flight.get("arm") != arm:
        print(
            f"trial end: in-flight arm {in_flight.get('arm')!r} does not match "
            f"trial-id arm {arm!r}; refusing to write cell.",
            file=sys.stderr,
        )
        return 2

    sidechain = _find_sidechain(in_flight)
    if sidechain is None:
        print(
            f"trial end: no agent-*.jsonl under {_sidechain_dir(in_flight['session_id'])} "
            f"with mtime > start_time {in_flight['start_time']}",
            file=sys.stderr,
        )
        return 1

    cell = _extract_cell_from_sidechain(sidechain, in_flight=in_flight)

    out_path = _io.arm_dir(run_id, arm) / f"{slug}.json"
    _io.write_json(out_path, cell)

    fp.unlink()
    print(f"trial end: wrote {out_path}")
    return 0


# --- CLI ---


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trial")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="record start_time + session_id before Agent dispatch")
    s.add_argument("--run", required=True)
    s.add_argument("--arm", required=True, choices=["A", "C"])
    s.add_argument(
        "--target",
        default=None,
        help="repo target id from corpus.yaml; omit for workspace-scope questions",
    )
    s.add_argument("--question", required=True)
    s.add_argument("--trial", type=int, required=True)

    e = sub.add_parser("end", help="read sidechain, write cell JSON, remove in-flight")
    e.add_argument("--trial-id", required=True, dest="trial_id")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "start":
        return cmd_start(args)
    if args.cmd == "end":
        return cmd_end(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
