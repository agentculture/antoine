"""Tests for backfill.py — focused on the corpus-aware
``(arm, target, question, trial)`` identification that disambiguates
sidechains across multiple cells in a round.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.scripts_eval import backfill
from experiments.scripts_eval import corpus as corpus_module

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SIDECHAIN = FIXTURE_DIR / "sidechain_min.jsonl"
CORPUS_MIN = FIXTURE_DIR / "corpus_minimal.yaml"


@pytest.fixture
def corpus_min():
    return corpus_module.load(CORPUS_MIN)


# --- _first_user_content ---


def test_first_user_content_extracts_string_form(tmp_path):
    fp = tmp_path / "side.jsonl"
    fp.write_text(
        json.dumps({"type": "user", "message": {"content": "Hello, agent!"}}) + "\n",
        encoding="utf-8",
    )
    assert backfill._first_user_content(fp) == "Hello, agent!"


def test_first_user_content_extracts_block_list_form(tmp_path):
    fp = tmp_path / "side.jsonl"
    fp.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "text", "text": "Overview the repo at"},
                        {"type": "text", "text": "/home/spark/git/culture."},
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = backfill._first_user_content(fp)
    assert "Overview the repo at" in out
    assert "/home/spark/git/culture." in out


def test_first_user_content_returns_none_when_no_user_entry(tmp_path):
    fp = tmp_path / "side.jsonl"
    fp.write_text(
        json.dumps({"type": "assistant", "message": {"content": "x"}}) + "\n",
        encoding="utf-8",
    )
    assert backfill._first_user_content(fp) is None


def test_first_user_content_skips_assistant_before_user(tmp_path):
    """Skip non-user lines until the first user entry is reached."""
    fp = tmp_path / "side.jsonl"
    lines = [
        json.dumps({"type": "system", "message": {"content": "system prelude"}}),
        json.dumps({"type": "user", "message": {"content": "actual prompt"}}),
        json.dumps({"type": "assistant", "message": {"content": "later"}}),
    ]
    fp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert backfill._first_user_content(fp) == "actual prompt"


# --- _identify_target_question ---


def test_identify_target_question_per_repo(corpus_min):
    prompt = "Overview the repo at /home/spark/git/culture.\n\nConstraints..."
    result = backfill._identify_target_question(prompt, corpus_min)
    assert result == ("culture", "q-profile-overview")


def test_identify_target_question_per_repo_disambiguates_targets(corpus_min):
    """Both `culture` and `daria` are valid targets; the prompt's
    target path must drive the choice."""
    prompt_daria = "Overview the repo at /home/spark/git/daria.\n"
    prompt_culture = "Overview the repo at /home/spark/git/culture.\n"
    assert backfill._identify_target_question(prompt_daria, corpus_min) == (
        "daria",
        "q-profile-overview",
    )
    assert backfill._identify_target_question(prompt_culture, corpus_min) == (
        "culture",
        "q-profile-overview",
    )


def test_identify_target_question_workspace_scope(corpus_min):
    prompt = "Map the repos in /home/spark/git.\n\nConstraints (verbatim)..."
    result = backfill._identify_target_question(prompt, corpus_min)
    assert result == (None, "q-graph-workspace")


def test_identify_target_question_returns_none_for_unmatched(corpus_min):
    prompt = "Some random text that does not match any corpus template."
    assert backfill._identify_target_question(prompt, corpus_min) is None


def test_identify_target_question_returns_none_for_empty_prompt(corpus_min):
    assert backfill._identify_target_question("", corpus_min) is None


# --- _all_tester_sidechains key shape ---


def _stage_session_with_sidechain(
    projects_root: Path,
    repo_root_encoded: str,
    session_id: str,
    agent_id: str,
    *,
    description: str,
    user_prompt: str,
):
    """Set up one fake session with one tester sidechain + meta."""
    sub_dir = projects_root / repo_root_encoded / session_id / "subagents"
    sub_dir.mkdir(parents=True, exist_ok=True)

    meta_fp = sub_dir / f"agent-{agent_id}.meta.json"
    meta_fp.write_text(
        json.dumps({"agentType": "Explore", "description": description}),
        encoding="utf-8",
    )

    side_fp = sub_dir / f"agent-{agent_id}.jsonl"
    side_fp.write_text(
        json.dumps({"type": "user", "message": {"content": user_prompt}})
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "timestamp": "2026-05-15T16:00:08.542Z",
                "message": {
                    "model": "claude-haiku-4-5-20251001",
                    "content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                    "stop_reason": "end_turn",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return side_fp


def test_all_tester_sidechains_disambiguates_by_target_and_question(
    tmp_path, monkeypatch, corpus_min
):
    """Two sessions with the same (arm, trial) but different (target, question)
    must produce distinct keys, not collide."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_root = tmp_path / "claude_projects"
    monkeypatch.setattr(backfill._io, "REPO_ROOT", repo_root)
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects_root))
    encoded = str(repo_root).replace("/", "-")

    # Session 1: arm-A t1 of culture/q-profile-overview
    _stage_session_with_sidechain(
        projects_root,
        encoded,
        session_id="sess-culture",
        agent_id="aaa11111",
        description="Arm-A t1: culture profile",
        user_prompt="Overview the repo at /home/spark/git/culture.\n",
    )
    # Session 2: arm-A t1 of daria/q-profile-overview (same arm + trial!)
    _stage_session_with_sidechain(
        projects_root,
        encoded,
        session_id="sess-daria",
        agent_id="bbb22222",
        description="Arm-A t1: daria profile",
        user_prompt="Overview the repo at /home/spark/git/daria.\n",
    )

    sidechains = backfill._all_tester_sidechains(corpus_min)

    # Both keyed cleanly, no collision
    assert ("A", "culture", "q-profile-overview", 1) in sidechains
    assert ("A", "daria", "q-profile-overview", 1) in sidechains
    assert sidechains[("A", "culture", "q-profile-overview", 1)].name == "agent-aaa11111.jsonl"
    assert sidechains[("A", "daria", "q-profile-overview", 1)].name == "agent-bbb22222.jsonl"


