"""Tests for trial.py — operator-driven per-trial bookkeeping.

Replaces capture.py + the SubagentStop hook. The end command extracts
the entire cell from the subagent sidechain transcript (real CC schema),
so the fixture is a sanitized real sidechain rather than a hand-crafted
mock — that's the lesson from the previous broken fixture.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.scripts_eval import trial

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SIDECHAIN = FIXTURE_DIR / "sidechain_min.jsonl"
SESSION = "test-session-1"


@pytest.fixture
def staged(tmp_path, monkeypatch):
    """REPO_ROOT, CLAUDE_PROJECTS_DIR, and CLAUDE_CODE_SESSION_ID all redirected to tmp_path."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_root = tmp_path / "claude_projects"
    projects_root.mkdir()
    monkeypatch.setattr(trial._io, "REPO_ROOT", repo_root)
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects_root))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION)
    return SimpleNamespace(
        tmp_path=tmp_path,
        repo_root=repo_root,
        projects_root=projects_root,
    )


def _stage_sidechain(staged, agent_id="testagent", session=SESSION):
    """Copy the fixture into the staged session's subagents dir, return the path."""
    encoded = str(staged.repo_root).replace("/", "-")
    sub_dir = staged.projects_root / encoded / session / "subagents"
    sub_dir.mkdir(parents=True, exist_ok=True)
    dest = sub_dir / f"agent-{agent_id}.jsonl"
    shutil.copy(SIDECHAIN, dest)
    return dest


def _make_start_args(run="r1", arm="A", target="agtag", question="q-profile-overview", trial_n=1):
    return SimpleNamespace(
        cmd="start", run=run, arm=arm, target=target, question=question, trial=trial_n
    )


def _make_end_args(trial_id):
    return SimpleNamespace(cmd="end", trial_id=trial_id)


def _cell_path(staged, run="r1", arm="A", slug="agtag-q-profile-overview-t1"):
    return (
        staged.repo_root
        / "experiments"
        / "scripts_eval"
        / "results"
        / run
        / f"arm-{arm}"
        / f"{slug}.json"
    )


def _in_flight_dir(staged, run="r1"):
    return staged.repo_root / "experiments" / "scripts_eval" / "results" / run / ".in_flight"


# --- start ---


def test_start_writes_in_flight_with_session_id_and_start_time(staged):
    rc = trial.cmd_start(_make_start_args())
    assert rc == 0

    files = list(_in_flight_dir(staged).glob("*.json"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["session_id"] == SESSION
    assert rec["run_id"] == "r1"
    assert rec["arm"] == "A"
    assert rec["repo_id"] == "agtag"
    assert rec["question_id"] == "q-profile-overview"
    assert rec["trial"] == 1
    assert isinstance(rec["start_time"], float)
    assert rec["trial_id"] == "r1/A/agtag-q-profile-overview-t1"


def test_start_prints_trial_id_to_stdout(staged, capsys):
    rc = trial.cmd_start(_make_start_args())
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "r1/A/agtag-q-profile-overview-t1"


def test_start_idempotent_does_not_overwrite_start_time(staged):
    args = _make_start_args()
    rc1 = trial.cmd_start(args)
    assert rc1 == 0
    rec1 = json.loads(list(_in_flight_dir(staged).glob("*.json"))[0].read_text())

    time.sleep(0.01)
    rc2 = trial.cmd_start(args)
    assert rc2 == 0

    files = list(_in_flight_dir(staged).glob("*.json"))
    assert len(files) == 1
    rec2 = json.loads(files[0].read_text())
    assert rec1["start_time"] == rec2["start_time"]


def test_start_workspace_scope_uses_workspace_slug(staged):
    args = _make_start_args(target=None, question="q-graph-workspace")
    rc = trial.cmd_start(args)
    assert rc == 0

    files = list(_in_flight_dir(staged).glob("*.json"))
    assert files[0].name == "_workspace_-q-graph-workspace-t1.json"
    rec = json.loads(files[0].read_text())
    assert rec["repo_id"] is None


def test_start_errors_without_session_id(staged, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    rc = trial.cmd_start(_make_start_args())
    assert rc == 2


# --- end ---


def test_end_finds_sidechain_and_writes_cell(staged):
    trial.cmd_start(_make_start_args())
    time.sleep(0.05)
    _stage_sidechain(staged, "abc12345")

    rc = trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))
    assert rc == 0
    assert _cell_path(staged).exists()


def test_end_extracts_model_from_last_assistant(staged):
    trial.cmd_start(_make_start_args())
    time.sleep(0.05)
    _stage_sidechain(staged)
    trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))

    cell = json.loads(_cell_path(staged).read_text())
    # Fixture's last assistant used Haiku 4.5
    assert cell["subagent"]["model"] == "claude-haiku-4-5-20251001"


