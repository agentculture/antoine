"""Tests for experiments.scripts_eval.corpus loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.scripts_eval import corpus

FIXTURE = Path(__file__).parent / "fixtures" / "corpus_minimal.yaml"


def test_load_returns_corpus_with_targets_and_questions():
    c = corpus.load(FIXTURE)
    assert c.version == 1
    assert c.config.trials_per_cell == 3
    assert c.config.arms == ["A", "C"]
    assert {t.id for t in c.targets} == {"culture", "daria"}
    assert {q.id for q in c.questions} == {"q-profile-overview", "q-graph-workspace"}


def test_iter_cells_per_repo_question_yields_one_per_repo_per_trial():
    c = corpus.load(FIXTURE)
    cells = [cell for cell in c.iter_cells(arm="A") if cell.question_id == "q-profile-overview"]
    # 2 repos x 3 trials = 6
    assert len(cells) == 6
    assert {cell.repo_id for cell in cells} == {"culture", "daria"}
    assert sorted({cell.trial for cell in cells}) == [1, 2, 3]


def test_iter_cells_workspace_question_yields_one_per_trial_only():
    c = corpus.load(FIXTURE)
    cells = [cell for cell in c.iter_cells(arm="C") if cell.question_id == "q-graph-workspace"]
    # workspace scope: 1 cell per trial
    assert len(cells) == 3
    assert all(cell.repo_id is None for cell in cells)


def test_cell_carries_substituted_prompt():
    c = corpus.load(FIXTURE)
    cell = next(
        cell
        for cell in c.iter_cells(arm="A")
        if cell.question_id == "q-profile-overview" and cell.repo_id == "culture"
    )
    assert "/home/spark/git/culture" in cell.prompt


def test_load_rejects_unknown_scope(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "corpus_version: 1\n"
        "config: {trials_per_cell: 1, arms: [A], workspace_root: /tmp}\n"
        "targets: [{id: x, path: /tmp, description: y}]\n"
        "questions:\n"
        "  - {id: q1, type: profile, scope: bogus, template: 'x', expected_evidence: {x: [a]}}\n"
    )
    with pytest.raises(ValueError, match="scope"):
        corpus.load(bad)
