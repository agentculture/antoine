"""Tests for the PostToolUse hook (per-tool log, only inside subagents)."""

from __future__ import annotations

import json

from experiments.scripts_eval.hooks import post_tool


def _payload(tool_name="Bash", session_id="sess-abc", input_=None):
    return {
        "session_id": session_id,
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/home/spark/git/seer-cli",
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": input_ or {"command": "ls"},
        "tool_response": {"stdout": "...", "exit_code": 0},
    }


def _seed_pre(tmp_path, sid, session_id="sess-abc"):
    """Drop a pre_tool jsonl line so post_tool can find it."""
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
            }
        )
        + "\n"
    )
    return fp


def test_no_op_when_run_id_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("SEER_EVAL_RUN_ID", raising=False)
    monkeypatch.setattr(post_tool._io, "REPO_ROOT", tmp_path)
    rc = post_tool.run(_payload(), now=lambda: 1700000010.0)
    assert rc == 0


def test_appends_to_open_subagent_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "C")
    monkeypatch.setattr(post_tool._io, "REPO_ROOT", tmp_path)
    sid = "r1-C-deadbeef"
    fp = _seed_pre(tmp_path, sid)

    rc = post_tool.run(
        _payload(tool_name="Bash", input_={"command": "scripts/profile.sh /tmp/x"}),
        now=lambda: 1700000010.0,
    )
    assert rc == 0
    lines = fp.read_text().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[1])
    assert record["event"] == "post_tool"
    assert record["tool_name"] == "Bash"
    assert "scripts/profile.sh" in record["args_summary"]
    assert record["ts"] == 1700000010.0


def test_no_open_subagent_means_no_op(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "A")
    monkeypatch.setattr(post_tool._io, "REPO_ROOT", tmp_path)
    rc = post_tool.run(_payload(), now=lambda: 1700000010.0)
    assert rc == 0  # silently skip; no raw dir, no file
