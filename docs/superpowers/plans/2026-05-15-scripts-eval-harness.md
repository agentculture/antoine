# scripts-eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `experiments/scripts_eval/` harness that runs an A/C subagent comparison of the `repo-map` skill, with three-layer scoring (mechanical via hooks, code-validation, pairwise blind LLM judge) and a generated `REPORT.md` per run.

**Architecture:** A small set of single-responsibility Python scripts under `experiments/scripts_eval/`, plus three Claude Code hook scripts that feed mechanical metrics from real subagent dispatches. Hooks are env-var-gated so they no-op outside an active eval session. Per-cell JSON is the lingua franca between scripts; `report.py` rolls everything up. Corpus + procedure live in `corpus.yaml` + `RUNBOOK.md`; both are operator-editable so the harness is repeatable on new repos.

**Tech Stack:** Python 3.12, `pyyaml` (already in deps), `anthropic` SDK (new, in `experiments` dep group), `pytest` + `pytest-xdist` for tests, Claude Code hooks (`PreToolUse` / `PostToolUse` / `SubagentStop`).

**Spec:** `docs/superpowers/specs/2026-05-15-scripts-eval-harness-design.md`. Read it before starting any task — every decision below traces back to a section there.

---

## Phase 0 — Scaffolding and dependencies

### Task 0.1: Create the experiments/scripts_eval/ skeleton

**Files:**
- Create: `experiments/__init__.py` (empty)
- Create: `experiments/scripts_eval/__init__.py` (empty)
- Create: `experiments/scripts_eval/hooks/__init__.py` (empty)
- Create: `experiments/scripts_eval/results/.gitkeep` (empty)
- Create: `experiments/scripts_eval/README.md` (stub — full content lands in Phase 9)
- Create: `tests/scripts_eval/__init__.py` (empty)
- Create: `tests/scripts_eval/fixtures/.gitkeep` (empty)
- Modify: `.gitignore`

- [ ] **Step 1: Create empty package markers and result-dir keep file**

```bash
mkdir -p experiments/scripts_eval/hooks experiments/scripts_eval/results
mkdir -p tests/scripts_eval/fixtures
touch experiments/__init__.py
touch experiments/scripts_eval/__init__.py
touch experiments/scripts_eval/hooks/__init__.py
touch experiments/scripts_eval/results/.gitkeep
touch tests/scripts_eval/__init__.py
touch tests/scripts_eval/fixtures/.gitkeep
```

- [ ] **Step 2: Write README stub**

Create `experiments/scripts_eval/README.md`:

```markdown
# scripts-eval

A/C subagent comparison harness for the `repo-map` skill.

This is a stub. Full README lands once the harness is wired.

See `docs/superpowers/specs/2026-05-15-scripts-eval-harness-design.md`
for the design and `RUNBOOK.md` (once written) for the operator
procedure.
```

- [ ] **Step 3: Add results/ contents to .gitignore (everything except .gitkeep)**

Append to `.gitignore`:

```
# scripts-eval results — runs are local artefacts, not checked in.
experiments/scripts_eval/results/*
!experiments/scripts_eval/results/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add experiments tests/scripts_eval .gitignore
git commit -m "scripts-eval: scaffold experiments/ + tests/ dirs"
```

---

### Task 0.2: Add the `experiments` dep group with anthropic SDK

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add experiments dep group**

In `pyproject.toml`, in `[dependency-groups]`, add a new group after `dev`:

```toml
experiments = [
    "anthropic>=0.40",
    "jsonschema>=4.20",
]
```

(`jsonschema` validates corpus.yaml; `anthropic` is the judge SDK.)

- [ ] **Step 2: Resolve and lock**

Run: `uv sync --group experiments`
Expected: `Resolved N packages` then `Installed M packages`. No errors.

- [ ] **Step 3: Verify import works**

Run: `uv run --group experiments python -c "import anthropic; import jsonschema; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "scripts-eval: add experiments dep group (anthropic, jsonschema)"
```

---

## Phase 1 — Shared I/O helpers

### Task 1.1: Implement `_io.py` (paths, env-var lookup, JSON read/write)

**Files:**
- Create: `experiments/scripts_eval/_io.py`
- Test: `tests/scripts_eval/test_io.py`

- [ ] **Step 1: Write failing test for env-var helpers**

Create `tests/scripts_eval/test_io.py`:

```python
"""Tests for experiments.scripts_eval._io shared helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from experiments.scripts_eval import _io


def test_eval_run_id_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "2026-05-15-run-01")
    assert _io.eval_run_id() == "2026-05-15-run-01"


def test_eval_run_id_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("SEER_EVAL_RUN_ID", raising=False)
    assert _io.eval_run_id() is None


def test_eval_arm_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("SEER_EVAL_ARM", "C")
    assert _io.eval_arm() == "C"


def test_eval_arm_rejects_invalid(monkeypatch):
    monkeypatch.setenv("SEER_EVAL_ARM", "Q")
    with pytest.raises(ValueError, match="SEER_EVAL_ARM must be 'A' or 'C'"):
        _io.eval_arm()


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
```

- [ ] **Step 2: Run test to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_io.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experiments.scripts_eval._io'`

- [ ] **Step 3: Implement `_io.py`**

Create `experiments/scripts_eval/_io.py`:

```python
"""Shared I/O helpers for the scripts-eval harness.

All paths resolve relative to the seer-cli repo root, so scripts work
regardless of cwd. Env-var helpers return None when unset rather than
raising — call sites decide whether the absence is fatal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "experiments" / "scripts_eval" / "results"
RAW_DIRNAME = "raw"


def eval_run_id() -> str | None:
    """Return SEER_EVAL_RUN_ID, or None if unset.

    Hooks read this first and no-op when None.
    """
    val = os.environ.get("SEER_EVAL_RUN_ID")
    return val if val else None


def eval_arm() -> str | None:
    """Return SEER_EVAL_ARM (must be 'A' or 'C'), or None if unset."""
    val = os.environ.get("SEER_EVAL_ARM")
    if val is None or val == "":
        return None
    if val not in ("A", "C"):
        raise ValueError(
            f"SEER_EVAL_ARM must be 'A' or 'C' (got {val!r})"
        )
    return val


def run_dir(run_id: str) -> Path:
    """Path to a specific run's results directory."""
    return REPO_ROOT / "experiments" / "scripts_eval" / "results" / run_id


def raw_dir(run_id: str) -> Path:
    """Path where hooks write their raw per-subagent JSONLs."""
    return run_dir(run_id) / RAW_DIRNAME


def arm_dir(run_id: str, arm: str) -> Path:
    """Path where capture.py writes per-cell JSONs for one arm."""
    return run_dir(run_id) / f"arm-{arm}"


def write_json(path: Path, data) -> None:
    """Write *data* as pretty JSON, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")


def read_json(path: Path):
    """Read JSON from *path*."""
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_io.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/scripts_eval/_io.py tests/scripts_eval/test_io.py
git commit -m "scripts-eval: shared I/O helpers (env vars, paths, json)"
```

---

## Phase 2 — Corpus loader

### Task 2.1: Implement `corpus.py` to parse and iterate corpus.yaml

**Files:**
- Create: `experiments/scripts_eval/corpus.py`
- Test: `tests/scripts_eval/test_corpus.py`
- Test fixture: `tests/scripts_eval/fixtures/corpus_minimal.yaml`

- [ ] **Step 1: Write the test fixture**

Create `tests/scripts_eval/fixtures/corpus_minimal.yaml`:

```yaml
corpus_version: 1
config:
  trials_per_cell: 3
  arms: [A, C]
  workspace_root: /home/spark/git
targets:
  - id: culture
    path: /home/spark/git/culture
    description: Async Python IRCd
  - id: daria
    path: /home/spark/git/daria
    description: Awareness agent
questions:
  - id: q-profile-overview
    type: profile
    scope: per_repo
    template: |
      Overview the repo at {repo_path}.
    expected_evidence:
      culture: [pyproject.toml, "uv sync"]
      daria: [pyproject.toml, awareness]
  - id: q-graph-workspace
    type: graph
    scope: workspace
    template: |
      Map the repos in {workspace_root}.
    expected_evidence:
      _global: [agentculture, culture]
```

- [ ] **Step 2: Write failing tests**

Create `tests/scripts_eval/test_corpus.py`:

```python
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
    cells = [
        cell for cell in c.iter_cells(arm="A")
        if cell.question_id == "q-profile-overview"
    ]
    # 2 repos × 3 trials = 6
    assert len(cells) == 6
    assert {cell.repo_id for cell in cells} == {"culture", "daria"}
    assert sorted({cell.trial for cell in cells}) == [1, 2, 3]


def test_iter_cells_workspace_question_yields_one_per_trial_only():
    c = corpus.load(FIXTURE)
    cells = [
        cell for cell in c.iter_cells(arm="C")
        if cell.question_id == "q-graph-workspace"
    ]
    # workspace scope: 1 cell per trial
    assert len(cells) == 3
    assert all(cell.repo_id is None for cell in cells)


def test_cell_carries_substituted_prompt():
    c = corpus.load(FIXTURE)
    cell = next(
        cell for cell in c.iter_cells(arm="A")
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
```

- [ ] **Step 3: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `corpus.py`**

Create `experiments/scripts_eval/corpus.py`:

```python
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
                    prompt = q.template.format(
                        workspace_root=self.config.workspace_root
                    )
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
        Target(id=t["id"], path=t["path"], description=t["description"])
        for t in raw["targets"]
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
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_corpus.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add experiments/scripts_eval/corpus.py tests/scripts_eval/test_corpus.py tests/scripts_eval/fixtures/corpus_minimal.yaml
git commit -m "scripts-eval: corpus.yaml loader + per-cell iterator"
```

---

## Phase 3 — Hooks

