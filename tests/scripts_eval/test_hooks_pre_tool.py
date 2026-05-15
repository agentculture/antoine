"""Tests for the PreToolUse hook (Agent dispatch start)."""

from __future__ import annotations

import json

from experiments.scripts_eval.hooks import pre_tool


def _payload(tool_name="Agent", prompt="explain X"):
    return {
        "session_id": "sess-abc",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/home/spark/git/seer-cli",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {
            "subagent_type": "Explore",
            "description": "test cell",
            "prompt": prompt,
        },
    }


def test_no_op_when_run_id_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("SEER_EVAL_RUN_ID", raising=False)
    monkeypatch.setattr(pre_tool._io, "REPO_ROOT", tmp_path)
    rc = pre_tool.run(_payload(), now=lambda: 1700000000.0)
    assert rc == 0
    raw = tmp_path / "experiments" / "scripts_eval" / "results"
    assert not raw.exists()  # nothing written


def test_no_op_when_tool_not_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "A")
    monkeypatch.setattr(pre_tool._io, "REPO_ROOT", tmp_path)
    rc = pre_tool.run(_payload(tool_name="Bash"), now=lambda: 1700000000.0)
    assert rc == 0
    assert not (tmp_path / "experiments" / "scripts_eval" / "results" / "r1").exists()


def test_writes_jsonl_for_agent_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "C")
    monkeypatch.setattr(pre_tool._io, "REPO_ROOT", tmp_path)

    rc = pre_tool.run(_payload(prompt="overview the culture repo"), now=lambda: 1700000000.0)
    assert rc == 0
    raw_dir = tmp_path / "experiments" / "scripts_eval" / "results" / "r1" / "raw"
    files = sorted(raw_dir.glob("*.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text().splitlines()[0])
    assert line["event"] == "pre_tool"
    assert line["arm"] == "C"
    assert line["run_id"] == "r1"
    assert line["agent_type"] == "Explore"
    assert line["prompt"] == "overview the culture repo"
    assert line["start_time"] == 1700000000.0


def test_warns_and_skips_when_arm_unset(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.delenv("SEER_EVAL_ARM", raising=False)
    monkeypatch.setattr(pre_tool._io, "REPO_ROOT", tmp_path)
    rc = pre_tool.run(_payload(), now=lambda: 1700000000.0)
    assert rc == 0
    captured = capsys.readouterr()
    assert "SEER_EVAL_ARM" in captured.err
    assert not (tmp_path / "experiments" / "scripts_eval" / "results").exists()
