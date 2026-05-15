"""Tests for report.py — generate REPORT.md from a run dir."""

from __future__ import annotations

from experiments.scripts_eval import _io, report


def _seed(rd, arm, name, payload):
    out = rd / f"arm-{arm}" / name
    _io.write_json(out, payload)


def test_report_summarises_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    base = {
        "run_id": "r1",
        "repo_id": "culture",
        "question_id": "q1",
        "trial": 1,
        "subagent": {
            "model": "claude-opus-4-7",
            "duration_seconds": 30.0,
            "tokens": {
                "input": 1000,
                "output": 200,
                "cache_read": 500,
                "cache_creation": 50,
            },
            "tools_used": [{"name": "Read", "count": 2, "patterns": ["a", "b"]}],
        },
        "validation": {
            "score": 0.75,
            "found": ["x"],
            "missing": ["y"],
            "expected_evidence": ["x", "y"],
        },
        "judge": {
            "judge_model": "claude-opus-4-7",
            "rubric_version": "v1",
            "comparison": {
                "winner": "C",
                "margin": "clear",
                "reasoning": "more concrete",
                "blind_label_for_A": "answer_X",
                "blind_label_for_C": "answer_Y",
            },
        },
        "answer_text": "ans",
    }
    _seed(rd, "A", "culture-q1-t1.json", {**base, "arm": "A"})
    _seed(rd, "C", "culture-q1-t1.json", {**base, "arm": "C"})

    out_path = report.write_report("r1")
    text = out_path.read_text(encoding="utf-8")

    assert out_path == rd / "REPORT.md"
    assert "# scripts-eval — run `r1`" in text
    assert "culture / q1 / t1" in text
    assert "Winner: **C** (clear)" in text
    assert "validation A=0.75 / C=0.75" in text


def test_report_flags_arm_violations(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    a_payload = {
        "run_id": "r1",
        "arm": "A",
        "repo_id": "culture",
        "question_id": "q1",
        "trial": 1,
        "subagent": {
            "model": "m",
            "duration_seconds": 1.0,
            "tokens": {"input": 1, "output": 1, "cache_read": 0, "cache_creation": 0},
            "tools_used": [
                {
                    "name": "Bash",
                    "count": 1,
                    "patterns": ["scripts/profile.sh /tmp/x"],
                },
            ],
        },
        "validation": {
            "score": 1.0,
            "found": [],
            "missing": [],
            "expected_evidence": [],
        },
        "judge": None,
        "answer_text": "x",
    }
    _seed(rd, "A", "culture-q1-t1.json", a_payload)

    out_path = report.write_report("r1")
    text = out_path.read_text(encoding="utf-8")
    assert "## Violations" in text
    assert "A_used_scripts" in text
    assert "culture / q1 / t1" in text