> **Pre-flight:** Read the Claude Code hooks docs section in `~/.claude/CLAUDE.md` (or the official docs) to confirm the hook payload schema. The plan below assumes:
> - All hooks receive a JSON object on stdin with at least `session_id`, `transcript_path`, `cwd`, `hook_event_name`.
> - `PreToolUse` / `PostToolUse` add `tool_name` and `tool_input` (Pre) plus `tool_response` (Post).
> - `SubagentStop` includes `transcript_path`.
>
> If the actual schema differs, update the implementations and tests below to match before writing the impl. The structure of the tasks (TDD, JSONL output) does not change.

### Task 3.1: `pre_tool.py` — record dispatch start time and prompt

**Files:**
- Create: `experiments/scripts_eval/hooks/pre_tool.py`
- Test: `tests/scripts_eval/test_hooks_pre_tool.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scripts_eval/test_hooks_pre_tool.py`:

```python
"""Tests for the PreToolUse hook (Agent dispatch start)."""
from __future__ import annotations

import json
from pathlib import Path

from experiments.scripts_eval.hooks import pre_tool


def _payload(tool_name="Agent", prompt="explain X"):
    return {
        "session_id": "sess-abc",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/home/spark/git/seer-cli",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {
            "subagent_type": "Explore",
            "description": "test cell",
            "prompt": prompt,
        },
    }


def test_no_op_when_run_id_unset(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SEER_EVAL_RUN_ID", raising=False)
    monkeypatch.setattr(pre_tool._io, "REPO_ROOT", tmp_path)
    rc = pre_tool.run(_payload(), now=lambda: 1700000000.0)
    assert rc == 0
    raw = tmp_path / "experiments" / "scripts_eval" / "results"
    assert not raw.exists()  # nothing written


def test_no_op_when_tool_not_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "A")
    monkeypatch.setattr(pre_tool._io, "REPO_ROOT", tmp_path)
    rc = pre_tool.run(_payload(tool_name="Bash"), now=lambda: 1700000000.0)
    assert rc == 0
    assert not (tmp_path / "experiments" / "scripts_eval" / "results" / "r1").exists()


def test_writes_jsonl_for_agent_dispatch(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "C")
    monkeypatch.setattr(pre_tool._io, "REPO_ROOT", tmp_path)

    rc = pre_tool.run(_payload(prompt="overview the culture repo"),
                      now=lambda: 1700000000.0)
    assert rc == 0
    raw_dir = tmp_path / "experiments" / "scripts_eval" / "results" / "r1" / "raw"
    files = sorted(raw_dir.glob("*.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text().splitlines()[0])
    assert line["event"] == "pre_tool"
    assert line["arm"] == "C"
    assert line["run_id"] == "r1"
    assert line["agent_type"] == "Explore"
    assert line["prompt"] == "overview the culture repo"
    assert line["start_time"] == 1700000000.0
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_hooks_pre_tool.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pre_tool.py`**

Create `experiments/scripts_eval/hooks/pre_tool.py`:

```python
#!/usr/bin/env python3
"""PreToolUse hook: stamps Agent dispatches into the run's raw/ JSONL.

No-op when SEER_EVAL_RUN_ID is unset, so day-to-day seer-cli sessions
are unaffected. Each Agent dispatch becomes one JSONL file under
results/<run_id>/raw/<subagent_id>.jsonl with a single 'pre_tool' line;
PostToolUse and SubagentStop append to the same file.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

from experiments.scripts_eval import _io


def _subagent_id(run_id: str, arm: str) -> str:
    """Synthesise a unique id for this subagent dispatch."""
    return f"{run_id}-{arm}-{uuid.uuid4().hex[:8]}"


def run(payload: dict, now: Callable[[], float] = time.time) -> int:
    run_id = _io.eval_run_id()
    if not run_id:
        return 0
    if payload.get("tool_name") != "Agent":
        return 0
    arm = _io.eval_arm() or "?"
    sid = _subagent_id(run_id, arm)
    tool_input = payload.get("tool_input", {}) or {}
    record = {
        "event": "pre_tool",
        "subagent_id": sid,
        "run_id": run_id,
        "arm": arm,
        "session_id": payload.get("session_id"),
        "transcript_path": payload.get("transcript_path"),
        "agent_type": tool_input.get("subagent_type"),
        "description": tool_input.get("description"),
        "prompt": tool_input.get("prompt"),
        "start_time": now(),
    }
    out_path = _io.raw_dir(run_id) / f"{sid}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record) + "\n")
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    return run(payload)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_hooks_pre_tool.py -v`
Expected: 3 passed.

- [ ] **Step 5: Make the script executable**

```bash
chmod +x experiments/scripts_eval/hooks/pre_tool.py
```

- [ ] **Step 6: Commit**

```bash
git add experiments/scripts_eval/hooks/pre_tool.py tests/scripts_eval/test_hooks_pre_tool.py
git commit -m "scripts-eval: PreToolUse hook records Agent dispatch start"
```

---

### Task 3.2: `post_tool.py` — append every tool call from a subagent

**Files:**
- Create: `experiments/scripts_eval/hooks/post_tool.py`
- Test: `tests/scripts_eval/test_hooks_post_tool.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scripts_eval/test_hooks_post_tool.py`:

```python
"""Tests for the PostToolUse hook (per-tool log, only inside subagents)."""
from __future__ import annotations

import json
from pathlib import Path

from experiments.scripts_eval.hooks import post_tool


def _payload(tool_name="Bash", session_id="sess-abc", input_=None):
    return {
        "session_id": session_id,
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/home/spark/git/seer-cli",
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": input_ or {"command": "ls"},
        "tool_response": {"stdout": "...", "exit_code": 0},
    }


def _seed_pre(tmp_path, sid, session_id="sess-abc"):
    """Drop a pre_tool jsonl line so post_tool can find it."""
    raw = tmp_path / "experiments" / "scripts_eval" / "results" / "r1" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    fp = raw / f"{sid}.jsonl"
    fp.write_text(json.dumps({
        "event": "pre_tool", "subagent_id": sid, "run_id": "r1",
        "session_id": session_id,
    }) + "\n")
    return fp


def test_no_op_when_run_id_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("SEER_EVAL_RUN_ID", raising=False)
    monkeypatch.setattr(post_tool._io, "REPO_ROOT", tmp_path)
    rc = post_tool.run(_payload(), now=lambda: 1700000010.0)
    assert rc == 0


def test_appends_to_open_subagent_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "C")
    monkeypatch.setattr(post_tool._io, "REPO_ROOT", tmp_path)
    sid = "r1-C-deadbeef"
    fp = _seed_pre(tmp_path, sid)

    rc = post_tool.run(
        _payload(tool_name="Bash",
                 input_={"command": "scripts/profile.sh /tmp/x"}),
        now=lambda: 1700000010.0,
    )
    assert rc == 0
    lines = fp.read_text().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[1])
    assert record["event"] == "post_tool"
    assert record["tool_name"] == "Bash"
    assert "scripts/profile.sh" in record["args_summary"]
    assert record["ts"] == 1700000010.0


def test_no_open_subagent_means_no_op(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "A")
    monkeypatch.setattr(post_tool._io, "REPO_ROOT", tmp_path)
    rc = post_tool.run(_payload(), now=lambda: 1700000010.0)
    assert rc == 0  # silently skip; no raw dir, no file
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_hooks_post_tool.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `post_tool.py`**

Create `experiments/scripts_eval/hooks/post_tool.py`:

```python
#!/usr/bin/env python3
"""PostToolUse hook: appends each subagent tool call to its raw JSONL.

Identifies the in-flight subagent by matching session_id against the
most-recent pre_tool record in the run's raw/ dir. If no pre_tool is
open (e.g. a top-level operator call), no-op.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable

from experiments.scripts_eval import _io

# Args-summary truncation limit (chars). Keeps logs readable; full args
# live in the transcript if a deep dive is needed.
ARGS_MAX_LEN = 200


def _summarise_args(tool_input: dict) -> str:
    """Compact one-line summary of a tool input dict."""
    if not isinstance(tool_input, dict):
        return ""
    # Common keys: command, file_path, pattern, prompt; fall back to repr.
    for key in ("command", "file_path", "pattern", "prompt", "url"):
        if key in tool_input and isinstance(tool_input[key], str):
            return tool_input[key][:ARGS_MAX_LEN]
    s = json.dumps(tool_input, separators=(",", ":"))
    return s[:ARGS_MAX_LEN]


def _find_open_subagent(run_id: str, session_id: str) -> Path | None:
    """Return the raw JSONL of the most-recent pre_tool with this session_id.

    Returns None if no match (this is a top-level call, not a subagent).
    """
    raw = _io.raw_dir(run_id)
    if not raw.exists():
        return None
    matches = []
    for fp in raw.glob("*.jsonl"):
        try:
            first = fp.read_text(encoding="utf-8").splitlines()[0]
            rec = json.loads(first)
        except (OSError, ValueError, IndexError):
            continue
        if rec.get("event") == "pre_tool" and rec.get("session_id") == session_id:
            matches.append((fp.stat().st_mtime, fp))
    if not matches:
        return None
    matches.sort()
    return matches[-1][1]


def run(payload: dict, now: Callable[[], float] = time.time) -> int:
    run_id = _io.eval_run_id()
    if not run_id:
        return 0
    session_id = payload.get("session_id")
    if not session_id:
        return 0
    fp = _find_open_subagent(run_id, session_id)
    if fp is None:
        return 0
    record = {
        "event": "post_tool",
        "tool_name": payload.get("tool_name"),
        "args_summary": _summarise_args(payload.get("tool_input", {})),
        "ts": now(),
    }
    with fp.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    return run(payload)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_hooks_post_tool.py -v`
Expected: 3 passed.

- [ ] **Step 5: Make executable + commit**

```bash
chmod +x experiments/scripts_eval/hooks/post_tool.py
git add experiments/scripts_eval/hooks/post_tool.py tests/scripts_eval/test_hooks_post_tool.py
git commit -m "scripts-eval: PostToolUse hook logs each subagent tool call"
```

---

### Task 3.3: `subagent_stop.py` — finalise duration, model, usage, final_text

**Files:**
- Create: `experiments/scripts_eval/hooks/subagent_stop.py`
- Test: `tests/scripts_eval/test_hooks_subagent_stop.py`
- Test fixture: `tests/scripts_eval/fixtures/transcript_min.jsonl`

- [ ] **Step 1: Write the transcript fixture**

Create `tests/scripts_eval/fixtures/transcript_min.jsonl`. Each line is one transcript entry; the structure here matches the Claude Code transcript format (assistant entries carry `usage` and `model`):

```jsonl
{"type": "user", "ts": 1700000005.0, "content": "explain X"}
{"type": "assistant", "ts": 1700000050.0, "model": "claude-opus-4-7", "usage": {"input_tokens": 1200, "output_tokens": 340, "cache_read_input_tokens": 800, "cache_creation_input_tokens": 100}, "content": "Here is the explanation: ...\n### tools_used\n- Bash: 2\n### evidence\n- /tmp/x/pyproject.toml"}
```

- [ ] **Step 2: Write failing tests**

Create `tests/scripts_eval/test_hooks_subagent_stop.py`:

```python
"""Tests for the SubagentStop hook."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from experiments.scripts_eval.hooks import subagent_stop

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _seed_pre(tmp_path, sid, session_id, transcript_path, start_time=1700000000.0):
    raw = tmp_path / "experiments" / "scripts_eval" / "results" / "r1" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    fp = raw / f"{sid}.jsonl"
    fp.write_text(json.dumps({
        "event": "pre_tool", "subagent_id": sid, "run_id": "r1",
        "session_id": session_id, "transcript_path": str(transcript_path),
        "start_time": start_time,
    }) + "\n")
    return fp


