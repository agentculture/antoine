"""Tests for the SubagentStop hook."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from experiments.scripts_eval.hooks import subagent_stop

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _seed_pre(tmp_path, sid, session_id, transcript_path, start_time=1700000000.0):
    raw = tmp_path / "experiments" / "scripts_eval" / "results" / "r1" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    fp = raw / f"{sid}.jsonl"
    fp.write_text(
        json.dumps(
            {
                "event": "pre_tool",
                "subagent_id": sid,
                "run_id": "r1",
                "session_id": session_id,
                "transcript_path": str(transcript_path),
                "start_time": start_time,
            }
        )
        + "\n"
    )
    return fp


def test_no_op_when_run_id_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("SEER_EVAL_RUN_ID", raising=False)
    monkeypatch.setattr(subagent_stop._io, "REPO_ROOT", tmp_path)
    rc = subagent_stop.run(
        {"session_id": "x", "transcript_path": "/tmp/t"}, now=lambda: 1700000060.0
    )
    assert rc == 0


def test_appends_stop_record_with_duration_model_usage(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "A")
    monkeypatch.setattr(subagent_stop._io, "REPO_ROOT", tmp_path)

    transcript = tmp_path / "transcript.jsonl"
    shutil.copy(FIXTURE_DIR / "transcript_min.jsonl", transcript)

    sid = "r1-A-feedface"
    fp = _seed_pre(tmp_path, sid, "sess-1", transcript, start_time=1700000005.0)

    rc = subagent_stop.run(
        {"session_id": "sess-1", "transcript_path": str(transcript)},
        now=lambda: 1700000060.0,
    )
    assert rc == 0

    lines = fp.read_text().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[1])
    assert rec["event"] == "subagent_stop"
    assert rec["model"] == "claude-opus-4-7"
    assert rec["usage"]["input_tokens"] == 1200
    assert rec["usage"]["output_tokens"] == 340
    assert rec["usage"]["cache_read_input_tokens"] == 800
    assert rec["usage"]["cache_creation_input_tokens"] == 100
    assert rec["duration_seconds"] == 55.0
    assert "Here is the explanation" in rec["final_text"]


def test_no_pre_record_means_no_op(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setattr(subagent_stop._io, "REPO_ROOT", tmp_path)
    transcript = tmp_path / "t.jsonl"
    shutil.copy(FIXTURE_DIR / "transcript_min.jsonl", transcript)
    rc = subagent_stop.run(
        {"session_id": "no-such-session", "transcript_path": str(transcript)},
        now=lambda: 1700000060.0,
    )
    assert rc == 0


def test_does_not_pick_up_assistant_messages_after_end_time(monkeypatch, tmp_path):
    """The transcript window is [start_time, end_time]. Assistant entries
    with ts > end_time belong to a later operator turn and must not be
    captured as this subagent's answer/usage."""
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "A")
    monkeypatch.setattr(subagent_stop._io, "REPO_ROOT", tmp_path)

    transcript = tmp_path / "transcript.jsonl"
    shutil.copy(FIXTURE_DIR / "transcript_with_late_msg.jsonl", transcript)

    sid = "r1-A-cafef00d"
    fp = _seed_pre(tmp_path, sid, "sess-1", transcript, start_time=1700000005.0)

    # end_time bounds the window at 1700000060; the late assistant at
    # ts=1700000080 must be excluded.
    rc = subagent_stop.run(
        {"session_id": "sess-1", "transcript_path": str(transcript)},
        now=lambda: 1700000060.0,
    )
    assert rc == 0

    rec = json.loads(fp.read_text().splitlines()[1])
    assert rec["event"] == "subagent_stop"
    # Picked the in-window assistant message, NOT the post-window one.
    assert rec["final_text"] == "the subagent's actual answer"
    assert rec["usage"]["input_tokens"] == 1200
    assert rec["usage"]["output_tokens"] == 340