def test_end_sums_usage_across_assistant_turns(staged):
    trial.cmd_start(_make_start_args())
    time.sleep(0.05)
    _stage_sidechain(staged)
    trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))

    cell = json.loads(_cell_path(staged).read_text())
    tokens = cell["subagent"]["tokens"]
    assert tokens["input"] > 0
    assert tokens["output"] > 0
    assert set(tokens.keys()) == {"input", "output", "cache_read", "cache_creation"}


def test_end_counts_tools_used_from_tool_use_blocks(staged):
    trial.cmd_start(_make_start_args())
    time.sleep(0.05)
    _stage_sidechain(staged)
    trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))

    cell = json.loads(_cell_path(staged).read_text())
    counts = {t["name"]: t["count"] for t in cell["subagent"]["tools_used"]}
    # Fixture-derived ground truth (counted directly from the sidechain)
    assert counts.get("Bash") == 17
    assert counts.get("Read") == 13


def test_end_computes_duration_from_last_iso_timestamp(staged):
    trial.cmd_start(_make_start_args())
    # Manually fast-forward by editing in-flight record to set a very low
    # start_time so duration is deterministic (positive, irrespective of clock)
    fp = list(_in_flight_dir(staged).glob("*.json"))[0]
    rec = json.loads(fp.read_text())
    rec["start_time"] = 0.0
    fp.write_text(json.dumps(rec, indent=2) + "\n")

    _stage_sidechain(staged)
    trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))

    cell = json.loads(_cell_path(staged).read_text())
    duration = cell["subagent"]["duration_seconds"]
    assert duration is not None
    # The fixture's last ISO timestamp is 2026-05-15T15:28:39.811Z ≈ epoch 1778858920
    assert duration > 1_700_000_000


def test_end_extracts_answer_text_from_last_text_block(staged):
    trial.cmd_start(_make_start_args())
    time.sleep(0.05)
    _stage_sidechain(staged)
    trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))

    cell = json.loads(_cell_path(staged).read_text())
    assert cell["answer_text"]
    # Real agtag overview content survived sanitization (specific spelling
    # of "agtag" is intact, paths replaced with /tmp/agtag etc.)
    assert "agtag" in cell["answer_text"].lower()


def test_end_removes_in_flight_on_success(staged):
    trial.cmd_start(_make_start_args())
    time.sleep(0.05)
    _stage_sidechain(staged)
    trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))

    assert list(_in_flight_dir(staged).glob("*.json")) == []


def test_end_errors_when_no_sidechain_found(staged):
    trial.cmd_start(_make_start_args())
    # No sidechain staged
    rc = trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))
    assert rc == 1
    # In-flight remains so the operator can retry once the sidechain appears
    assert list(_in_flight_dir(staged).glob("*.json"))


def test_end_skips_sidechain_with_mtime_before_start(staged):
    """A stale sidechain (from a prior trial) must not be picked up."""
    stale = _stage_sidechain(staged, "stale")
    # Force mtime well before the start_time we're about to record
    os.utime(stale, (1_700_000_000, 1_700_000_000))

    trial.cmd_start(_make_start_args())
    rc = trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))
    # No sidechain newer than start_time → 1
    assert rc == 1


def test_end_errors_with_malformed_trial_id(staged):
    rc = trial.cmd_end(_make_end_args("not-a-real-id"))
    assert rc == 2


def test_end_writes_cell_with_full_schema(staged):
    trial.cmd_start(_make_start_args())
    time.sleep(0.05)
    _stage_sidechain(staged)
    trial.cmd_end(_make_end_args("r1/A/agtag-q-profile-overview-t1"))

    cell = json.loads(_cell_path(staged).read_text())
    assert set(cell.keys()) == {
        "run_id",
        "arm",
        "repo_id",
        "question_id",
        "trial",
        "subagent",
        "question_text",
        "answer_text",
        "validation",
        "judge",
    }
    assert set(cell["subagent"].keys()) == {
        "agent_type",
        "model",
        "duration_seconds",
        "tokens",
        "tools_used",
    }
    assert set(cell["subagent"]["tokens"].keys()) == {
        "input",
        "output",
        "cache_read",
        "cache_creation",
    }
    # validation + judge filled by separate commands; trial.py leaves them None
    assert cell["validation"] is None
    assert cell["judge"] is None