def test_no_op_when_run_id_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("SEER_EVAL_RUN_ID", raising=False)
    monkeypatch.setattr(subagent_stop._io, "REPO_ROOT", tmp_path)
    rc = subagent_stop.run({"session_id": "x", "transcript_path": "/tmp/t"},
                           now=lambda: 1700000060.0)
    assert rc == 0


def test_appends_stop_record_with_duration_model_usage(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setenv("SEER_EVAL_ARM", "A")
    monkeypatch.setattr(subagent_stop._io, "REPO_ROOT", tmp_path)

    transcript = tmp_path / "transcript.jsonl"
    shutil.copy(FIXTURE_DIR / "transcript_min.jsonl", transcript)

    sid = "r1-A-feedface"
    fp = _seed_pre(tmp_path, sid, "sess-1", transcript, start_time=1700000005.0)

    rc = subagent_stop.run(
        {"session_id": "sess-1", "transcript_path": str(transcript)},
        now=lambda: 1700000060.0,
    )
    assert rc == 0

    lines = fp.read_text().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[1])
    assert rec["event"] == "subagent_stop"
    assert rec["model"] == "claude-opus-4-7"
    assert rec["usage"]["input_tokens"] == 1200
    assert rec["usage"]["output_tokens"] == 340
    assert rec["usage"]["cache_read_input_tokens"] == 800
    assert rec["usage"]["cache_creation_input_tokens"] == 100
    assert rec["duration_seconds"] == 55.0
    assert "Here is the explanation" in rec["final_text"]


def test_no_pre_record_means_no_op(monkeypatch, tmp_path):
    monkeypatch.setenv("SEER_EVAL_RUN_ID", "r1")
    monkeypatch.setattr(subagent_stop._io, "REPO_ROOT", tmp_path)
    transcript = tmp_path / "t.jsonl"
    shutil.copy(FIXTURE_DIR / "transcript_min.jsonl", transcript)
    rc = subagent_stop.run(
        {"session_id": "no-such-session", "transcript_path": str(transcript)},
        now=lambda: 1700000060.0,
    )
    assert rc == 0
```

- [ ] **Step 3: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_hooks_subagent_stop.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Implement `subagent_stop.py`**

Create `experiments/scripts_eval/hooks/subagent_stop.py`:

```python
#!/usr/bin/env python3
"""SubagentStop hook: finalises the subagent's raw JSONL.

Reads the transcript path from the payload, finds the assistant
message(s) belonging to this subagent (by start_time stamped in
pre_tool), extracts the last usage block, and appends one
'subagent_stop' record with duration, model, usage, final_text.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable

from experiments.scripts_eval import _io


def _find_pre_record(run_id: str, session_id: str) -> tuple[Path, dict] | None:
    """Locate this subagent's raw JSONL + its pre_tool record."""
    raw = _io.raw_dir(run_id)
    if not raw.exists():
        return None
    matches = []
    for fp in raw.glob("*.jsonl"):
        try:
            first = fp.read_text(encoding="utf-8").splitlines()[0]
            rec = json.loads(first)
        except (OSError, ValueError, IndexError):
            continue
        if rec.get("event") == "pre_tool" and rec.get("session_id") == session_id:
            matches.append((fp.stat().st_mtime, fp, rec))
    if not matches:
        return None
    matches.sort()
    _, fp, rec = matches[-1]
    return fp, rec


def _last_assistant_after(transcript_path: Path, start_time: float) -> dict | None:
    """Return the last assistant message with ts > start_time, or None."""
    if not transcript_path.exists():
        return None
    last = None
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        ts = entry.get("ts")
        if ts is None or ts <= start_time:
            continue
        last = entry
    return last


def run(payload: dict, now: Callable[[], float] = time.time) -> int:
    run_id = _io.eval_run_id()
    if not run_id:
        return 0
    session_id = payload.get("session_id")
    transcript_path = Path(payload.get("transcript_path") or "")
    if not session_id or not str(transcript_path):
        return 0
    found = _find_pre_record(run_id, session_id)
    if found is None:
        return 0
    fp, pre = found
    start_time = float(pre.get("start_time", 0.0))
    end_time = now()
    last = _last_assistant_after(transcript_path, start_time)
    record = {
        "event": "subagent_stop",
        "end_time": end_time,
        "duration_seconds": round(end_time - start_time, 3),
        "model": (last or {}).get("model"),
        "usage": (last or {}).get("usage", {}),
        "final_text": (last or {}).get("content", ""),
    }
    with fp.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record) + "\n")
    return 0


def main() -> int:
    payload = json.load(sys.stdin)
    return run(payload)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_hooks_subagent_stop.py -v`
Expected: 3 passed.

- [ ] **Step 6: Make executable + commit**

```bash
chmod +x experiments/scripts_eval/hooks/subagent_stop.py
git add experiments/scripts_eval/hooks/subagent_stop.py tests/scripts_eval/test_hooks_subagent_stop.py tests/scripts_eval/fixtures/transcript_min.jsonl
git commit -m "scripts-eval: SubagentStop hook finalises raw JSONL with usage"
```

---

## Phase 4 — settings.json hook wiring + manual smoke test

### Task 4.1: Wire hooks into `.claude/settings.json` and smoke-test

**Files:**
- Create: `.claude/settings.json`

- [ ] **Step 1: Create `.claude/settings.json` with hook config**

Create `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --group experiments python -m experiments.scripts_eval.hooks.pre_tool"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --group experiments python -m experiments.scripts_eval.hooks.post_tool"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run --group experiments python -m experiments.scripts_eval.hooks.subagent_stop"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Smoke-test (manual, before commit)**

In a new shell from the seer-cli repo root:

```bash
export SEER_EVAL_RUN_ID=smoke-test-01
export SEER_EVAL_ARM=A
# Start a new claude code session in this shell and dispatch one
# Explore subagent with prompt "List the files in /tmp" or similar.
# After the subagent finishes, check:
ls experiments/scripts_eval/results/smoke-test-01/raw/
# Expect: at least one *.jsonl file with three lines (pre_tool,
# at least one post_tool, subagent_stop). Inspect with:
cat experiments/scripts_eval/results/smoke-test-01/raw/*.jsonl
```

If the file is missing or malformed, fix the hooks before continuing. Likely failure modes: hook command path wrong, env vars not exported, JSON parse error in stdin. (`uv run` should resolve the venv automatically.)

- [ ] **Step 3: Clean up the smoke-test results**

```bash
rm -rf experiments/scripts_eval/results/smoke-test-01
```

- [ ] **Step 4: Commit settings.json**

```bash
git add .claude/settings.json
git commit -m "scripts-eval: wire hooks into .claude/settings.json (env-gated)"
```

---

## Phase 5 — Capture: raw JSONL → per-cell JSON

### Task 5.1: Implement `capture.py`

**Files:**
- Create: `experiments/scripts_eval/capture.py`
- Test: `tests/scripts_eval/test_capture.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scripts_eval/test_capture.py`:

