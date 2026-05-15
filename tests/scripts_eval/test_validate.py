"""Tests for validate.py — adds validation block to per-cell JSONs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.scripts_eval import _io, validate


def _seed_cell(run_dir: Path, arm: str, name: str, payload: dict) -> Path:
    out = run_dir / f"arm-{arm}" / name
    _io.write_json(out, payload)
    return out


def test_validate_marks_recall(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    fp = _seed_cell(
        rd,
        "C",
        "culture-q1-t1.json",
        {
            "run_id": "r1",
            "arm": "C",
            "repo_id": "culture",
            "question_id": "q1",
            "trial": 1,
            "answer_text": (
                "Look at pyproject.toml; run uv sync to install. "
                "The repo is an async IRCd."
            ),
            "subagent": {},
            "validation": None,
            "judge": None,
        },
    )
    expected = {"q1": {"culture": ["pyproject.toml", "uv sync", "async IRCd", "agent harness"]}}

    cells = validate.process_run("r1", expected_evidence_by_q_repo=expected)

    cell = json.loads(fp.read_text())
    assert cell["validation"]["found"] == ["pyproject.toml", "uv sync", "async IRCd"]
    assert cell["validation"]["missing"] == ["agent harness"]
    assert cell["validation"]["score"] == pytest.approx(0.75, rel=1e-3)
    assert cell["validation"]["expected_evidence"] == expected["q1"]["culture"]
    assert cells == [cell]


def test_validate_handles_workspace_question(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    fp = _seed_cell(
        rd,
        "A",
        "_workspace_-q-graph-t1.json",
        {
            "run_id": "r1",
            "arm": "A",
            "repo_id": None,
            "question_id": "q-graph",
            "trial": 1,
            "answer_text": "AgentCulture cluster: culture, daria, steward.",
            "subagent": {},
            "validation": None,
            "judge": None,
        },
    )
    expected = {"q-graph": {"_global": ["AgentCulture", "culture", "missing-thing"]}}

    validate.process_run("r1", expected_evidence_by_q_repo=expected)

    cell = json.loads(fp.read_text())
    assert sorted(cell["validation"]["found"]) == ["AgentCulture", "culture"]
    assert cell["validation"]["missing"] == ["missing-thing"]
    assert cell["validation"]["score"] == pytest.approx(2 / 3, rel=1e-3)


def test_validate_supports_regex_form(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    fp = _seed_cell(
        rd,
        "C",
        "x-q1-t1.json",
        {
            "run_id": "r1",
            "arm": "C",
            "repo_id": "x",
            "question_id": "q1",
            "trial": 1,
            "answer_text": "version 0.42.7 ships",
            "subagent": {},
            "validation": None,
            "judge": None,
        },
    )
    expected = {"q1": {"x": ["/version \\d+\\.\\d+\\.\\d+/"]}}
    validate.process_run("r1", expected_evidence_by_q_repo=expected)
    cell = json.loads(fp.read_text())
    assert cell["validation"]["score"] == 1.0
