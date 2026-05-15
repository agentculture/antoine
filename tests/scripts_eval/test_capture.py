"""Tests for capture.py — rolls raw hook JSONL into per-cell JSON."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.scripts_eval import _io, capture


def _seed_raw(run_dir: Path, sid: str, lines: list[dict]) -> Path:
    raw = run_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    fp = raw / f"{sid}.jsonl"
    fp.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return fp


def test_capture_one_complete_subagent(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    run_id = "r1"
    rd = _io.run_dir(run_id)
    rd.mkdir(parents=True)
    sid = "r1-C-deadbeef"
    _seed_raw(
        rd,
        sid,
        [
            {
                "event": "pre_tool",
                "subagent_id": sid,
                "run_id": "r1",
                "arm": "C",
                "session_id": "sess-1",
                "agent_type": "Explore",
                "prompt": "overview the culture repo",
                "start_time": 1700000000.0,
            },
            {
                "event": "post_tool",
                "tool_name": "Bash",
                "args_summary": "scripts/profile.sh /tmp/x",
                "ts": 1700000005.0,
            },
            {
                "event": "post_tool",
                "tool_name": "Read",
                "args_summary": "/tmp/x/README.md",
                "ts": 1700000010.0,
            },
            {
                "event": "subagent_stop",
                "end_time": 1700000050.0,
                "duration_seconds": 50.0,
                "model": "claude-opus-4-7",
                "usage": {
                    "input_tokens": 1200,
                    "output_tokens": 340,
                    "cache_read_input_tokens": 800,
                    "cache_creation_input_tokens": 100,
                },
                "final_text": "answer text",
            },
        ],
    )
    cells = capture.process_run(
        run_id, repo_id="culture", question_id="q-profile-overview", trial=1
    )
    # process_run picks up unprocessed raw files and assigns them in order
    assert len(cells) == 1
    cell = cells[0]
    assert cell["arm"] == "C"
    assert cell["repo_id"] == "culture"
    assert cell["question_id"] == "q-profile-overview"
    assert cell["trial"] == 1
    assert cell["subagent"]["model"] == "claude-opus-4-7"
    assert cell["subagent"]["duration_seconds"] == 50.0
    assert cell["subagent"]["tokens"]["input"] == 1200
    tools = {t["name"]: t for t in cell["subagent"]["tools_used"]}
    assert tools["Bash"]["count"] == 1
    assert tools["Read"]["count"] == 1
    assert any("scripts/profile.sh" in p for p in tools["Bash"]["patterns"])
    assert cell["question_text"] == "overview the culture repo"
    assert cell["answer_text"] == "answer text"

    # Per-cell JSON written under arm-C/
    written = list((rd / "arm-C").glob("*.json"))
    assert len(written) == 1


def test_capture_skips_incomplete_subagent(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    run_id = "r1"
    rd = _io.run_dir(run_id)
    rd.mkdir(parents=True)
    sid = "r1-A-incomplete"
    # Pre + post only, no stop yet.
    _seed_raw(
        rd,
        sid,
        [
            {
                "event": "pre_tool",
                "subagent_id": sid,
                "run_id": "r1",
                "arm": "A",
                "session_id": "x",
                "agent_type": "Explore",
                "prompt": "p",
                "start_time": 1.0,
            },
            {"event": "post_tool", "tool_name": "Read", "args_summary": "/tmp/x", "ts": 2.0},
        ],
    )
    cells = capture.process_run(run_id, repo_id="culture", question_id="q1", trial=1)
    assert cells == []  # incomplete: skipped, will be picked up next pass
