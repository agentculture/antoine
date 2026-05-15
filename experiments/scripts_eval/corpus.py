"""Corpus loader for the scripts-eval harness.

corpus.yaml is the source of truth for what to test (repos, questions,
expected_evidence). This module parses it and iterates over the
(arm, repo, question, trial) cells the runbook will dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

ALLOWED_SCOPES = {"per_repo", "workspace"}


@dataclass(frozen=True)
class Config:
    trials_per_cell: int
    arms: list[str]
    workspace_root: str


@dataclass(frozen=True)
class Target:
    id: str
    path: str
    description: str


@dataclass(frozen=True)
class Question:
    id: str
    type: str
    scope: str  # "per_repo" or "workspace"
    template: str
    expected_evidence: dict[str, list[str]]


@dataclass(frozen=True)
class Cell:
    arm: str
    repo_id: str | None  # None for workspace-scoped questions
    repo_path: str | None
    question_id: str
    question_type: str
    trial: int
    prompt: str
    expected_evidence: list[str]


@dataclass(frozen=True)
class Corpus:
    version: int
    config: Config
    targets: list[Target]
    questions: list[Question]

    def target_by_id(self, repo_id: str) -> Target:
        for t in self.targets:
            if t.id == repo_id:
                return t
        raise KeyError(f"no target with id={repo_id!r}")

    def iter_cells(self, arm: str) -> Iterator[Cell]:
        for q in self.questions:
            for trial in range(1, self.config.trials_per_cell + 1):
                if q.scope == "workspace":
                    prompt = q.template.format(workspace_root=self.config.workspace_root)
                    yield Cell(
                        arm=arm,
                        repo_id=None,
                        repo_path=None,
                        question_id=q.id,
                        question_type=q.type,
                        trial=trial,
                        prompt=prompt,
                        expected_evidence=q.expected_evidence.get("_global", []),
                    )
                else:  # per_repo
                    for t in self.targets:
                        prompt = q.template.format(repo_path=t.path)
                        yield Cell(
                            arm=arm,
                            repo_id=t.id,
                            repo_path=t.path,
                            question_id=q.id,
                            question_type=q.type,
                            trial=trial,
                            prompt=prompt,
                            expected_evidence=q.expected_evidence.get(t.id, []),
                        )


def load(path: Path) -> Corpus:
    """Parse a corpus.yaml file into a Corpus."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    cfg_raw = raw["config"]
    cfg = Config(
        trials_per_cell=int(cfg_raw["trials_per_cell"]),
        arms=list(cfg_raw["arms"]),
        workspace_root=str(cfg_raw["workspace_root"]),
    )
    targets = [
        Target(id=t["id"], path=t["path"], description=t["description"]) for t in raw["targets"]
    ]
    questions = []
    for q in raw["questions"]:
        scope = q.get("scope", "per_repo")
        if scope not in ALLOWED_SCOPES:
            raise ValueError(
                f"question {q['id']!r}: scope must be one of "
                f"{sorted(ALLOWED_SCOPES)} (got {scope!r})"
            )
        questions.append(
            Question(
                id=q["id"],
                type=q["type"],
                scope=scope,
                template=q["template"],
                expected_evidence=dict(q.get("expected_evidence", {})),
            )
        )
    return Corpus(
        version=int(raw["corpus_version"]),
        config=cfg,
        targets=targets,
        questions=questions,
    )