```python
"""Tests for capture.py — rolls raw hook JSONL into per-cell JSON."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.scripts_eval import _io, capture


def _seed_raw(run_dir: Path, sid: str, lines: list[dict]) -> Path:
    raw = run_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    fp = raw / f"{sid}.jsonl"
    fp.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
    return fp


def test_capture_one_complete_subagent(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    run_id = "r1"
    rd = _io.run_dir(run_id)
    rd.mkdir(parents=True)
    sid = "r1-C-deadbeef"
    _seed_raw(rd, sid, [
        {"event": "pre_tool", "subagent_id": sid, "run_id": "r1", "arm": "C",
         "session_id": "sess-1",
         "agent_type": "Explore",
         "prompt": "overview the culture repo",
         "start_time": 1700000000.0},
        {"event": "post_tool", "tool_name": "Bash",
         "args_summary": "scripts/profile.sh /tmp/x", "ts": 1700000005.0},
        {"event": "post_tool", "tool_name": "Read",
         "args_summary": "/tmp/x/README.md", "ts": 1700000010.0},
        {"event": "subagent_stop", "end_time": 1700000050.0,
         "duration_seconds": 50.0, "model": "claude-opus-4-7",
         "usage": {"input_tokens": 1200, "output_tokens": 340,
                   "cache_read_input_tokens": 800,
                   "cache_creation_input_tokens": 100},
         "final_text": "answer text"},
    ])
    cells = capture.process_run(run_id, repo_id="culture",
                                question_id="q-profile-overview", trial=1)
    # process_run picks up unprocessed raw files and assigns them in order
    assert len(cells) == 1
    cell = cells[0]
    assert cell["arm"] == "C"
    assert cell["repo_id"] == "culture"
    assert cell["question_id"] == "q-profile-overview"
    assert cell["trial"] == 1
    assert cell["subagent"]["model"] == "claude-opus-4-7"
    assert cell["subagent"]["duration_seconds"] == 50.0
    assert cell["subagent"]["tokens"]["input"] == 1200
    tools = {t["name"]: t for t in cell["subagent"]["tools_used"]}
    assert tools["Bash"]["count"] == 1
    assert tools["Read"]["count"] == 1
    assert "scripts/profile.sh" in tools["Bash"]["patterns"]
    assert cell["answer_text"] == "answer text"

    # Per-cell JSON written under arm-C/
    written = list((rd / "arm-C").glob("*.json"))
    assert len(written) == 1


def test_capture_skips_incomplete_subagent(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    run_id = "r1"
    rd = _io.run_dir(run_id)
    rd.mkdir(parents=True)
    sid = "r1-A-incomplete"
    # Pre + post only, no stop yet.
    _seed_raw(rd, sid, [
        {"event": "pre_tool", "subagent_id": sid, "run_id": "r1", "arm": "A",
         "session_id": "x",
         "agent_type": "Explore",
         "prompt": "p",
         "start_time": 1.0},
        {"event": "post_tool", "tool_name": "Read",
         "args_summary": "/tmp/x", "ts": 2.0},
    ])
    cells = capture.process_run(run_id, repo_id="culture",
                                question_id="q1", trial=1)
    assert cells == []  # incomplete: skipped, will be picked up next pass
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_capture.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `capture.py`**

Create `experiments/scripts_eval/capture.py`:

```python
"""capture.py — fold raw hook JSONLs into per-cell JSON records.

Operator workflow:
  python -m experiments.scripts_eval.capture --run <id> \\
      --repo <repo_id> --question <qid> --trial <n>

Pairs the next unprocessed raw/<sid>.jsonl with the (repo, question,
trial) the operator just dispatched. The mapping is operator-driven
(the hooks don't know which corpus row triggered them) — RUNBOOK.md
makes this explicit.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from experiments.scripts_eval import _io


def _read_raw(fp: Path) -> list[dict]:
    return [json.loads(ln) for ln in fp.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _is_complete(records: list[dict]) -> bool:
    events = {r.get("event") for r in records}
    return "pre_tool" in events and "subagent_stop" in events


def _mark_processed(fp: Path) -> None:
    """Rename raw/<sid>.jsonl → raw/<sid>.jsonl.done so we don't re-process."""
    fp.rename(fp.with_suffix(fp.suffix + ".done"))


def _aggregate_tools(records: Iterable[dict]) -> list[dict]:
    by_name: dict[str, dict] = defaultdict(lambda: {"count": 0, "patterns": []})
    for r in records:
        if r.get("event") != "post_tool":
            continue
        name = r.get("tool_name") or "Unknown"
        slot = by_name[name]
        slot["count"] += 1
        s = r.get("args_summary")
        if s:
            slot["patterns"].append(s)
    out = []
    for name, slot in by_name.items():
        out.append({
            "name": name,
            "count": slot["count"],
            "patterns": slot["patterns"][:10],  # cap
        })
    out.sort(key=lambda d: d["name"])
    return out


def build_cell(records: list[dict], *, repo_id: str | None, question_id: str,
               trial: int) -> dict:
    pre = next(r for r in records if r.get("event") == "pre_tool")
    stop = next(r for r in records if r.get("event") == "subagent_stop")
    usage = stop.get("usage", {}) or {}
    cell = {
        "run_id": pre.get("run_id"),
        "arm": pre.get("arm"),
        "repo_id": repo_id,
        "question_id": question_id,
        "trial": trial,
        "subagent": {
            "agent_type": pre.get("agent_type"),
            "model": stop.get("model"),
            "duration_seconds": stop.get("duration_seconds"),
            "tokens": {
                "input": usage.get("input_tokens", 0),
                "output": usage.get("output_tokens", 0),
                "cache_read": usage.get("cache_read_input_tokens", 0),
                "cache_creation": usage.get("cache_creation_input_tokens", 0),
            },
            "tools_used": _aggregate_tools(records),
        },
        "answer_text": stop.get("final_text", ""),
        "validation": None,
        "judge": None,
    }
    return cell


