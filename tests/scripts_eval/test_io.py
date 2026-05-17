"""Tests for experiments.scripts_eval._io shared helpers."""

from __future__ import annotations

import json

import pytest

from experiments.scripts_eval import _io


def test_eval_run_id_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("ANTOINE_EVAL_RUN_ID", "2026-05-15-run-01")
    assert _io.eval_run_id() == "2026-05-15-run-01"


def test_eval_run_id_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("ANTOINE_EVAL_RUN_ID", raising=False)
    assert _io.eval_run_id() is None


def test_eval_arm_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("ANTOINE_EVAL_ARM", "C")
    assert _io.eval_arm() == "C"


def test_eval_arm_rejects_invalid(monkeypatch):
    monkeypatch.setenv("ANTOINE_EVAL_ARM", "Q")
    with pytest.raises(ValueError, match=r"ANTOINE_EVAL_ARM must be one of \('A', 'B', 'C'\)"):
        _io.eval_arm()


def test_eval_arm_accepts_b(monkeypatch):
    monkeypatch.setenv("ANTOINE_EVAL_ARM", "B")
    assert _io.eval_arm() == "B"


def test_run_dir_constructs_path_under_results(tmp_path, monkeypatch):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    expected = tmp_path / "experiments" / "scripts_eval" / "results" / "r1"
    assert _io.run_dir("r1") == expected


def test_write_json_creates_parents_and_writes_pretty(tmp_path):
    target = tmp_path / "a" / "b" / "x.json"
    _io.write_json(target, {"k": 1, "v": [1, 2]})
    text = target.read_text(encoding="utf-8")
    assert json.loads(text) == {"k": 1, "v": [1, 2]}
    assert text.endswith("\n")  # trailing newline
