"""Tests for summarize.py — accumulates per-set evidence into a single
tracked markdown file between marker comments."""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.scripts_eval import _io, summarize


def _seed_cell(
    rd: Path,
    *,
    arm: str,
    repo_id: str | None,
    question_id: str,
    trial: int,
    answer_text: str = "answer body",
    duration: float = 12.5,
    tools_used: list | None = None,
    judge_block: dict | None = None,
    validation: dict | None = None,
) -> None:
    cell = {
        "run_id": "r1",
        "arm": arm,
        "repo_id": repo_id,
        "question_id": question_id,
        "trial": trial,
        "subagent": {
            "agent_type": "Explore",
            "model": "claude-opus-4-7",
            "duration_seconds": duration,
            "tokens": {"input": 1000, "output": 500, "cache_read": 0, "cache_creation": 0},
            "tools_used": tools_used or [{"name": "Read", "count": 5, "patterns": []}],
        },
        "question_text": "Q?",
        "answer_text": answer_text,
        "validation": validation,
        "judge": judge_block,
    }
    suffix = repo_id or "_workspace_"
    out = rd / f"arm-{arm}" / f"{suffix}-{question_id}-t{trial}.json"
    _io.write_json(out, cell)


def _judge_block(winner: str, margin: str = "slight", reasoning: str = "r") -> dict:
    return {
        "judge_model": "subagent:claude-opus-4-7",
        "rubric_version": "v1",
        "comparison": {
            "winner": winner,
            "margin": margin,
            "reasoning": reasoning,
            "blind_label_for_A": "answer_X",
            "blind_label_for_C": "answer_Y",
        },
    }


_TEMPLATE = """# Round-1

Prose preamble that should be untouched.

<!-- runstate:start -->
(placeholder)
<!-- runstate:end -->

More untouched prose.

<!-- evidence:start -->
(placeholder)
<!-- evidence:end -->

Footer that should be untouched.
"""


