"""Tests for judge.py — pairwise blind judge with subagent dispatch.

The Python module owns determinism (pairing, seeded blinding, JSON parse,
disk write). The actual LLM call is performed by an operator-dispatched
subagent — so no API client is exercised here. The tests cover the two
public APIs: ``iter_jobs`` (the prepare side) and ``record_verdict``
(the record side).
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from experiments.scripts_eval import _io, judge


def _seed_pair(
    rd: Path,
    qid: str,
    repo: str | None,
    trial: int,
    *,
    a_text: str = "answer from arm A",
    c_text: str = "answer from arm C",
    question_text: str | None = None,
) -> None:
    """Write a paired (A, C) cell into ``rd/arm-A/`` and ``rd/arm-C/``."""
    q = question_text if question_text is not None else f"What does {repo or 'this workspace'} do?"
    for arm, text in (("A", a_text), ("C", c_text)):
        cell = {
            "run_id": "r1",
            "arm": arm,
            "repo_id": repo,
            "question_id": qid,
            "trial": trial,
            "answer_text": text,
            "question_text": q,
            "subagent": {},
            "validation": {"score": 0.5},
            "judge": None,
        }
        suffix = repo or "_workspace_"
        out = rd / f"arm-{arm}" / f"{suffix}-{qid}-t{trial}.json"
        _io.write_json(out, cell)


class TestPrepare:
    def test_emits_one_job_per_pair(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)
        _seed_pair(rd, "q1", "culture", 2)
        _seed_pair(rd, "q1", "daria", 1)

        jobs = list(
            judge.iter_jobs(
                "r1",
                rubric_text="rubric body",
                rubric_version="v1",
                judge_model="subagent:claude-opus-4-7",
                rng=random.Random(0),  # noqa: S311
            )
        )

        assert len(jobs) == 3
        assert {j["pair_key"] for j in jobs} == {
            "culture/q1/1",
            "culture/q1/2",
            "daria/q1/1",
        }
        # Round-tripped corpus fields are present.
        sample = jobs[0]
        assert {
            "pair_key",
            "repo_id",
            "question_id",
            "trial",
            "blind_label_for_A",
            "blind_label_for_C",
            "prompt_text",
            "rubric_version",
            "judge_model",
        } <= sample.keys()
        assert sample["rubric_version"] == "v1"
        assert sample["judge_model"] == "subagent:claude-opus-4-7"

    def test_blinding_is_seeded_and_stable(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)
        _seed_pair(rd, "q1", "culture", 2)

        jobs_a = list(
            judge.iter_jobs(
                "r1",
                rubric_text="r",
                rubric_version="v1",
                judge_model="m",
                rng=random.Random(0),  # noqa: S311
            )
        )
        jobs_b = list(
            judge.iter_jobs(
                "r1",
                rubric_text="r",
                rubric_version="v1",
                judge_model="m",
                rng=random.Random(0),  # noqa: S311
            )
        )
        # Same seed → identical blinding per pair.
        for j_a, j_b in zip(jobs_a, jobs_b):
            assert j_a["blind_label_for_A"] == j_b["blind_label_for_A"]
            assert j_a["blind_label_for_C"] == j_b["blind_label_for_C"]
        # Labels are complementary on every pair.
        for j in jobs_a:
            assert {j["blind_label_for_A"], j["blind_label_for_C"]} == {
                "answer_X",
                "answer_Y",
            }

    def test_strips_tools_used_and_evidence_tails(self, monkeypatch, tmp_path):
        """The judge must not see the ``### tools_used`` / ``### evidence``
        tails — they de-blind the comparison (e.g. arm C's tail can name
        ``scripts/profile.sh``, immediately revealing the equipped arm)."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        c_text = (
            "The agtag repo is a small CLI for issue posting.\n\n"
            "### tools_used\n"
            "- Bash: 3 (uses scripts/profile.sh)\n"
            "- Read: 5\n\n"
            "### evidence\n"
            "- agtag/cli/__init__.py\n"
            "- pyproject.toml\n"
        )
        a_text = (
            "agtag is a CLI tool.\n\n"
            "### tools_used\n"
            "- Read: 12\n"
            "- Grep: 4\n\n"
            "### evidence\n"
            "- agtag/cli/__init__.py\n"
        )
        _seed_pair(rd, "q1", "agtag", 1, a_text=a_text, c_text=c_text)

        jobs = list(
            judge.iter_jobs(
                "r1",
                rubric_text="r",
                rubric_version="v1",
                judge_model="m",
                rng=random.Random(0),  # noqa: S311
            )
        )
        prompt = jobs[0]["prompt_text"]
        # Answer bodies preserved.
        assert "small CLI for issue posting" in prompt
        assert "agtag is a CLI tool" in prompt
        # Tails and de-blinding signals stripped.
        assert "### tools_used" not in prompt
        assert "### evidence" not in prompt
        assert "scripts/profile.sh" not in prompt
        assert "Bash: 3" not in prompt
        assert "Read: 12" not in prompt

    def test_prompt_contains_rubric_and_question_and_no_tools_directive(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(
            rd,
            "q-overview",
            "culture",
            1,
            a_text="answer A body",
            c_text="answer C body",
            question_text="What does culture do?",
        )

        jobs = list(
            judge.iter_jobs(
                "r1",
                rubric_text="RUBRIC BODY HERE",
                rubric_version="v1",
                judge_model="m",
                rng=random.Random(0),  # noqa: S311
            )
        )
        prompt = jobs[0]["prompt_text"]
        assert "RUBRIC BODY HERE" in prompt
        assert "What does culture do?" in prompt
        assert "answer A body" in prompt
        assert "answer C body" in prompt
        # No-tools / JSON-only directive present so the subagent doesn't
        # invoke Read/Grep when this prompt lands.
        assert "Do not call any tools" in prompt

    def test_skips_unpaired_pair(self, monkeypatch, tmp_path):
        """One arm only → no job emitted."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        cell = {
            "run_id": "r1",
            "arm": "C",
            "repo_id": "culture",
            "question_id": "q1",
            "trial": 1,
            "answer_text": "C answer",
            "question_text": "Q?",
            "subagent": {},
            "validation": None,
            "judge": None,
        }
        _io.write_json(rd / "arm-C" / "culture-q1-t1.json", cell)

        jobs = list(
            judge.iter_jobs(
                "r1",
                rubric_text="r",
                rubric_version="v1",
                judge_model="m",
                rng=random.Random(0),  # noqa: S311
            )
        )
        assert jobs == []


class TestRecord:
    def test_writes_judge_block_to_both_cells(self, monkeypatch, tmp_path):
        """The locked-surface ``judge`` block lands on both paired cells."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        verdict_text = '{"winner": "X", "margin": "clear", "reasoning": "X is sharper."}'
        a_path, c_path = judge.record_verdict(
            "r1",
            pair_key="culture/q1/1",
            verdict_text=verdict_text,
            blind_label_for_a="answer_X",
            blind_label_for_c="answer_Y",
            rubric_version="v1",
            judge_model="subagent:claude-opus-4-7",
        )

        a_cell = _io.read_json(a_path)
        c_cell = _io.read_json(c_path)
        # Same judge block on both sides.
        assert a_cell["judge"] == c_cell["judge"]
        block = a_cell["judge"]
        assert block["judge_model"] == "subagent:claude-opus-4-7"
        assert block["rubric_version"] == "v1"
        cmp_ = block["comparison"]
        assert cmp_["winner"] == "A"  # A was blinded as answer_X, judge picked X
        assert cmp_["margin"] == "clear"
        assert cmp_["reasoning"] == "X is sharper."
        assert cmp_["blind_label_for_A"] == "answer_X"
        assert cmp_["blind_label_for_C"] == "answer_Y"

    @pytest.mark.parametrize(
        "winner_letter,a_label,expected_winner",
        [
            ("X", "answer_X", "A"),
            ("X", "answer_Y", "C"),
            ("Y", "answer_X", "C"),
            ("Y", "answer_Y", "A"),
            ("tie", "answer_X", "tie"),
            ("tie", "answer_Y", "tie"),
        ],
    )
    def test_de_blinds_winner_correctly(
        self, monkeypatch, tmp_path, winner_letter, a_label, expected_winner
    ):
        """De-blinding maps verdict X/Y/tie back to A/C/tie using the blind
        labels recorded by prepare."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)
        c_label = "answer_Y" if a_label == "answer_X" else "answer_X"

        verdict_text = f'{{"winner": "{winner_letter}", "margin": "slight", "reasoning": "r"}}'
        a_path, _ = judge.record_verdict(
            "r1",
            pair_key="culture/q1/1",
            verdict_text=verdict_text,
            blind_label_for_a=a_label,
            blind_label_for_c=c_label,
            rubric_version="v1",
            judge_model="m",
        )
        cmp_ = _io.read_json(a_path)["judge"]["comparison"]
        assert cmp_["winner"] == expected_winner

    def test_extracts_json_from_noisy_text(self, monkeypatch, tmp_path):
        """A chatty subagent may wrap the JSON in prose — extract the
        first ``{...}`` and proceed."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        verdict_text = (
            "Here is my analysis. Based on the rubric...\n\n"
            '{"winner": "Y", "margin": "decisive", "reasoning": "Y is more concrete."}\n\n'
            "Hope that helps!"
        )
        a_path, _ = judge.record_verdict(
            "r1",
            pair_key="culture/q1/1",
            verdict_text=verdict_text,
            blind_label_for_a="answer_X",
            blind_label_for_c="answer_Y",
            rubric_version="v1",
            judge_model="m",
        )
        cmp_ = _io.read_json(a_path)["judge"]["comparison"]
        assert cmp_["winner"] == "C"  # Y picked, C was answer_Y
        assert cmp_["margin"] == "decisive"
        assert cmp_["reasoning"] == "Y is more concrete."

    def test_rejects_malformed_verdict(self, monkeypatch, tmp_path):
        """No JSON / unknown winner / unknown margin → ``ValueError``.

        Loud failure forces the operator to re-dispatch the subagent
        rather than silently record a false tie.
        """
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        def _call(verdict_text: str):
            judge.record_verdict(
                "r1",
                pair_key="culture/q1/1",
                verdict_text=verdict_text,
                blind_label_for_a="answer_X",
                blind_label_for_c="answer_Y",
                rubric_version="v1",
                judge_model="m",
            )

        # No JSON at all.
        with pytest.raises(ValueError, match="non-JSON"):
            _call("the subagent refused to produce JSON")
        # Unknown winner letter.
        with pytest.raises(ValueError, match="winner"):
            _call('{"winner": "Z", "margin": "tie", "reasoning": ""}')
        # Unknown margin vocabulary.
        with pytest.raises(ValueError, match="margin"):
            _call('{"winner": "X", "margin": "huge", "reasoning": ""}')

    def test_idempotent_on_replay(self, monkeypatch, tmp_path):
        """Re-recording a pair overwrites cleanly — no double-write,
        no corruption — so the operator can recover from a bad
        subagent answer without manual cell editing."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        a_path, c_path = judge.record_verdict(
            "r1",
            pair_key="culture/q1/1",
            verdict_text='{"winner": "X", "margin": "slight", "reasoning": "first"}',
            blind_label_for_a="answer_X",
            blind_label_for_c="answer_Y",
            rubric_version="v1",
            judge_model="m",
        )
        # Replay with a different verdict — both cells should reflect
        # the second call, not a merger of the two.
        judge.record_verdict(
            "r1",
            pair_key="culture/q1/1",
            verdict_text='{"winner": "Y", "margin": "decisive", "reasoning": "second"}',
            blind_label_for_a="answer_X",
            blind_label_for_c="answer_Y",
            rubric_version="v1",
            judge_model="m",
        )
        for fp in (a_path, c_path):
            cmp_ = _io.read_json(fp)["judge"]["comparison"]
            assert cmp_["winner"] == "C"  # Y → C under this blinding
            assert cmp_["margin"] == "decisive"
            assert cmp_["reasoning"] == "second"

    def test_record_unknown_pair_key_raises(self, monkeypatch, tmp_path):
        """A pair_key with no on-disk cells is a programming error."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)
        with pytest.raises(ValueError, match="no cells"):
            judge.record_verdict(
                "r1",
                pair_key="missing/q1/9",
                verdict_text='{"winner": "X", "margin": "tie", "reasoning": ""}',
                blind_label_for_a="answer_X",
                blind_label_for_c="answer_Y",
                rubric_version="v1",
                judge_model="m",
            )

    def test_extracts_first_json_object_with_multiple_candidates(self, monkeypatch, tmp_path):
        """A chatty subagent may emit several `{...}` blobs (false start +
        correction). RUNBOOK promises the first valid one wins — a greedy
        ``r"\\{.*\\}"`` span would otherwise capture from the first ``{``
        to the *last* ``}`` and either fail to parse or return the wrong
        object."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        verdict_text = (
            "Let me think... first attempt:\n"
            '{"winner": "X", "margin": "tie", "reasoning": "first try"}\n'
            "Actually, on reflection:\n"
            '{"winner": "Y", "margin": "decisive", "reasoning": "second try"}'
        )
        a_path, _ = judge.record_verdict(
            "r1",
            pair_key="culture/q1/1",
            verdict_text=verdict_text,
            blind_label_for_a="answer_X",
            blind_label_for_c="answer_Y",
            rubric_version="v1",
            judge_model="m",
        )
        cmp_ = _io.read_json(a_path)["judge"]["comparison"]
        # First valid JSON wins.
        assert cmp_["margin"] == "tie"
        assert cmp_["reasoning"] == "first try"
        assert cmp_["winner"] == "A"  # X under a_label=answer_X

    def test_extracts_json_with_nested_braces(self, monkeypatch, tmp_path):
        """Balanced-brace scanning must respect nested objects and quoted
        strings — a future rubric may include sub-objects in the verdict
        and braces inside ``reasoning`` strings are also possible."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        verdict_text = (
            'Verdict: {"winner": "X", "margin": "clear", '
            '"reasoning": "X cites {nested} braces in its body"} (done)'
        )
        a_path, _ = judge.record_verdict(
            "r1",
            pair_key="culture/q1/1",
            verdict_text=verdict_text,
            blind_label_for_a="answer_X",
            blind_label_for_c="answer_Y",
            rubric_version="v1",
            judge_model="m",
        )
        cmp_ = _io.read_json(a_path)["judge"]["comparison"]
        assert cmp_["reasoning"] == "X cites {nested} braces in its body"
        assert cmp_["margin"] == "clear"

    def test_record_rejects_identical_blind_labels(self, monkeypatch, tmp_path):
        """If a caller passes the same blind label for A and C, de-blinding
        is ambiguous — silently returning ``A`` (which the current
        ``_de_blind`` does) would persist the wrong winner to the locked
        surface. Fail loudly instead."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        with pytest.raises(ValueError, match="blind_label"):
            judge.record_verdict(
                "r1",
                pair_key="culture/q1/1",
                verdict_text='{"winner": "X", "margin": "tie", "reasoning": ""}',
                blind_label_for_a="answer_X",
                blind_label_for_c="answer_X",  # same as A — invalid
                rubric_version="v1",
                judge_model="m",
            )

    def test_record_rejects_invalid_blind_label_values(self, monkeypatch, tmp_path):
        """blind labels must be in {answer_X, answer_Y}; anything else
        means a bug in the caller and should fail before disk I/O."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_pair(rd, "q1", "culture", 1)

        with pytest.raises(ValueError, match="blind_label"):
            judge.record_verdict(
                "r1",
                pair_key="culture/q1/1",
                verdict_text='{"winner": "X", "margin": "tie", "reasoning": ""}',
                blind_label_for_a="answer_Z",  # invalid value
                blind_label_for_c="answer_Y",
                rubric_version="v1",
                judge_model="m",
            )