def process_run(run_id: str, *, repo_id: str | None, question_id: str,
                trial: int) -> list[dict]:
    """Process the next complete raw JSONL into a per-cell JSON.

    Returns the list of cells written this invocation (0 or 1 today;
    the list shape leaves room for batched processing later).
    """
    raw = _io.raw_dir(run_id)
    if not raw.exists():
        return []
    written = []
    for fp in sorted(raw.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        records = _read_raw(fp)
        if not _is_complete(records):
            continue
        cell = build_cell(records, repo_id=repo_id, question_id=question_id, trial=trial)
        suffix = repo_id or "_workspace_"
        out_path = _io.arm_dir(run_id, cell["arm"]) / f"{suffix}-{question_id}-t{trial}.json"
        _io.write_json(out_path, cell)
        _mark_processed(fp)
        written.append(cell)
        break  # one cell per invocation; operator controls pairing
    return written


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="capture")
    p.add_argument("--run", required=True)
    p.add_argument("--repo", required=False, default=None)
    p.add_argument("--question", required=True)
    p.add_argument("--trial", type=int, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cells = process_run(args.run, repo_id=args.repo,
                        question_id=args.question, trial=args.trial)
    if not cells:
        print(f"capture: no complete subagent JSONL found under run={args.run}")
        return 1
    print(f"capture: wrote {len(cells)} cell(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_capture.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/scripts_eval/capture.py tests/scripts_eval/test_capture.py
git commit -m "scripts-eval: capture rolls raw hook JSONL into per-cell JSON"
```

---

### Task 5.2: Implement `manifest.py` (per-run metadata)

**Files:**
- Create: `experiments/scripts_eval/manifest.py`
- Test: `tests/scripts_eval/test_manifest.py`

The spec calls for a `manifest.json` per run capturing `corpus_version`,
`models`, `date`, `env`, `operator`. The operator runs `manifest init`
once per arm session before the first capture; it is idempotent.

- [ ] **Step 1: Write failing tests**

Create `tests/scripts_eval/test_manifest.py`:

```python
"""Tests for manifest.py — per-run metadata writer."""
from __future__ import annotations

import json
from pathlib import Path

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
    a = manifest.init("r1", corpus_path=corpus_yaml,
                      operator_model="x", judge_model="y", rubric_version="v1",
                      now=lambda: "T1", git_sha=lambda: "s1", git_branch=lambda: "b1")
    b = manifest.init("r1", corpus_path=corpus_yaml,
                      operator_model="z", judge_model="z", rubric_version="v9",
                      now=lambda: "T2", git_sha=lambda: "s2", git_branch=lambda: "b2")
    # Second call returns the same path with the original content untouched.
    assert a == b
    data = json.loads(b.read_text())
    assert data["operator"]["model"] == "x"  # original
    assert data["started_at"] == "T1"
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_manifest.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `manifest.py`**

Create `experiments/scripts_eval/manifest.py`:

```python
"""manifest.py — per-run metadata, written once at the start of a run."""
from __future__ import annotations

import argparse
import datetime as dt
import platform
import subprocess
from pathlib import Path

import yaml

from experiments.scripts_eval import _io


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_io.REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=_io.REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _utcnow() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def init(run_id: str, *, corpus_path: Path, operator_model: str,
         judge_model: str, rubric_version: str,
         now=_utcnow, git_sha=_git_sha, git_branch=_git_branch) -> Path:
    """Write manifest.json idempotently. Return its path."""
    out = _io.run_dir(run_id) / "manifest.json"
    if out.exists():
        return out
    raw = yaml.safe_load(corpus_path.read_text(encoding="utf-8"))
    data = {
        "run_id": run_id,
        "started_at": now(),
        "corpus_version": int(raw.get("corpus_version", 0)),
        "corpus_path": str(corpus_path),
        "operator": {"model": operator_model},
        "judge_model": judge_model,
        "rubric_version": rubric_version,
        "env": {
            "git_sha": git_sha(),
            "git_branch": git_branch(),
            "platform": platform.system().lower(),
        },
    }
    _io.write_json(out, data)
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="manifest")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("init")
    pi.add_argument("--run", required=True)
    pi.add_argument("--corpus", default="experiments/scripts_eval/corpus.yaml")
    pi.add_argument("--operator-model", default="claude-opus-4-7")
    pi.add_argument("--judge-model", default="claude-opus-4-7")
    pi.add_argument("--rubric-version", default="v1")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    out = init(args.run, corpus_path=Path(args.corpus),
               operator_model=args.operator_model,
               judge_model=args.judge_model,
               rubric_version=args.rubric_version)
    print(f"manifest: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_manifest.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/scripts_eval/manifest.py tests/scripts_eval/test_manifest.py
git commit -m "scripts-eval: per-run manifest.json (corpus_version, env, models)"
```

---

## Phase 6 — Code-validation

### Task 6.1: Implement `validate.py`

**Files:**
- Create: `experiments/scripts_eval/validate.py`
- Test: `tests/scripts_eval/test_validate.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scripts_eval/test_validate.py`:

```python
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
    fp = _seed_cell(rd, "C", "culture-q1-t1.json", {
        "run_id": "r1", "arm": "C", "repo_id": "culture",
        "question_id": "q1", "trial": 1,
        "answer_text": "Look at pyproject.toml; run uv sync to install. The repo is an async IRCd.",
        "subagent": {}, "validation": None, "judge": None,
    })
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
    fp = _seed_cell(rd, "A", "_workspace_-q-graph-t1.json", {
        "run_id": "r1", "arm": "A", "repo_id": None,
        "question_id": "q-graph", "trial": 1,
        "answer_text": "AgentCulture cluster: culture, daria, steward.",
        "subagent": {}, "validation": None, "judge": None,
    })
    expected = {"q-graph": {"_global": ["AgentCulture", "culture", "missing-thing"]}}

    validate.process_run("r1", expected_evidence_by_q_repo=expected)

    cell = json.loads(fp.read_text())
    assert sorted(cell["validation"]["found"]) == ["AgentCulture", "culture"]
    assert cell["validation"]["missing"] == ["missing-thing"]
    assert cell["validation"]["score"] == pytest.approx(2/3, rel=1e-3)


def test_validate_supports_regex_form(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    fp = _seed_cell(rd, "C", "x-q1-t1.json", {
        "run_id": "r1", "arm": "C", "repo_id": "x",
        "question_id": "q1", "trial": 1,
        "answer_text": "version 0.42.7 ships",
        "subagent": {}, "validation": None, "judge": None,
    })
    expected = {"q1": {"x": ["/version \\d+\\.\\d+\\.\\d+/"]}}
    validate.process_run("r1", expected_evidence_by_q_repo=expected)
    cell = json.loads(fp.read_text())
    assert cell["validation"]["score"] == 1.0
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_validate.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `validate.py`**

Create `experiments/scripts_eval/validate.py`:

```python
"""validate.py — fills the 'validation' block on every per-cell JSON.

Each expected_evidence entry is either a substring (case-insensitive)
or a regex in /pattern/ form. score = len(found) / len(expected).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

from experiments.scripts_eval import _io, corpus


def _is_regex(item: str) -> bool:
    return len(item) >= 2 and item.startswith("/") and item.endswith("/")


def _matches(item: str, text: str) -> bool:
    if _is_regex(item):
        pattern = item[1:-1]
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return item.lower() in text.lower()


def _validate_one(cell: dict, expected: list[str]) -> dict:
    text = cell.get("answer_text", "") or ""
    found, missing = [], []
    for item in expected:
        (found if _matches(item, text) else missing).append(item)
    score = (len(found) / len(expected)) if expected else 1.0
    return {
        "expected_evidence": list(expected),
        "found": found,
        "missing": missing,
        "score": round(score, 4),
    }


def process_run(run_id: str, *, expected_evidence_by_q_repo: dict) -> list[dict]:
    """Walk arm-A/ and arm-C/ in this run, fill validation, write back.

    expected_evidence_by_q_repo maps {question_id: {repo_id_or_global: [items]}}.
    For workspace cells, repo_id is None; the loader uses '_global' as the key.
    """
    rd = _io.run_dir(run_id)
    out: list[dict] = []
    for arm in ("A", "C"):
        for fp in sorted((rd / f"arm-{arm}").glob("*.json")):
            cell = _io.read_json(fp)
            qid = cell["question_id"]
            key = cell.get("repo_id") or "_global"
            expected = (expected_evidence_by_q_repo.get(qid, {}) or {}).get(key, [])
            cell["validation"] = _validate_one(cell, expected)
            _io.write_json(fp, cell)
            out.append(cell)
    return out


def _expected_from_corpus(corpus_path: Path) -> dict:
    c = corpus.load(corpus_path)
    return {q.id: q.expected_evidence for q in c.questions}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="validate")
    p.add_argument("--run", required=True)
    p.add_argument("--corpus", default="experiments/scripts_eval/corpus.yaml")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    expected = _expected_from_corpus(Path(args.corpus))
    cells = process_run(args.run, expected_evidence_by_q_repo=expected)
    print(f"validate: scored {len(cells)} cell(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_validate.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/scripts_eval/validate.py tests/scripts_eval/test_validate.py
git commit -m "scripts-eval: validate adds expected-evidence recall scores"
```

---

## Phase 7 — LLM-as-judge

### Task 7.1: Implement `judge.py` with mocked Anthropic client

**Files:**
- Create: `experiments/scripts_eval/judge.py`
- Test: `tests/scripts_eval/test_judge.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scripts_eval/test_judge.py`:

```python
"""Tests for judge.py — pairwise blind LLM-as-judge."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

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
            "run_id": "r1", "arm": arm, "repo_id": repo,
            "question_id": qid, "trial": trial,
            "answer_text": f"answer from arm {arm}",
            "subagent": {}, "validation": {"score": 0.5}, "judge": None,
        }
        out = rd / f"arm-{arm}" / f"{repo}-{qid}-t{trial}.json"
        _io.write_json(out, cell)


def test_judge_writes_blind_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    _seed_pair(rd, "q1", "culture", 1)
    fake = _FakeClient(
        '{"winner": "X", "margin": "clear", "reasoning": "X is more concrete."}'
    )

    rng = random.Random(0)
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
    cell = {"run_id": "r1", "arm": "C", "repo_id": "culture",
            "question_id": "q1", "trial": 1,
            "answer_text": "x", "subagent": {}, "validation": None, "judge": None}
    _io.write_json(rd / "arm-C" / "culture-q1-t1.json", cell)
    fake = _FakeClient('{"winner":"X","margin":"tie","reasoning":""}')
    judge.process_run("r1", client=fake, rubric_text="r", rubric_version="v1",
                      judge_model="m", rng=random.Random(0))
    # Judge field still None — no pair.
    cell = _io.read_json(rd / "arm-C" / "culture-q1-t1.json")
    assert cell["judge"] is None
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_judge.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `judge.py`**

Create `experiments/scripts_eval/judge.py`:

```python
"""judge.py — pairwise blind LLM-as-judge over arm-A vs arm-C cells.

Pairs cells by (repo_id, question_id, trial). Within each pair, A and
C are randomly relabelled answer_X / answer_Y; the judge picks a
winner and margin without knowing which is which. The blinding map is
recorded in the cell's 'judge' block so downstream analysis can
de-blind.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path

from experiments.scripts_eval import _io


def _pair_key(cell: dict) -> tuple:
    return (cell.get("repo_id"), cell["question_id"], cell["trial"])


def _load_arm(rd: Path, arm: str) -> dict:
    out = {}
    for fp in (rd / f"arm-{arm}").glob("*.json"):
        cell = _io.read_json(fp)
        out[_pair_key(cell)] = (fp, cell)
    return out


PROMPT_TEMPLATE = """You are a blind judge comparing two answers to the same question.

Rubric:
{rubric}

Question:
{question}

answer_X:
{answer_x}

answer_Y:
{answer_y}

Respond with a single-line JSON object: {{"winner": "X" or "Y" or "tie", "margin": "tie" or "slight" or "clear" or "decisive", "reasoning": "one short sentence"}}.
"""


def _ask_judge(client, *, judge_model: str, rubric: str, question: str,
               answer_x: str, answer_y: str) -> dict:
    msg = client.messages.create(
        model=judge_model,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": PROMPT_TEMPLATE.format(
                rubric=rubric, question=question,
                answer_x=answer_x, answer_y=answer_y,
            ),
        }],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    # Extract the first JSON object from the response.
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"judge returned non-JSON: {text[:200]!r}")
    return json.loads(match.group(0))


def process_run(run_id: str, *, client, rubric_text: str, rubric_version: str,
                judge_model: str, rng: random.Random) -> int:
    """Score every (A, C) pair in this run; write judge block to both cells."""
    rd = _io.run_dir(run_id)
    a_by = _load_arm(rd, "A")
    c_by = _load_arm(rd, "C")
    pairs = sorted(set(a_by) & set(c_by))
    n = 0
    for key in pairs:
        a_fp, a_cell = a_by[key]
        c_fp, c_cell = c_by[key]
        # Random blind assignment.
        a_label = rng.choice(["answer_X", "answer_Y"])
        c_label = "answer_Y" if a_label == "answer_X" else "answer_X"
        ans_x = a_cell["answer_text"] if a_label == "answer_X" else c_cell["answer_text"]
        ans_y = c_cell["answer_text"] if c_label == "answer_Y" else a_cell["answer_text"]

        question = a_cell.get("question_text", "")  # may be empty in early rounds
        verdict = _ask_judge(client, judge_model=judge_model, rubric=rubric_text,
                             question=question, answer_x=ans_x, answer_y=ans_y)
        winner_label = verdict.get("winner")
        if winner_label == "X":
            winner = "A" if a_label == "answer_X" else "C"
        elif winner_label == "Y":
            winner = "A" if a_label == "answer_Y" else "C"
        else:
            winner = "tie"

        block = {
            "judge_model": judge_model,
            "rubric_version": rubric_version,
            "comparison": {
                "winner": winner,
                "margin": verdict.get("margin", "tie"),
                "reasoning": verdict.get("reasoning", ""),
                "blind_label_for_A": a_label,
                "blind_label_for_C": c_label,
            },
        }
        a_cell["judge"] = block
        c_cell["judge"] = block
        _io.write_json(a_fp, a_cell)
        _io.write_json(c_fp, c_cell)
        n += 1
    return n


def _make_client():
    import anthropic  # lazy import — the dep is in the experiments group
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="judge")
    p.add_argument("--run", required=True)
    p.add_argument("--rubric",
                   default="experiments/scripts_eval/judge_rubric.md")
    p.add_argument("--rubric-version", default="v1")
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--seed", type=int, default=0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    rubric = Path(args.rubric).read_text(encoding="utf-8")
    n = process_run(
        args.run,
        client=_make_client(),
        rubric_text=rubric,
        rubric_version=args.rubric_version,
        judge_model=args.model,
        rng=random.Random(args.seed),
    )
    print(f"judge: scored {n} pair(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_judge.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add experiments/scripts_eval/judge.py tests/scripts_eval/test_judge.py
git commit -m "scripts-eval: pairwise blind LLM-as-judge with seeded blinding"
```

---

## Phase 8 — Report

### Task 8.1: Implement `report.py`

**Files:**
- Create: `experiments/scripts_eval/report.py`
- Test: `tests/scripts_eval/test_report.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scripts_eval/test_report.py`:

```python
"""Tests for report.py — generate REPORT.md from a run dir."""
from __future__ import annotations

from pathlib import Path

from experiments.scripts_eval import _io, report

ARM_VIOLATIONS = ("scripts/profile.sh", "scripts/connections.sh",
                  "scripts/graph.sh", "seer.repo", "seer/repo")


def _seed(rd, arm, name, payload):
    out = rd / f"arm-{arm}" / name
    _io.write_json(out, payload)


def test_report_summarises_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(_io, "REPO_ROOT", tmp_path)
    rd = _io.run_dir("r1")
    rd.mkdir(parents=True)
    base = {
        "run_id": "r1", "repo_id": "culture", "question_id": "q1", "trial": 1,
        "subagent": {
            "model": "claude-opus-4-7", "duration_seconds": 30.0,
            "tokens": {"input": 1000, "output": 200, "cache_read": 500, "cache_creation": 50},
            "tools_used": [{"name": "Read", "count": 2, "patterns": ["a", "b"]}],
        },
        "validation": {"score": 0.75, "found": ["x"], "missing": ["y"], "expected_evidence": ["x", "y"]},
        "judge": {
            "judge_model": "claude-opus-4-7", "rubric_version": "v1",
            "comparison": {"winner": "C", "margin": "clear",
                           "reasoning": "more concrete",
                           "blind_label_for_A": "answer_X",
                           "blind_label_for_C": "answer_Y"},
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
        "run_id": "r1", "arm": "A", "repo_id": "culture",
        "question_id": "q1", "trial": 1,
        "subagent": {
            "model": "m", "duration_seconds": 1.0,
            "tokens": {"input": 1, "output": 1, "cache_read": 0, "cache_creation": 0},
            "tools_used": [
                {"name": "Bash", "count": 1, "patterns": ["scripts/profile.sh /tmp/x"]},
            ],
        },
        "validation": {"score": 1.0, "found": [], "missing": [], "expected_evidence": []},
        "judge": None,
        "answer_text": "x",
    }
    _seed(rd, "A", "culture-q1-t1.json", a_payload)

    out_path = report.write_report("r1")
    text = out_path.read_text(encoding="utf-8")
    assert "## Violations" in text
    assert "A_used_scripts" in text
    assert "culture / q1 / t1" in text
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `uv run pytest tests/scripts_eval/test_report.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `report.py`**

Create `experiments/scripts_eval/report.py`:

```python
"""report.py — roll a run directory up into a single REPORT.md."""
from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median

from experiments.scripts_eval import _io

VIOLATION_PATTERNS = (
    "scripts/profile.sh", "scripts/connections.sh", "scripts/graph.sh",
    "seer.repo", "seer/repo", "python -m seer",
)


def _arm_used_scripts(cell: dict) -> bool:
    for tool in cell.get("subagent", {}).get("tools_used", []) or []:
        for p in tool.get("patterns", []) or []:
            if any(v in p for v in VIOLATION_PATTERNS):
                return True
    return False


def _load(rd: Path) -> dict:
    by_pair = {}
    for arm in ("A", "C"):
        for fp in sorted((rd / f"arm-{arm}").glob("*.json")):
            cell = _io.read_json(fp)
            key = (cell.get("repo_id") or "_workspace_",
                   cell["question_id"], cell["trial"])
            by_pair.setdefault(key, {})[arm] = cell
    return by_pair


def _format_pair(key, pair: dict) -> str:
    repo, qid, trial = key
    a, c = pair.get("A"), pair.get("C")
    av = (a or {}).get("validation", {}) or {}
    cv = (c or {}).get("validation", {}) or {}
    parts = [f"### {repo} / {qid} / t{trial}"]
    if a and c:
        judge = a.get("judge") or c.get("judge") or {}
        cmp_ = judge.get("comparison", {}) or {}
        if cmp_:
            parts.append(f"Winner: **{cmp_.get('winner','?')}** "
                         f"({cmp_.get('margin','?')}) — {cmp_.get('reasoning','')}")
        parts.append(
            f"validation A={av.get('score','-')} / C={cv.get('score','-')}"
        )
        a_dur = (a.get("subagent") or {}).get("duration_seconds")
        c_dur = (c.get("subagent") or {}).get("duration_seconds")
        a_tok = ((a.get("subagent") or {}).get("tokens") or {}).get("input", 0) + \
                ((a.get("subagent") or {}).get("tokens") or {}).get("output", 0)
        c_tok = ((c.get("subagent") or {}).get("tokens") or {}).get("input", 0) + \
                ((c.get("subagent") or {}).get("tokens") or {}).get("output", 0)
        parts.append(f"duration A={a_dur}s / C={c_dur}s; total tokens A={a_tok} / C={c_tok}")
    elif a:
        parts.append("(no C cell)")
    elif c:
        parts.append("(no A cell)")
    return "\n".join(parts)


def _format_violations(by_pair: dict) -> list[str]:
    rows = []
    for (repo, qid, trial), pair in sorted(by_pair.items()):
        if "A" in pair and _arm_used_scripts(pair["A"]):
            rows.append(f"- A_used_scripts: {repo} / {qid} / t{trial}")
        if "C" in pair and not _arm_used_scripts(pair["C"]):
            rows.append(f"- C_did_not_use_scripts: {repo} / {qid} / t{trial}")
    return rows


def _aggregate(by_pair: dict) -> str:
    a_scores, c_scores, c_wins = [], [], 0
    for pair in by_pair.values():
        if "A" in pair and pair["A"].get("validation"):
            a_scores.append(pair["A"]["validation"]["score"])
        if "C" in pair and pair["C"].get("validation"):
            c_scores.append(pair["C"]["validation"]["score"])
        for arm in ("A", "C"):
            j = (pair.get(arm) or {}).get("judge") or {}
            cmp_ = j.get("comparison", {}) or {}
            if cmp_.get("winner") == "C":
                c_wins += 1
                break  # don't double-count the same pair
    lines = ["## Aggregate"]
    if a_scores:
        lines.append(f"- median validation A: {median(a_scores):.3f} (n={len(a_scores)})")
    if c_scores:
        lines.append(f"- median validation C: {median(c_scores):.3f} (n={len(c_scores)})")
    lines.append(f"- judge C wins: {c_wins}")
    return "\n".join(lines)


def write_report(run_id: str) -> Path:
    rd = _io.run_dir(run_id)
    by_pair = _load(rd)
    sections = [f"# scripts-eval — run `{run_id}`", "",
                _aggregate(by_pair), ""]
    violations = _format_violations(by_pair)
    if violations:
        sections.append("## Violations")
        sections.extend(violations)
        sections.append("")
    sections.append("## Per-cell")
    for key, pair in sorted(by_pair.items()):
        sections.append(_format_pair(key, pair))
        sections.append("")
    out = rd / "REPORT.md"
    out.write_text("\n".join(sections) + "\n", encoding="utf-8")
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="report")
    p.add_argument("--run", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    out = write_report(args.run)
    print(f"report: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm pass**

Run: `uv run pytest tests/scripts_eval/test_report.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run full eval test suite**

Run: `uv run pytest tests/scripts_eval/ -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add experiments/scripts_eval/report.py tests/scripts_eval/test_report.py
git commit -m "scripts-eval: report rolls a run dir up into REPORT.md"
```

---

## Phase 9 — Procedure docs

### Task 9.1: Write `judge_rubric.md`

**Files:**
- Create: `experiments/scripts_eval/judge_rubric.md`

- [ ] **Step 1: Write the rubric**

Create `experiments/scripts_eval/judge_rubric.md`:

```markdown
# Judge rubric (v1)

You are scoring one of two answers (`answer_X`, `answer_Y`) to the
same question. Both answers came from the same model under the same
prompt; one was equipped with a `repo-map` skill, the other was not.

Score on these dimensions, in priority order:

1. **Factual correctness.** Are the claims about the repo true?
   Penalise unsupported assertions, invented file paths, and wrong
   dependency names.
2. **Completeness vs. the question scope.** A "what is this repo"
   question should cover purpose, build/test, and top-level
   structure. A "what does this connect to" question should name the
   actual connections.
3. **Actionability.** If the asker is going to do something with the
   answer (port a CI pipeline, build a similar CLI), can they?
4. **Restraint.** Penalise irrelevant detail, repetition, and padding.

Pick a winner: `X`, `Y`, or `tie`. Pick a margin: `tie`, `slight`,
`clear`, `decisive`. Justify in **one short sentence** of reasoning —
the reasoning is for spot-check, not for the asker.

Output a single-line JSON object:

    {"winner": "X" | "Y" | "tie", "margin": "tie" | "slight" | "clear" | "decisive", "reasoning": "..."}

No prose outside the JSON.
```

- [ ] **Step 2: Commit**

```bash
git add experiments/scripts_eval/judge_rubric.md
git commit -m "scripts-eval: judge rubric v1"
```

---

### Task 9.2: Write `RUNBOOK.md`

**Files:**
- Create: `experiments/scripts_eval/RUNBOOK.md`

- [ ] **Step 1: Write the runbook**

Create `experiments/scripts_eval/RUNBOOK.md`:

````markdown
# scripts-eval RUNBOOK

This is the operator-facing procedure. It is followed by an
interactive Claude Code session ("operator-Claude"), arm at a time,
one cell at a time.

## Prerequisites

- `uv sync --group experiments` has run.
- `ANTHROPIC_API_KEY` is set in the operator's shell (for `judge.py`).
- `corpus.yaml` lists the targets and questions for this round.
- A run id is chosen, e.g. `2026-05-15-run-01`.

## One run = two operator sessions

Round 1 uses two distinct Claude Code sessions, one per arm:

| Arm | Skill state | Operator system prompt |
| --- | --- | --- |
| A   | `repo-map` skill **not loaded** in this session | "Dispatch only `Explore` subagents. In each subagent prompt, forbid the `repo-map` skill and the `seer.repo` / `scripts/*.sh` paths." |
| C   | `repo-map` skill **loaded** in this session | "Dispatch only `Explore` subagents. Each may use the `repo-map` skill and its scripts at its discretion." |

Both sessions export the same env vars before launching:

```bash
export SEER_EVAL_RUN_ID=2026-05-15-run-01
export SEER_EVAL_ARM=A   # or C in the other session
```

The hooks pick up these env vars; without them, hooks no-op.

Once per run (in either arm session — it is idempotent), write the
manifest:

```bash
uv run --group experiments python -m experiments.scripts_eval.manifest init \
    --run $SEER_EVAL_RUN_ID
```

## Per-cell loop (within an arm session)

For each `(repo_id or workspace, question_id, trial)` row in
`corpus.yaml` not yet present in this run's `arm-<X>/`:

1. Look up the question template in `corpus.yaml`. Substitute
   `{repo_path}` (per-repo) or `{workspace_root}` (workspace).
2. Dispatch one `Explore` subagent. Subagent prompt:

   ```
   <substituted question template>

   Constraints (verbatim):
   - <arm-specific restrictions, see table above>
   - After answering, append two sections and stop:
     ### tools_used
     - <ToolName>: <count>  (one line per distinct tool)
     ### evidence
     - <one path per line>
   ```
3. Wait for the subagent to finish. Hooks fire automatically.
4. Run capture:

   ```bash
   uv run --group experiments python -m experiments.scripts_eval.capture \
       --run $SEER_EVAL_RUN_ID --repo <repo_id_or_blank> \
       --question <question_id> --trial <n>
   ```
5. Verify a per-cell JSON appeared under
   `experiments/scripts_eval/results/$SEER_EVAL_RUN_ID/arm-<X>/`.
6. Move to the next row.

**Sequential, not parallel.** One cell at a time. Round 1 favours
observability over speed.

## After both arms finish

```bash
uv run --group experiments python -m experiments.scripts_eval.validate \
    --run $SEER_EVAL_RUN_ID

uv run --group experiments python -m experiments.scripts_eval.judge \
    --run $SEER_EVAL_RUN_ID

uv run --group experiments python -m experiments.scripts_eval.report \
    --run $SEER_EVAL_RUN_ID
```

Read `results/$SEER_EVAL_RUN_ID/REPORT.md`.

## Violations

`REPORT.md` lists two kinds:

- `A_used_scripts: ...` — an arm-A subagent invoked the scripts despite
  the prompt. Re-dispatch that cell with this stricter system prompt
  prepended:

  ```
  ABSOLUTE: do not run any of: scripts/profile.sh, scripts/connections.sh,
  scripts/graph.sh, python -m seer.repo, or any path containing seer/repo.
  If you cannot answer without them, say so explicitly and stop.
  ```

  Re-run capture for the cell. Replace the prior arm-A JSON in place.

- `C_did_not_use_scripts: ...` — an arm-C subagent never called the
  scripts. Keep the cell; this is a finding ("the scripts didn't seem
  necessary"), not a bug.

## Adding a target repo or question type mid-corpus

Edit `corpus.yaml`. For a new target, add an `expected_evidence` row
under every per-repo question. Re-run only the new cells (capture
takes `--repo` and `--question` so partial runs are natural).
````

- [ ] **Step 2: Commit**

```bash
git add experiments/scripts_eval/RUNBOOK.md
git commit -m "scripts-eval: RUNBOOK with per-cell loop and violation handling"
```

---

### Task 9.3: Replace the README stub with the full README

**Files:**
- Modify: `experiments/scripts_eval/README.md`

- [ ] **Step 1: Replace the stub**

Overwrite `experiments/scripts_eval/README.md`:

```markdown
# scripts-eval

A/C subagent comparison harness for the `repo-map` skill.

This experiment answers three questions about the scripts under
`.claude/skills/repo-map/scripts/`:

1. **Gate** — does an agent armed with `repo-map` produce better
   answers than a bare agent (Read/Grep/Glob only)?
2. **Calibration** — *where* is the win — which question shapes
   benefit, and how much (in tokens, time, judged quality)?
3. **Diagnostics** — when do equipped agents misuse the scripts?

See `docs/superpowers/specs/2026-05-15-scripts-eval-harness-design.md`
for the design and `RUNBOOK.md` for the operator procedure.

## Layout

```
experiments/scripts_eval/
├── README.md             ← this file
├── RUNBOOK.md            ← operator procedure
├── corpus.yaml           ← targets × questions × expected_evidence
├── judge_rubric.md       ← rubric for the LLM-as-judge
├── _io.py                ← shared helpers
├── corpus.py             ← corpus loader
├── manifest.py           ← per-run manifest.json (date, env, models)
├── capture.py            ← raw hook JSONL → per-cell JSON
├── validate.py           ← code-validation against expected_evidence
├── judge.py              ← pairwise blind LLM-as-judge
├── report.py             ← REPORT.md generator
├── hooks/                ← Claude Code hook scripts
└── results/              ← per-run artefacts (gitignored)
```

## Three-layer scoring

| Layer | Source |
| --- | --- |
| Mechanical (duration, tokens, model, tools) | hooks |
| Code validation (recall of expected_evidence) | validate.py |
| Pairwise blind LLM judge (winner + margin) | judge.py |

## Repeatability

A new contributor pointing this at their own repos:

1. `uv sync --group experiments`
2. Edit `corpus.yaml`: replace `targets:` with their own repos and
   each question's `expected_evidence` with their own facts.
3. Pick a run id, export `SEER_EVAL_RUN_ID` and `SEER_EVAL_ARM`,
   follow `RUNBOOK.md`.
4. Read `results/<run_id>/REPORT.md`.

The hooks no-op without the env vars, so day-to-day seer-cli work in
the same checkout is unaffected.
```

- [ ] **Step 2: Commit**

```bash
git add experiments/scripts_eval/README.md
git commit -m "scripts-eval: full README replacing the stub"
```

---

## Phase 10 — Round-1 corpus content

### Task 10.1: Author `corpus.yaml` skeleton (targets + question templates only)

**Files:**
- Create: `experiments/scripts_eval/corpus.yaml`

- [ ] **Step 1: Write the corpus skeleton**

Create `experiments/scripts_eval/corpus.yaml`. Targets and question templates only — `expected_evidence` lists are filled in Tasks 10.2–10.6:

```yaml
corpus_version: 1

config:
  trials_per_cell: 3
  arms: [A, C]
  workspace_root: /home/spark/git

targets:
  - id: culture
    path: /home/spark/git/culture
    description: Async Python IRCd + agent harnesses (Claude Agent SDK).
  - id: daria
    path: /home/spark/git/daria
    description: Awareness agent that consumes culture; cite-don't-import edges.
  - id: claude-code-guide
    path: /home/spark/git/claude-code-guide
    description: Claude Code plugin (plugin.json, marketplace.json shape).
  - id: agtag
    path: /home/spark/git/agtag
    description: Small CLI tool with dense pyproject.toml.
  - id: citation-cli
    path: /home/spark/git/citation-cli
    description: Cite-don't-import reference; packages/ shape.

questions:
  - id: q-profile-overview
    type: profile
    scope: per_repo
    template: |
      You are exploring the repository at {repo_path}.
      Give me a clear overview: what is this repo for, what is the
      build/test story, what are its top-level components.
    expected_evidence: {}

  - id: q-connections-1hop
    type: connections
    scope: per_repo
    template: |
      What does the repository at {repo_path} connect to (depend on,
      vendor from, or get cited by)? Walk one hop out.
    expected_evidence: {}

  - id: q-graph-workspace
    type: graph
    scope: workspace
    template: |
      Map the repos in {workspace_root}. Which ones form clusters
      (by shared dependencies, vendored skills, or cite-don't-import
      edges), and how are they related?
    expected_evidence: {}

  - id: q-narrative
    type: narrative
    scope: per_repo
    template: |
      Explain to me how the repository at {repo_path} works.
      Walk me through the main flow end-to-end. Be concrete: name files
      and functions where relevant.
    expected_evidence: {}

  - id: q-transfer-cli
    type: transfer
    scope: per_repo
    template: |
      The repository at {repo_path} has a CLI. Explain how I could
      build something like it in my own Python repo. Be concrete: what
      files, what entry points, what conventions, what packaging.
    expected_evidence: {}

  - id: q-transfer-quality
    type: transfer
    scope: per_repo
    template: |
      The repository at {repo_path} has a CI / quality pipeline.
      What do I need to add to a generic Python repo to get the same
      pipeline (lint, test, security, version-bump enforcement)?
    expected_evidence: {}
```

- [ ] **Step 2: Smoke-test the loader against the real corpus**

Run: `uv run --group experiments python -c "from experiments.scripts_eval import corpus; c = corpus.load('experiments/scripts_eval/corpus.yaml'); print(len(list(c.iter_cells('A'))), 'cells/arm')"`
Expected: a number ≈ `5 repos × 5 per-repo questions × 3 trials + 1 workspace question × 3 trials = 78` cells per arm. (Multiply by 2 arms = 156 total cells.) Confirm value.

- [ ] **Step 3: Commit**

```bash
git add experiments/scripts_eval/corpus.yaml
git commit -m "scripts-eval: round-1 corpus skeleton (targets + templates)"
```

---

### Task 10.2: Author `expected_evidence` for `culture`

**Files:**
- Modify: `experiments/scripts_eval/corpus.yaml`

- [ ] **Step 1: Profile the target to ground the evidence list**

Run: `uv run python -m seer.repo profile /home/spark/git/culture --depth deep`
Expected: a markdown profile dump. Skim it to identify: package layout, deps, entry points, vendored skills, key sub-systems. Use these to author the lists.

- [ ] **Step 2: Add `culture` keys to every per-repo question's `expected_evidence`**

In `corpus.yaml`, fill `expected_evidence:` blocks for each per-repo
question with a `culture:` key. Aim for **4–8 items per question**.
Mix: file paths the answer should cite, dep names, concept names. Use
the `/regex/` form for things like version strings.

Example for `q-profile-overview` (verify against the profile output;
this is illustrative, not authoritative):

```yaml
expected_evidence:
  culture:
    - pyproject.toml
    - "uv sync"
    - culture.yaml
    - async IRCd
    - agent harness
    - "claude agent sdk"
```

Author lists for: `q-profile-overview`, `q-connections-1hop`,
`q-narrative`, `q-transfer-cli`, `q-transfer-quality`.
The workspace question (`q-graph-workspace`) takes a `_global` key,
authored in Task 10.7.

- [ ] **Step 3: User review**

Pause. Show the diff to the user; have them sanity-check that the
items are facts the answer must contain (not preferences).

- [ ] **Step 4: Commit**

```bash
git add experiments/scripts_eval/corpus.yaml
git commit -m "scripts-eval: expected_evidence for culture"
```

---

### Task 10.3: Author `expected_evidence` for `daria`

**Files:**
- Modify: `experiments/scripts_eval/corpus.yaml`

Repeat Task 10.2's structure, swapping `culture` for `daria`. Profile
first (`uv run python -m seer.repo profile /home/spark/git/daria
--depth deep`), then write 4–8 items per per-repo question keyed by
`daria:`. User reviews. Commit:

```bash
git add experiments/scripts_eval/corpus.yaml
git commit -m "scripts-eval: expected_evidence for daria"
```

---

### Task 10.4: Author `expected_evidence` for `claude-code-guide`

Same pattern as 10.2, target `/home/spark/git/claude-code-guide`. Note
this repo is a Claude Code plugin (different shape — `plugin.json`,
`marketplace.json`); evidence lists should reflect that. User reviews.

```bash
git add experiments/scripts_eval/corpus.yaml
git commit -m "scripts-eval: expected_evidence for claude-code-guide"
```

---

### Task 10.5: Author `expected_evidence` for `agtag`

Same pattern, target `/home/spark/git/agtag`. User reviews.

```bash
git add experiments/scripts_eval/corpus.yaml
git commit -m "scripts-eval: expected_evidence for agtag"
```

---

### Task 10.6: Author `expected_evidence` for `citation-cli`

Same pattern, target `/home/spark/git/citation-cli`. User reviews.

```bash
git add experiments/scripts_eval/corpus.yaml
git commit -m "scripts-eval: expected_evidence for citation-cli"
```

---

### Task 10.7: Author `_global` evidence for the workspace question

**Files:**
- Modify: `experiments/scripts_eval/corpus.yaml`

- [ ] **Step 1: Profile the workspace**

Run: `uv run python -m seer.repo graph /home/spark/git`
Expected: a markdown overview of every repo + edges.

- [ ] **Step 2: Author `_global` for `q-graph-workspace`**

Items the answer must mention: cluster names ("AgentCulture"), key
hub repos (`culture`, `daria`, `steward`), and one or two specific
edges (e.g. "daria depends on culture"). 6–10 items.

- [ ] **Step 3: User reviews + commit**

```bash
git add experiments/scripts_eval/corpus.yaml
git commit -m "scripts-eval: workspace expected_evidence (_global)"
```

---

## Phase 11 — End-to-end smoke

### Task 11.1: Run a 2-cell smoke (arm-A + arm-C, one cell each) on culture / q-profile-overview

This is a **manual** task that exercises the full pipeline
end-to-end. Treat any failure as a fix-then-retry, not as a follow-up.

- [ ] **Step 1: Pick a smoke run id, export env, init manifest**

```bash
export SEER_EVAL_RUN_ID=smoke-end-to-end-01
mkdir -p experiments/scripts_eval/results/$SEER_EVAL_RUN_ID
uv run --group experiments python -m experiments.scripts_eval.manifest init \
    --run $SEER_EVAL_RUN_ID
```

- [ ] **Step 2: Run the arm-A cell**

In a Claude Code session **without** `repo-map` loaded:

```bash
export SEER_EVAL_ARM=A
```

Dispatch one `Explore` subagent with the substituted
`q-profile-overview` template targeting `/home/spark/git/culture`,
including the arm-A constraints from `RUNBOOK.md`.

After it finishes, run capture:

```bash
uv run --group experiments python -m experiments.scripts_eval.capture \
    --run $SEER_EVAL_RUN_ID --repo culture \
    --question q-profile-overview --trial 1
```

Expect the message `capture: wrote 1 cell(s)` and a file at
`experiments/scripts_eval/results/$SEER_EVAL_RUN_ID/arm-A/culture-q-profile-overview-t1.json`.

- [ ] **Step 3: Run the arm-C cell**

In a separate Claude Code session **with** `repo-map` loaded:

```bash
export SEER_EVAL_RUN_ID=smoke-end-to-end-01
export SEER_EVAL_ARM=C
```

Dispatch the same question. Run capture again. Expect a file under
`arm-C/`.

- [ ] **Step 4: Run validate, judge, report**

```bash
uv run --group experiments python -m experiments.scripts_eval.validate \
    --run $SEER_EVAL_RUN_ID
uv run --group experiments python -m experiments.scripts_eval.judge \
    --run $SEER_EVAL_RUN_ID
uv run --group experiments python -m experiments.scripts_eval.report \
    --run $SEER_EVAL_RUN_ID
```

Open `experiments/scripts_eval/results/$SEER_EVAL_RUN_ID/REPORT.md`.
It should contain:

- A `# scripts-eval — run smoke-end-to-end-01` heading.
- An `## Aggregate` section with median validation scores.
- A `### culture / q-profile-overview / t1` section with a winner +
  margin from the judge and validation deltas.

- [ ] **Step 5: Investigate any anomaly**

Common issues and their fixes:

- Hooks didn't fire → re-check `.claude/settings.json`, env vars
  exported in the *exact* shell the operator session is in.
- Capture says `no complete subagent JSONL found` → inspect
  `results/<run>/raw/` — did `subagent_stop` line land? If not, the
  transcript-slicing heuristic in `subagent_stop.py` likely needs an
  adjustment.
- Validation score is 0 with a clearly correct answer → check whether
  the regex form was misused or the substring is too specific.
- Judge call fails → confirm `ANTHROPIC_API_KEY` is set; retry with
  `--seed 1` to vary the blinding.

- [ ] **Step 6: Decide whether the smoke is clean**

If the report shows both cells, validation looks reasonable, and the
judge produced a defensible verdict, proceed to deleting the smoke
results and committing nothing. The smoke proves the pipeline works;
it is not data we want checked in.

```bash
rm -rf experiments/scripts_eval/results/smoke-end-to-end-01
```

- [ ] **Step 7: Mark the harness ready**

If the smoke passes, the harness is ready for round 1. Open a PR for
the branch (`experiments/scripts-eval`) referencing the spec and this
plan. Do not run round 1 inside the PR — round 1 is a separate
operator activity that produces a `2026-05-XX-run-01/` artefact, kept
local (gitignored).

```bash
git push -u origin experiments/scripts-eval
gh pr create --base main --head experiments/scripts-eval \
    --title "scripts-eval harness: hooks + capture + validate + judge + report" \
    --body "Implements the design in docs/superpowers/specs/2026-05-15-scripts-eval-harness-design.md and the plan in docs/superpowers/plans/2026-05-15-scripts-eval-harness.md. End-to-end smoke clean.

- seer (Claude)"
```

---

## Self-review notes

- **Spec coverage:** every section/requirement of the spec maps to a
  task above. Hooks → Tasks 3.1–3.3 + 4.1; manifest → 5.2; capture →
  5.1; validate → 6.1; judge → 7.1; report → 8.1; corpus + procedure
  → 9.x + 10.x; end-to-end smoke + repeatability → 11.1.
- **Open questions from the spec:**
  - *Transcript-slicing heuristic*: implemented in
    `_last_assistant_after` (Task 3.3) — last assistant entry with
    `ts > start_time`. Smoke test verifies.
  - *Args-summary truncation*: `ARGS_MAX_LEN = 200` in `post_tool.py`,
    documented inline. Adjust if logs prove too noisy.
  - *Judge model choice*: `claude-opus-4-7` default in `judge.py`;
    overridable via `--model`.
  - *Authoring tooling*: not built; Tasks 10.x specify "profile first,
    then author" so the human stays in the loop.
- **Type consistency:** `process_run` signature is consistent across
  `capture.py`, `validate.py`, `judge.py`. Cell schema is consistent
  between `capture.py` (writes) and `validate.py`/`judge.py` (modify
  in place).
- **No placeholders.** Every step contains the actual content.
  Tasks 10.2–10.6 deliberately use repeated patterns rather than
  duplicating long YAML blocks; the engineer reading any single one
  has Task 10.2 as the worked example.