class TestCollectState:
    def test_empty_run_yields_no_sets(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        _io.run_dir("r1").mkdir(parents=True)
        state = summarize.collect_run_state("r1")
        assert state == []

    def test_one_paired_unjudged_set(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q-profile-overview", trial=1)
        _seed_cell(rd, arm="C", repo_id="agtag", question_id="q-profile-overview", trial=1)

        state = summarize.collect_run_state("r1")
        assert len(state) == 1
        s = state[0]
        assert s["repo_id"] == "agtag"
        assert s["question_id"] == "q-profile-overview"
        assert s["arm_a_trials"] == [1]
        assert s["arm_c_trials"] == [1]
        assert s["judged_trials"] == []
        # winner tally is all zero when nothing judged
        assert s["winners"] == {"A": 0, "C": 0, "tie": 0}

    def test_judged_pair_counts_winner(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_cell(
            rd,
            arm="A",
            repo_id="agtag",
            question_id="q-profile-overview",
            trial=1,
            judge_block=_judge_block("C", margin="clear", reasoning="C cites more files"),
        )
        _seed_cell(
            rd,
            arm="C",
            repo_id="agtag",
            question_id="q-profile-overview",
            trial=1,
            judge_block=_judge_block("C", margin="clear", reasoning="C cites more files"),
        )
        state = summarize.collect_run_state("r1")
        s = state[0]
        assert s["judged_trials"] == [1]
        assert s["winners"] == {"A": 0, "C": 1, "tie": 0}

    def test_arm_a_only_no_pair(self, monkeypatch, tmp_path):
        """Arm A captured, arm C still pending — set is listed but unjudged."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q-profile-overview", trial=1)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q-profile-overview", trial=2)
        state = summarize.collect_run_state("r1")
        s = state[0]
        assert s["arm_a_trials"] == [1, 2]
        assert s["arm_c_trials"] == []
        assert s["judged_trials"] == []

    def test_sorts_by_repo_then_question(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        # Out-of-order seeding
        _seed_cell(rd, arm="A", repo_id="daria", question_id="q-narrative", trial=1)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q-profile-overview", trial=1)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q-connections-1hop", trial=1)
        state = summarize.collect_run_state("r1")
        keys = [(s["repo_id"], s["question_id"]) for s in state]
        assert keys == [
            ("agtag", "q-connections-1hop"),
            ("agtag", "q-profile-overview"),
            ("daria", "q-narrative"),
        ]


class TestRender:
    def test_runstate_table_marks_done_and_pending(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q1", trial=1)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q1", trial=2)
        _seed_cell(
            rd, arm="C", repo_id="agtag", question_id="q1", trial=1, judge_block=_judge_block("A")
        )
        # Mirror block for the A side (record_verdict writes identical blocks)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q1", trial=3, judge_block=None)
        state = summarize.collect_run_state("r1")
        table = summarize.render_runstate_table(state)
        assert "| agtag | q1 |" in table
        # trial counts shown as "X/3"
        assert "3/3" in table or "2/3" in table  # arm-A: 3 trials present

    def test_evidence_section_includes_reasoning_when_judged(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_cell(
            rd,
            arm="A",
            repo_id="agtag",
            question_id="q1",
            trial=1,
            judge_block=_judge_block(
                "C",
                margin="decisive",
                reasoning="C names test_cli.py and bandit explicitly",
            ),
        )
        _seed_cell(
            rd,
            arm="C",
            repo_id="agtag",
            question_id="q1",
            trial=1,
            judge_block=_judge_block(
                "C",
                margin="decisive",
                reasoning="C names test_cli.py and bandit explicitly",
            ),
        )
        state = summarize.collect_run_state("r1")
        section = summarize.render_evidence_sections(state)
        assert "agtag / q1" in section
        assert "C names test_cli.py and bandit explicitly" in section
        # Winner+margin annotated
        assert "C" in section
        assert "decisive" in section


class TestUpdateFile:
    def test_replaces_between_markers_only(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q1", trial=1)
        _seed_cell(rd, arm="C", repo_id="agtag", question_id="q1", trial=1)

        evidence_path = tmp_path / "EVIDENCE.md"
        evidence_path.write_text(_TEMPLATE, encoding="utf-8")

        summarize.update_evidence_file("r1", evidence_path)

        content = evidence_path.read_text(encoding="utf-8")
        # Untouched bits stay.
        assert content.startswith("# Round-1\n")
        assert "Prose preamble that should be untouched." in content
        assert "Footer that should be untouched." in content
        # Markers still present.
        assert "<!-- runstate:start -->" in content
        assert "<!-- runstate:end -->" in content
        assert "<!-- evidence:start -->" in content
        assert "<!-- evidence:end -->" in content
        # Placeholder is replaced with real data.
        assert "(placeholder)" not in content
        assert "agtag" in content

    def test_idempotent_on_replay(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        _seed_cell(rd, arm="A", repo_id="agtag", question_id="q1", trial=1)

        evidence_path = tmp_path / "EVIDENCE.md"
        evidence_path.write_text(_TEMPLATE, encoding="utf-8")

        summarize.update_evidence_file("r1", evidence_path)
        first = evidence_path.read_text(encoding="utf-8")
        summarize.update_evidence_file("r1", evidence_path)
        second = evidence_path.read_text(encoding="utf-8")
        assert first == second

    def test_missing_markers_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        _io.run_dir("r1").mkdir(parents=True)
        bad = tmp_path / "EVIDENCE.md"
        bad.write_text("# No markers here\n", encoding="utf-8")
        with pytest.raises(ValueError, match="marker"):
            summarize.update_evidence_file("r1", bad)

    def test_payload_containing_end_marker_text_does_not_corrupt(self, monkeypatch, tmp_path):
        """Adversarial payload — judge reasoning that happens to quote
        the literal `<!-- evidence:end -->` string. A regex-based
        ``.*?end_marker`` would terminate at the inner occurrence on the
        next summarize call and corrupt the file. The escape step
        disarms the marker (``<!--`` → ``<\\!--``) so subsequent passes
        see only the proper markers."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        rd = _io.run_dir("r1")
        rd.mkdir(parents=True)
        nasty_reasoning = (
            "C names the markers verbatim: <!-- evidence:end --> "
            "and <!-- runstate:end --> — pathological but legal."
        )
        _seed_cell(
            rd,
            arm="A",
            repo_id="agtag",
            question_id="q1",
            trial=1,
            judge_block=_judge_block("C", margin="clear", reasoning=nasty_reasoning),
        )
        _seed_cell(
            rd,
            arm="C",
            repo_id="agtag",
            question_id="q1",
            trial=1,
            judge_block=_judge_block("C", margin="clear", reasoning=nasty_reasoning),
        )
        path = tmp_path / "EVIDENCE.md"
        path.write_text(_TEMPLATE, encoding="utf-8")

        # First call: payload lands between markers; literal markers
        # inside the reasoning are escaped.
        summarize.update_evidence_file("r1", path)
        first = path.read_text(encoding="utf-8")
        assert first.startswith("# Round-1\n")
        assert "Footer that should be untouched." in first
        # Escaped form of the contaminating markers landed in the table.
        assert "<\\!-- evidence:end -->" in first
        assert "<\\!-- runstate:end -->" in first
        # Proper marker pairs still each appear exactly once.
        assert first.count("<!-- runstate:start -->") == 1
        assert first.count("<!-- runstate:end -->") == 1
        assert first.count("<!-- evidence:start -->") == 1
        assert first.count("<!-- evidence:end -->") == 1
        # Second call must round-trip cleanly — no growth, no slice drift.
        summarize.update_evidence_file("r1", path)
        second = path.read_text(encoding="utf-8")
        assert second == first
        assert "Footer that should be untouched." in second

    def test_end_marker_before_start_marker_raises(self, monkeypatch, tmp_path):
        """If the source file accidentally inverts the order, the slice
        cannot proceed — find_end_after_start returns -1."""
        monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
        _io.run_dir("r1").mkdir(parents=True)
        inverted = (
            "# Round-1\n\n"
            "<!-- runstate:end -->\n(content)\n<!-- runstate:start -->\n\n"
            "<!-- evidence:start -->\n(c)\n<!-- evidence:end -->\n"
        )
        path = tmp_path / "EVIDENCE.md"
        path.write_text(inverted, encoding="utf-8")
        with pytest.raises(ValueError, match="end marker not found"):
            summarize.update_evidence_file("r1", path)
