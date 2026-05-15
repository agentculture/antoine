"""Tests for judge.py — pairwise blind LLM-as-judge."""

from __future__ import annotations

import random
from pathlib import Path

from experiments.scripts_eval import _io, judge


class _FakeMessages:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        # Mimic anthropic.types.Message minimally.
        class _Block:
            def __init__(self, text):
                self.type = "text"
                self.text = text

        class _Msg:
            def __init__(self, text):
                self.content = [_Block(text)]
                self.usage = type("U", (), {"input_tokens": 1, "output_tokens": 2})()

        return _Msg(self.response_text)


class _FakeClient:
    def __init__(self, response_text: str):
        self.messages = _FakeMessages(response_text)


def _seed_pair(rd: Path, qid: str, repo: str, trial: int):
    for arm in ("A", "C"):
        cell = {
            "run_id": "r1",
            "arm": arm,
            "repo_id": repo,
            "question_id": qid,
            "trial": trial,
            "answer_text": f"answer from arm {arm}",
            "subagent": {},
            "validation": {"score": 0.5},
            "judge": None,
        }
        out = rd / f"arm-{arm}" / f"{repo}-{qid}-t{trial}.json"
        _io.write_json(out, cell)


def test_judge_writes_blind_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    _seed_pair(rd, "q1", "culture", 1)
    fake = _FakeClient('{"winner": "X", "margin": "clear", "reasoning": "X is more concrete."}')

    rng = random.Random(0)  # noqa: S311
    judge.process_run(
        "r1",
        client=fake,
        rubric_text="rubric goes here",
        rubric_version="v1",
        judge_model="claude-opus-4-7",
        rng=rng,
    )

    a_cell = _io.read_json(rd / "arm-A" / "culture-q1-t1.json")
    c_cell = _io.read_json(rd / "arm-C" / "culture-q1-t1.json")
    # Same judge object on both cells of a pair.
    assert a_cell["judge"] == c_cell["judge"]
    assert a_cell["judge"]["judge_model"] == "claude-opus-4-7"
    assert a_cell["judge"]["rubric_version"] == "v1"
    # Blinding fields recorded.
    cmp_ = a_cell["judge"]["comparison"]
    assert cmp_["margin"] == "clear"
    assert cmp_["winner"] in ("A", "C")
    assert cmp_["blind_label_for_A"] in ("answer_X", "answer_Y")
    assert cmp_["blind_label_for_C"] in ("answer_X", "answer_Y")
    assert cmp_["blind_label_for_A"] != cmp_["blind_label_for_C"]


def test_judge_skips_pair_when_one_side_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    # Only arm-C exists; no matching arm-A.
    cell = {
        "run_id": "r1",
        "arm": "C",
        "repo_id": "culture",
        "question_id": "q1",
        "trial": 1,
        "answer_text": "x",
        "subagent": {},
        "validation": None,
        "judge": None,
    }
    _io.write_json(rd / "arm-C" / "culture-q1-t1.json", cell)
    fake = _FakeClient('{"winner":"X","margin":"tie","reasoning":""}')
    judge.process_run(
        "r1",
        client=fake,
        rubric_text="r",
        rubric_version="v1",
        judge_model="m",
        rng=random.Random(0),  # noqa: S311
    )
    # Judge field still None — no pair.
    cell = _io.read_json(rd / "arm-C" / "culture-q1-t1.json")
    assert cell["judge"] is None
