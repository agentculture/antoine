"""Tests for manifest.py — per-run metadata writer."""

from __future__ import annotations

import json

from experiments.scripts_eval import _io, manifest


def test_init_writes_manifest_with_corpus_version(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    corpus_yaml = tmp_path / "corpus.yaml"
    corpus_yaml.write_text(
        "corpus_version: 7\n"
        "config: {trials_per_cell: 1, arms: [A, C], workspace_root: /tmp}\n"
        "targets: []\nquestions: []\n"
    )
    out = manifest.init(
        "r1",
        corpus_path=corpus_yaml,
        operator_model="claude-opus-4-7",
        judge_model="claude-opus-4-7",
        rubric_version="v1",
        now=lambda: "2026-05-15T10:00:00Z",
        git_sha=lambda: "abc1234",
        git_branch=lambda: "experiments/scripts-eval",
    )
    data = json.loads(out.read_text())
    assert data["run_id"] == "r1"
    assert data["corpus_version"] == 7
    assert data["operator"]["model"] == "claude-opus-4-7"
    assert data["judge_model"] == "claude-opus-4-7"
    assert data["env"]["git_sha"] == "abc1234"
    assert data["env"]["git_branch"] == "experiments/scripts-eval"
    assert data["started_at"] == "2026-05-15T10:00:00Z"


def test_init_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    corpus_yaml = tmp_path / "corpus.yaml"
    corpus_yaml.write_text(
        "corpus_version: 1\n"
        "config: {trials_per_cell: 1, arms: [A], workspace_root: /tmp}\n"
        "targets: []\nquestions: []\n"
    )
    a = manifest.init(
        "r1",
        corpus_path=corpus_yaml,
        operator_model="x",
        judge_model="y",
        rubric_version="v1",
        now=lambda: "T1",
        git_sha=lambda: "s1",
        git_branch=lambda: "b1",
    )
    b = manifest.init(
        "r1",
        corpus_path=corpus_yaml,
        operator_model="z",
        judge_model="z",
        rubric_version="v9",
        now=lambda: "T2",
        git_sha=lambda: "s2",
        git_branch=lambda: "b2",
    )
    # Second call returns the same path with the original content untouched.
    assert a == b
    data = json.loads(b.read_text())
    assert data["operator"]["model"] == "x"  # original
    assert data["started_at"] == "T1"