def test_all_tester_sidechains_skips_judge_dispatches(tmp_path, monkeypatch, corpus_min):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_root = tmp_path / "claude_projects"
    monkeypatch.setattr(backfill._io, "REPO_ROOT", repo_root)
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects_root))
    encoded = str(repo_root).replace("/", "-")

    _stage_session_with_sidechain(
        projects_root,
        encoded,
        session_id="sess-judge",
        agent_id="ccc33333",
        description="scripts_eval judge: culture/q-profile-overview/1",
        user_prompt="You are a blind judge…",
    )

    sidechains = backfill._all_tester_sidechains(corpus_min)
    assert sidechains == {}


def test_all_tester_sidechains_drops_unmatchable_prompt(tmp_path, monkeypatch, corpus_min):
    """Sidechain whose first user prompt doesn't match any corpus template
    is dropped — safer than guessing."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    projects_root = tmp_path / "claude_projects"
    monkeypatch.setattr(backfill._io, "REPO_ROOT", repo_root)
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects_root))
    encoded = str(repo_root).replace("/", "-")

    _stage_session_with_sidechain(
        projects_root,
        encoded,
        session_id="sess-mystery",
        agent_id="ddd44444",
        description="Arm-A t1: unknown",
        user_prompt="Tell me about /tmp/something-else.",
    )

    sidechains = backfill._all_tester_sidechains(corpus_min)
    assert sidechains == {}


# --- backfill_cell uses the 4-tuple ---


def test_backfill_cell_misses_when_cell_key_does_not_match(tmp_path, monkeypatch, corpus_min):
    """If a cell's (arm, target, question, trial) has no matching sidechain,
    backfill_cell reports a clear skip with the full key."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(backfill._io, "REPO_ROOT", repo_root)

    cell_path = (
        repo_root
        / "experiments"
        / "scripts_eval"
        / "results"
        / "r1"
        / "arm-A"
        / "culture-q-profile-overview-t1.json"
    )
    cell_path.parent.mkdir(parents=True, exist_ok=True)
    cell_path.write_text(
        json.dumps(
            {
                "run_id": "r1",
                "arm": "A",
                "repo_id": "culture",
                "question_id": "q-profile-overview",
                "trial": 1,
                "subagent": {},
                "question_text": "",
                "answer_text": "",
                "validation": None,
                "judge": None,
            }
        ),
        encoding="utf-8",
    )

    summary = backfill.backfill_cell(cell_path, sidechains={}, pre_tools={})
    assert "skipped" in summary
    # Skip message names the full key, not just (arm, trial)
    assert "culture" in summary["skipped"]
    assert "q-profile-overview" in summary["skipped"]
