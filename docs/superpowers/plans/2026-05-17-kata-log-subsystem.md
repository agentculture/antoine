# kata-cli log subsystem (Cell 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the foundational log subsystem for the kata-cli capture/reduce/assess loop — the JSONL schema, the two-tier on-disk store (shape file + raw-args sidecar), TTL gc with the privacy invariant, and the `kata log {tail, gc, grep}` verbs.

**Architecture:** A new `antoine/kata/log/` engine subpackage owns the store layout and IO; a new `antoine/cli/_commands/log.py` registers the `log` verb with three subcommands (`tail`, `gc`, `grep`). All paths are relative to the current working directory: `.antoine/log/<YYYY-MM-DD>.jsonl` for the shape index, `.antoine/log/args/<session>.jsonl` for raw args. Gc enforces a 7-day TTL and exits non-zero if it cannot honour it (privacy invariant). The engine is adapter-agnostic — antoine never *writes* into the store as part of normal operation; the agent's backend does. We ship a `LogEntry` writer for tests and (later cells) verb-internal use only.

**Tech Stack:** Python 3.12, stdlib only (json, pathlib, datetime, argparse, hashlib, time), pytest with `-n auto`, uv.

**Spec:** [`docs/superpowers/specs/2026-05-17-kata-loop-design.md`](../specs/2026-05-17-kata-loop-design.md). This plan covers **Cell 1** of the 8-cell scope.

**Plan-wide invariants** (every task respects these):

1. **No env vars.** No verb in this plan reads or writes any `KATA_*` environment variable.
2. **antoine never crashes.** All handlers raise `AntoineError` on failure; unexpected exceptions are caught by the existing `_dispatch` chassis (no traceback to stderr).
3. **Errors are remediable** — every `AntoineError` has a non-empty `remediation` field that names a concrete next step.
4. **TDD.** Each task writes the failing test first, then the minimum code.

**Exit code reconciliation.** The existing chassis defines `EXIT_USER_ERROR=1`, `EXIT_ENV_ERROR=2`, `EXIT_INTERNAL=3` (`antoine/cli/_errors.py:16-27`). This plan reuses those three codes:

- "No log present" → `EXIT_ENV_ERROR` (2)
- "Bad flag / unknown subcommand" → `EXIT_USER_ERROR` (1)
- "GC cannot delete (permission)" → `EXIT_ENV_ERROR` (2)
- Unexpected → `EXIT_INTERNAL` (3) via existing `_dispatch` wrap

The Error/Fix/Then *message* distinguishes between these, not the exit code. New numeric codes are not introduced.

---

### Task 1: Scaffold `antoine.kata.log` and add gitignore rule

**Files:**
- Create: `antoine/kata/__init__.py`
- Create: `antoine/kata/log/__init__.py`
- Create: `tests/kata/__init__.py`
- Modify: `.gitignore` (append a section for `.antoine/`)

- [ ] **Step 1: Write the failing test**

Create `tests/kata/__init__.py` (empty) and `tests/kata/test_package.py`:

```python
"""Smoke test: kata.log package is importable and exposes nothing yet."""
from __future__ import annotations


def test_kata_log_package_imports() -> None:
    import antoine.kata.log as mod

    # Cell 1 starts with no public API; later tasks will add LogEntry etc.
    assert mod.__name__ == "antoine.kata.log"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/kata/test_package.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'antoine.kata'`.

- [ ] **Step 3: Create the scaffold**

`antoine/kata/__init__.py`:

```python
"""antoine.kata — the capture/reduce/assess loop engine.

See `docs/superpowers/specs/2026-05-17-kata-loop-design.md` for the design.
This package is purely the engine; CLI verbs live in `antoine.cli._commands`.
"""
```

`antoine/kata/log/__init__.py`:

```python
"""Log subsystem: JSONL schema, on-disk store, TTL gc.

Layout (under the current working directory):

  .antoine/log/<YYYY-MM-DD>.jsonl    shape index, one line per tool call
  .antoine/log/args/<session>.jsonl  raw args sidecar, keyed by row index

The shape index is what `suggest`/`assess` read. The args sidecar holds
raw, privacy-sensitive data and is the first thing the 7-day TTL pass
deletes.
"""
```

- [ ] **Step 4: Append gitignore rule**

Append to `.gitignore`:

```gitignore

# kata-cli local store — everything under .antoine/ is local-only,
# EXCEPT katas.toml which is the committed audit ledger.
.antoine/*
!.antoine/katas.toml
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/kata/test_package.py -v
```
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add antoine/kata/ tests/kata/ .gitignore
git commit -m "feat(kata): scaffold antoine.kata.log subpackage + gitignore rule"
```

---

### Task 2: `LogEntry` schema with serialization round-trip

**Files:**
- Create: `antoine/kata/log/_schema.py`
- Create: `tests/kata/test_log_schema.py`

- [ ] **Step 1: Write the failing tests**

`tests/kata/test_log_schema.py`:

```python
"""LogEntry round-trip: dataclass <-> JSON line."""
from __future__ import annotations

import json

import pytest

from antoine.kata.log._schema import LogEntry


def _entry() -> LogEntry:
    return LogEntry(
        ts="2026-05-17T14:22:01Z",
        session="sess-abc",
        agent="claude-code",
        tool="Bash",
        args_digest="sha256:" + "0" * 64,
        bash_argv0="git",
        tokens_in=1234,
        tokens_out=567,
        duration_ms=412,
    )


def test_logentry_to_json_line_is_one_line_with_trailing_newline() -> None:
    line = _entry().to_json_line()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    payload = json.loads(line)
    assert payload["tool"] == "Bash"
    assert payload["bash_argv0"] == "git"


def test_logentry_round_trip() -> None:
    original = _entry()
    line = original.to_json_line()
    restored = LogEntry.from_json_line(line)
    assert restored == original


def test_logentry_optional_fields_default_none() -> None:
    minimal = LogEntry(
        ts="2026-05-17T14:22:01Z",
        session="s",
        agent="claude-code",
        tool="Read",
        args_digest="sha256:" + "0" * 64,
    )
    assert minimal.bash_argv0 is None
    assert minimal.tokens_in is None
    assert minimal.tokens_out is None
    assert minimal.duration_ms is None
    # Round-trip preserves the None fields.
    assert LogEntry.from_json_line(minimal.to_json_line()) == minimal


def test_logentry_from_json_line_rejects_missing_required_field() -> None:
    line = '{"session": "s", "agent": "claude-code", "tool": "Read"}\n'
    with pytest.raises(ValueError, match="missing required field"):
        LogEntry.from_json_line(line)


def test_logentry_args_digest_must_be_sha256() -> None:
    with pytest.raises(ValueError, match="args_digest must start with 'sha256:'"):
        LogEntry(
            ts="2026-05-17T14:22:01Z",
            session="s",
            agent="claude-code",
            tool="Read",
            args_digest="md5:deadbeef",
        )
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/kata/test_log_schema.py -v
```
Expected: FAIL with `ModuleNotFoundError` for `antoine.kata.log._schema`.

- [ ] **Step 3: Implement `LogEntry`**

`antoine/kata/log/_schema.py`:

```python
"""LogEntry — the JSONL row written by an adapter per captured tool call.

The schema is documented in:
  docs/kata/log-schema.md  (added in a later task in this plan)

This module is pure data + serialization; it owns no IO.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

_REQUIRED = ("ts", "session", "agent", "tool", "args_digest")


@dataclass(frozen=True)
class LogEntry:
    """One captured tool call.

    Required fields (always present): ts, session, agent, tool, args_digest.
    Optional fields (None if the adapter could not provide them):
    bash_argv0, tokens_in, tokens_out, duration_ms.
    """

    ts: str
    session: str
    agent: str
    tool: str
    args_digest: str
    bash_argv0: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.args_digest.startswith("sha256:"):
            raise ValueError(
                "args_digest must start with 'sha256:' "
                f"(got: {self.args_digest!r})"
            )

    def to_json_line(self) -> str:
        """Return a single newline-terminated JSON object."""
        payload = asdict(self)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"

    @classmethod
    def from_json_line(cls, line: str) -> "LogEntry":
        """Parse one JSONL row. Raises ValueError on missing required fields."""
        payload: dict[str, Any] = json.loads(line)
        for field_name in _REQUIRED:
            if field_name not in payload:
                raise ValueError(f"missing required field: {field_name!r}")
        return cls(**payload)
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/kata/test_log_schema.py -v
```
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add antoine/kata/log/_schema.py tests/kata/test_log_schema.py
git commit -m "feat(kata.log): LogEntry schema with JSONL round-trip"
```

---

### Task 3: Store layout — paths + append + read

**Files:**
- Create: `antoine/kata/log/_store.py`
- Create: `tests/kata/test_log_store.py`

- [ ] **Step 1: Write the failing tests**

`tests/kata/test_log_store.py`:

```python
"""Store layout: paths, append, read."""
from __future__ import annotations

from pathlib import Path

import pytest

from antoine.kata.log._schema import LogEntry
from antoine.kata.log._store import LogStore


def _entry(ts: str = "2026-05-17T14:22:01Z", session: str = "s") -> LogEntry:
    return LogEntry(
        ts=ts,
        session=session,
        agent="claude-code",
        tool="Bash",
        args_digest="sha256:" + "0" * 64,
        bash_argv0="git",
    )


def test_logstore_root_defaults_to_cwd_dot_antoine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = LogStore()
    assert store.root == tmp_path / ".antoine" / "log"


def test_logstore_root_can_be_overridden(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path / "custom")
    assert store.root == tmp_path / "custom"


def test_append_creates_shape_file_per_day(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry(ts="2026-05-17T10:00:00Z"))
    store.append(_entry(ts="2026-05-17T23:59:59Z"))
    store.append(_entry(ts="2026-05-18T00:00:01Z"))

    files = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    assert files == ["2026-05-17.jsonl", "2026-05-18.jsonl"]


def test_append_writes_one_line_per_entry(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry())
    store.append(_entry(session="t"))

    lines = (tmp_path / "2026-05-17.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_read_all_returns_entries_in_chronological_order(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry(ts="2026-05-18T00:00:01Z"))
    store.append(_entry(ts="2026-05-17T10:00:00Z"))
    store.append(_entry(ts="2026-05-17T11:00:00Z"))

    ts_order = [e.ts for e in store.read_all()]
    assert ts_order == [
        "2026-05-17T10:00:00Z",
        "2026-05-17T11:00:00Z",
        "2026-05-18T00:00:01Z",
    ]


def test_read_all_on_empty_store_returns_empty_list(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    assert list(store.read_all()) == []


def test_read_all_skips_blank_lines(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    store.append(_entry())
    # Simulate a malformed write (trailing blank).
    (tmp_path / "2026-05-17.jsonl").write_text(
        _entry().to_json_line() + "\n\n" + _entry(session="t").to_json_line()
    )
    sessions = [e.session for e in store.read_all()]
    assert sessions == ["s", "t"]


def test_read_all_raises_on_corrupt_line(tmp_path: Path) -> None:
    store = LogStore(root=tmp_path)
    (tmp_path / "2026-05-17.jsonl").write_text("not json\n")
    with pytest.raises(ValueError, match="log corrupted"):
        list(store.read_all())
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/kata/test_log_store.py -v
```
Expected: FAIL with `ModuleNotFoundError` for `antoine.kata.log._store`.

- [ ] **Step 3: Implement `LogStore`**

`antoine/kata/log/_store.py`:

```python
"""LogStore — append-only shape index, one file per UTC day.

Layout under ``root`` (defaults to ``./.antoine/log``):

    <YYYY-MM-DD>.jsonl   one line per LogEntry whose ts falls on that day

No IO beyond append + sequential read happens here. Raw args live in a
sibling sidecar handled by ``_args.py`` (next task).
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from antoine.kata.log._schema import LogEntry


class LogStore:
    """Append-only daily-sharded JSONL store."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path.cwd() / ".antoine" / "log"
        self.root = root

    def _file_for(self, ts: str) -> Path:
        # ts is ISO-8601 UTC; YYYY-MM-DD is the first 10 chars.
        return self.root / f"{ts[:10]}.jsonl"

    def append(self, entry: LogEntry) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._file_for(entry.ts)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(entry.to_json_line())

    def read_all(self) -> Iterator[LogEntry]:
        """Yield entries in chronological order across all shard files."""
        if not self.root.exists():
            return
        shards = sorted(self.root.glob("*.jsonl"))
        for shard in shards:
            with shard.open("r", encoding="utf-8") as fp:
                for line_no, raw in enumerate(fp, start=1):
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    try:
                        yield LogEntry.from_json_line(stripped)
                    except (ValueError, json.JSONDecodeError) as exc:
                        raise ValueError(
                            f"log corrupted: {shard.name}:{line_no}: {exc}"
                        ) from exc
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/kata/test_log_store.py -v
```
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add antoine/kata/log/_store.py tests/kata/test_log_store.py
git commit -m "feat(kata.log): daily-sharded JSONL LogStore"
```

---

### Task 4: Args sidecar — separate write/read for raw args

**Files:**
- Create: `antoine/kata/log/_args.py`
- Create: `tests/kata/test_log_args.py`

- [ ] **Step 1: Write the failing tests**

`tests/kata/test_log_args.py`:

```python
"""Args sidecar — raw args keyed by (session, row_index)."""
from __future__ import annotations

from pathlib import Path

from antoine.kata.log._args import ArgsSidecar


def test_append_and_read_round_trip(tmp_path: Path) -> None:
    side = ArgsSidecar(root=tmp_path)
    side.append("sess-1", {"command": "git log --oneline"})
    side.append("sess-1", {"command": "git show HEAD"})
    side.append("sess-2", {"path": "README.md"})

    one = list(side.read("sess-1"))
    two = list(side.read("sess-2"))
    assert one == [
        {"command": "git log --oneline"},
        {"command": "git show HEAD"},
    ]
    assert two == [{"path": "README.md"}]


def test_read_unknown_session_returns_empty(tmp_path: Path) -> None:
    side = ArgsSidecar(root=tmp_path)
    assert list(side.read("nope")) == []


def test_sidecar_files_live_in_args_subdir(tmp_path: Path) -> None:
    side = ArgsSidecar(root=tmp_path)
    side.append("s", {"x": 1})
    assert (tmp_path / "args" / "s.jsonl").exists()
    # Top-level (shape) area is untouched.
    assert not (tmp_path / "s.jsonl").exists()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/kata/test_log_args.py -v
```
Expected: FAIL with `ModuleNotFoundError` for `antoine.kata.log._args`.

- [ ] **Step 3: Implement `ArgsSidecar`**

`antoine/kata/log/_args.py`:

```python
"""ArgsSidecar — raw args kept separately from the shape index.

This is the privacy-sensitive half of the log. TTL gc deletes this
directory first; the shape index can be retained longer if the user wants
aggregate stats without raw content.

Files live at <root>/args/<session>.jsonl, one JSON object per line.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class ArgsSidecar:
    """Per-session JSONL store for raw tool args."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.args_dir = root / "args"

    def _file_for(self, session: str) -> Path:
        return self.args_dir / f"{session}.jsonl"

    def append(self, session: str, args: dict[str, Any]) -> None:
        self.args_dir.mkdir(parents=True, exist_ok=True)
        path = self._file_for(session)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(args, ensure_ascii=False, separators=(",", ":")) + "\n")

    def read(self, session: str) -> Iterator[dict[str, Any]]:
        path = self._file_for(session)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fp:
            for raw in fp:
                stripped = raw.strip()
                if not stripped:
                    continue
                yield json.loads(stripped)
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/kata/test_log_args.py -v
```
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add antoine/kata/log/_args.py tests/kata/test_log_args.py
git commit -m "feat(kata.log): raw-args sidecar separate from shape index"
```

---

### Task 5: TTL gc with privacy invariant

**Files:**
- Create: `antoine/kata/log/_gc.py`
- Create: `tests/kata/test_log_gc.py`

- [ ] **Step 1: Write the failing tests**

`tests/kata/test_log_gc.py`:

```python
"""TTL gc — deletes shape + args past TTL; raises on permission failure."""
from __future__ import annotations

import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from antoine.kata.log._gc import GCResult, gc


def _touch(path: Path, days_old: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("payload\n")
    age = (datetime.now(timezone.utc) - timedelta(days=days_old)).timestamp()
    os.utime(path, (age, age))


def test_gc_deletes_files_past_ttl(tmp_path: Path) -> None:
    fresh = tmp_path / "2026-05-16.jsonl"
    stale = tmp_path / "2026-05-01.jsonl"
    _touch(fresh, days_old=2)
    _touch(stale, days_old=10)

    result = gc(root=tmp_path, ttl_days=7)
    assert result.deleted_shape == [stale]
    assert result.deleted_args == []
    assert fresh.exists()
    assert not stale.exists()


def test_gc_deletes_args_first(tmp_path: Path) -> None:
    args_old = tmp_path / "args" / "old.jsonl"
    args_fresh = tmp_path / "args" / "fresh.jsonl"
    _touch(args_old, days_old=10)
    _touch(args_fresh, days_old=2)

    result = gc(root=tmp_path, ttl_days=7)
    assert result.deleted_args == [args_old]
    assert not args_old.exists()
    assert args_fresh.exists()


def test_gc_on_empty_store_is_noop(tmp_path: Path) -> None:
    result = gc(root=tmp_path, ttl_days=7)
    assert result == GCResult(deleted_shape=[], deleted_args=[])


def test_gc_raises_on_permission_error(tmp_path: Path) -> None:
    stale = tmp_path / "2026-05-01.jsonl"
    _touch(stale, days_old=10)
    # Lock the parent dir read-only so unlink fails.
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(PermissionError):
            gc(root=tmp_path, ttl_days=7)
    finally:
        # Restore for cleanup.
        tmp_path.chmod(stat.S_IRWXU)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/kata/test_log_gc.py -v
```
Expected: FAIL with `ModuleNotFoundError` for `antoine.kata.log._gc`.

- [ ] **Step 3: Implement `gc`**

`antoine/kata/log/_gc.py`:

```python
"""TTL gc — privacy invariant: if files past TTL exist, they MUST be deleted.

The order is intentional: raw args first (privacy-sensitive), then the
shape index. If any unlink raises ``PermissionError``, propagate it
unchanged so the caller (the ``kata log gc`` verb handler) can translate
it into an ``AntoineError`` with an actionable Fix line.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GCResult:
    deleted_shape: list[Path] = field(default_factory=list)
    deleted_args: list[Path] = field(default_factory=list)


def _stale_files(directory: Path, ttl_seconds: float, now: float) -> list[Path]:
    if not directory.exists():
        return []
    out: list[Path] = []
    for p in sorted(directory.glob("*.jsonl")):
        if (now - p.stat().st_mtime) > ttl_seconds:
            out.append(p)
    return out


def gc(*, root: Path, ttl_days: int) -> GCResult:
    """Delete files older than ``ttl_days`` from ``root`` and ``root/args``.

    Raises ``PermissionError`` if any unlink fails — privacy invariant.
    """
    now = time.time()
    ttl_seconds = ttl_days * 86400.0

    args_dir = root / "args"
    stale_args = _stale_files(args_dir, ttl_seconds, now)
    stale_shape = _stale_files(root, ttl_seconds, now)

    # Args first — they hold the raw, privacy-sensitive data.
    for path in stale_args:
        path.unlink()
    for path in stale_shape:
        path.unlink()

    return GCResult(deleted_shape=stale_shape, deleted_args=stale_args)
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/kata/test_log_gc.py -v
```
Expected: PASS (4 passed). Note: if running as root, the permission test will be skipped/xfail — that's acceptable; document but do not block.

- [ ] **Step 5: Commit**

```bash
git add antoine/kata/log/_gc.py tests/kata/test_log_gc.py
git commit -m "feat(kata.log): TTL gc with privacy invariant (args deleted first)"
```

---

### Task 6: `kata log` verb shell + subcommand registration

**Files:**
- Create: `antoine/cli/_commands/log.py`
- Modify: `antoine/cli/__init__.py` (register the new verb)
- Create: `tests/test_cli_log_cmd.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_log_cmd.py`:

```python
"""`kata log` CLI: parent + 3 subcommands wired."""
from __future__ import annotations

import pytest

from antoine.cli import main


def test_log_with_no_subcommand_prints_help_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["log"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tail" in out
    assert "gc" in out
    assert "grep" in out


def test_log_unknown_subcommand_exits_one_with_remediation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["log", "nope"])
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "log --help" in err
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
```
Expected: FAIL — verb not registered.

- [ ] **Step 3: Implement the verb shell**

`antoine/cli/_commands/log.py`:

```python
"""`kata log` verb: parent + tail/gc/grep subcommands.

Concrete handlers are added in subsequent tasks; this module wires the
argparse skeleton and a default handler that prints help when no
subcommand is given.
"""
from __future__ import annotations

import argparse


def _no_subcommand(args: argparse.Namespace) -> int:
    # args.func is this function; args._parent_parser was stashed by register().
    args._parent_parser.print_help()
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "log",
        help="raw access to the local capture log",
        description="Inspect, prune, or search the local kata capture log under ./.antoine/log/.",
    )
    parser.set_defaults(func=_no_subcommand, _parent_parser=parser)
    subsub = parser.add_subparsers(dest="log_command")

    # tail/gc/grep are registered by sibling modules in later tasks.
    parser._kata_log_subparsers = subsub  # type: ignore[attr-defined]
```

`antoine/cli/__init__.py` — add to the imports and registrations:

```python
    from antoine.cli._commands import log as _log_cmd
    # ... existing imports unchanged ...

    _learn_cmd.register(sub)
    _explain_cmd.register(sub)
    _whoami_cmd.register(sub)
    _classify_cmd.register(sub)
    _grep_cmd.register(sub)
    _recent_cmd.register(sub)
    _log_cmd.register(sub)  # NEW
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
```
Expected: PASS (2 passed). Also run the full suite to confirm no regressions: `uv run pytest -n auto`. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add antoine/cli/_commands/log.py antoine/cli/__init__.py tests/test_cli_log_cmd.py
git commit -m "feat(cli): register 'kata log' parent verb with help-on-no-subcommand"
```

---

### Task 7: `kata log tail` subcommand

**Files:**
- Modify: `antoine/cli/_commands/log.py` (add tail handler)
- Modify: `tests/test_cli_log_cmd.py` (extend with tail tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_log_cmd.py`:

```python
import json
from pathlib import Path

import pytest


def _seed_log(root: Path, count: int = 3) -> None:
    """Write `count` synthetic entries into root/2026-05-17.jsonl."""
    root.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(count):
        lines.append(
            json.dumps(
                {
                    "ts": f"2026-05-17T10:00:{i:02d}Z",
                    "session": f"s{i}",
                    "agent": "claude-code",
                    "tool": "Bash",
                    "args_digest": "sha256:" + "0" * 64,
                    "bash_argv0": "git",
                }
            )
        )
    (root / "2026-05-17.jsonl").write_text("\n".join(lines) + "\n")


def test_log_tail_prints_last_n_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_log(tmp_path / ".antoine" / "log", count=5)

    rc = main(["log", "tail", "-n", "2"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2
    # Last two entries: s3, s4.
    assert "s3" in out[0]
    assert "s4" in out[1]


def test_log_tail_default_n_is_10(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_log(tmp_path / ".antoine" / "log", count=3)
    rc = main(["log", "tail"])
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 3  # only 3 in store; tail caps at what's there


def test_log_tail_with_empty_store_exits_two_with_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["log", "tail"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "No capture data" in err
    assert "kata learn" in err  # remediation hint
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
```
Expected: 3 new tests FAIL (no `tail` subcommand).

- [ ] **Step 3: Implement the `tail` subcommand**

Modify `antoine/cli/_commands/log.py` — replace the body of `register()` and add `_handle_tail`:

```python
from __future__ import annotations

import argparse
from collections import deque

from antoine.cli._errors import EXIT_ENV_ERROR, AntoineError
from antoine.cli._output import emit_result
from antoine.kata.log._store import LogStore


def _no_subcommand(args: argparse.Namespace) -> int:
    args._parent_parser.print_help()
    return 0


def _handle_tail(args: argparse.Namespace) -> int:
    store = LogStore()
    if not store.root.exists() or not any(store.root.glob("*.jsonl")):
        raise AntoineError(
            code=EXIT_ENV_ERROR,
            message=(
                "No capture data found in .antoine/log/. "
                "antoine has no observed tool calls to display."
            ),
            remediation=(
                "Run `kata learn` to see how to instrument your agent, "
                "then start a session and try `kata log tail` again."
            ),
        )

    n = max(1, int(args.n))
    last = deque(store.read_all(), maxlen=n)
    for entry in last:
        emit_result(entry.to_json_line().rstrip("\n"), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "log",
        help="raw access to the local capture log",
        description="Inspect, prune, or search the local kata capture log under ./.antoine/log/.",
    )
    parser.set_defaults(func=_no_subcommand, _parent_parser=parser)
    subsub = parser.add_subparsers(dest="log_command")

    tail = subsub.add_parser("tail", help="print the last N captured entries")
    tail.add_argument("-n", default=10, type=int, help="number of entries (default: 10)")
    tail.set_defaults(func=_handle_tail)

    parser._kata_log_subparsers = subsub  # type: ignore[attr-defined]
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
uv run pytest -n auto
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add antoine/cli/_commands/log.py tests/test_cli_log_cmd.py
git commit -m "feat(cli): kata log tail -n <N>"
```

---

### Task 8: `kata log gc` subcommand

**Files:**
- Modify: `antoine/cli/_commands/log.py` (add gc handler)
- Modify: `tests/test_cli_log_cmd.py` (extend with gc tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_log_cmd.py`:

```python
import os
from datetime import datetime, timedelta, timezone


def _age_file(path: Path, days: int) -> None:
    age = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    os.utime(path, (age, age))


def test_log_gc_deletes_stale_and_reports_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    log_root = tmp_path / ".antoine" / "log"
    _seed_log(log_root, count=1)
    _age_file(log_root / "2026-05-17.jsonl", days=10)

    rc = main(["log", "gc"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "deleted 1 shape file" in out
    assert "deleted 0 args file" in out
    assert not (log_root / "2026-05-17.jsonl").exists()


def test_log_gc_with_no_store_is_noop_zero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = main(["log", "gc"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "deleted 0 shape file" in out


def test_log_gc_custom_ttl_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    log_root = tmp_path / ".antoine" / "log"
    _seed_log(log_root, count=1)
    _age_file(log_root / "2026-05-17.jsonl", days=3)

    # Default TTL would keep it; --ttl-days=1 deletes it.
    rc = main(["log", "gc", "--ttl-days", "1"])
    assert rc == 0
    assert not (log_root / "2026-05-17.jsonl").exists()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
```
Expected: 3 new tests FAIL.

- [ ] **Step 3: Implement the `gc` subcommand**

Modify `antoine/cli/_commands/log.py` — add the import and handler:

```python
from antoine.kata.log._gc import gc as _gc_run

# ...

def _handle_gc(args: argparse.Namespace) -> int:
    store = LogStore()
    if not store.root.exists():
        emit_result("deleted 0 shape files, 0 args files (no log present)", json_mode=False)
        return 0
    try:
        result = _gc_run(root=store.root, ttl_days=args.ttl_days)
    except PermissionError as exc:
        raise AntoineError(
            code=EXIT_ENV_ERROR,
            message=(
                f"GC could not delete files past TTL: {exc}. "
                "The privacy invariant requires expired data to be removed."
            ),
            remediation=(
                "Check filesystem permissions on .antoine/log/ "
                "(needs delete access for the user running antoine), then retry."
            ),
        ) from exc

    emit_result(
        f"deleted {len(result.deleted_shape)} shape files, "
        f"{len(result.deleted_args)} args files",
        json_mode=False,
    )
    return 0


# In register(), add after the tail registration:

    gc_p = subsub.add_parser("gc", help="delete capture entries past TTL")
    gc_p.add_argument(
        "--ttl-days",
        type=int,
        default=7,
        help="retention window in days (default: 7)",
    )
    gc_p.set_defaults(func=_handle_gc)
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
uv run pytest -n auto
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add antoine/cli/_commands/log.py tests/test_cli_log_cmd.py
git commit -m "feat(cli): kata log gc --ttl-days (privacy-invariant deletion)"
```

---

### Task 9: `kata log grep` subcommand

**Files:**
- Modify: `antoine/cli/_commands/log.py` (add grep handler)
- Modify: `tests/test_cli_log_cmd.py` (extend with grep tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_log_cmd.py`:

```python
def test_log_grep_matches_tool_substring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    log_root = tmp_path / ".antoine" / "log"
    log_root.mkdir(parents=True)
    (log_root / "2026-05-17.jsonl").write_text(
        json.dumps(
            {
                "ts": "2026-05-17T10:00:00Z",
                "session": "s1",
                "agent": "claude-code",
                "tool": "Bash",
                "args_digest": "sha256:" + "0" * 64,
                "bash_argv0": "git",
            }
        )
        + "\n"
        + json.dumps(
            {
                "ts": "2026-05-17T10:00:01Z",
                "session": "s2",
                "agent": "claude-code",
                "tool": "Read",
                "args_digest": "sha256:" + "0" * 64,
            }
        )
        + "\n"
    )

    rc = main(["log", "grep", "Bash"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "s1" in out
    assert "s2" not in out


def test_log_grep_matches_bash_argv0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    log_root = tmp_path / ".antoine" / "log"
    _seed_log(log_root, count=1)
    rc = main(["log", "grep", "git"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "s0" in out


def test_log_grep_no_matches_exits_zero_with_empty_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    log_root = tmp_path / ".antoine" / "log"
    _seed_log(log_root, count=1)
    rc = main(["log", "grep", "xyzzy"])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_log_grep_with_no_store_exits_two_with_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["log", "grep", "anything"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "No capture data" in err
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
```
Expected: 4 new tests FAIL.

- [ ] **Step 3: Implement the `grep` subcommand**

Modify `antoine/cli/_commands/log.py` — add handler:

```python
def _handle_grep(args: argparse.Namespace) -> int:
    store = LogStore()
    if not store.root.exists() or not any(store.root.glob("*.jsonl")):
        raise AntoineError(
            code=EXIT_ENV_ERROR,
            message=(
                "No capture data found in .antoine/log/. "
                "antoine has nothing to grep."
            ),
            remediation=(
                "Run `kata learn` to see how to instrument your agent, "
                "then start a session before grepping the log."
            ),
        )

    needle = args.pattern
    for entry in store.read_all():
        haystack = " ".join(
            v
            for v in (entry.tool, entry.bash_argv0 or "", entry.agent, entry.session)
            if v
        )
        if needle in haystack:
            emit_result(entry.to_json_line().rstrip("\n"), json_mode=False)
    return 0


# In register(), after gc:

    grep_p = subsub.add_parser("grep", help="filter log entries by substring")
    grep_p.add_argument("pattern", help="substring matched against tool/bash_argv0/agent/session")
    grep_p.set_defaults(func=_handle_grep)
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_cli_log_cmd.py -v
uv run pytest -n auto
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add antoine/cli/_commands/log.py tests/test_cli_log_cmd.py
git commit -m "feat(cli): kata log grep <pattern> (substring over tool/argv0/agent/session)"
```

---

### Task 10: Schema docs + version bump + CHANGELOG

**Files:**
- Create: `docs/kata/log-schema.md`
- Modify: `pyproject.toml` (version bump)
- Modify: `CHANGELOG.md` (prepend entry)

- [ ] **Step 1: Write the schema doc**

`docs/kata/log-schema.md`:

```markdown
# kata-cli log schema

The local capture log lives under `.antoine/log/` relative to the
current working directory. Two-tier layout:

- `<YYYY-MM-DD>.jsonl` — shape index. One row per captured tool call.
- `args/<session>.jsonl` — raw args sidecar. Privacy-sensitive; deleted
  first by `kata log gc`.

## Shape row (JSONL)

| Field          | Type   | Required | Notes |
|----------------|--------|----------|-------|
| `ts`           | string | yes      | ISO-8601 UTC; the date prefix selects the shard file. |
| `session`      | string | yes      | Adapter-assigned session id; keys the args sidecar. |
| `agent`        | string | yes      | `claude-code`, `codex`, etc. |
| `tool`         | string | yes      | Backend-native tool name (`Bash`, `Read`, `Edit`, …). |
| `args_digest`  | string | yes      | `sha256:` prefix + 64 hex; used by `kata skill suggest` for shape clustering. |
| `bash_argv0`   | string | no       | First token of the argv when `tool` is `Bash`; `null` otherwise. |
| `tokens_in`    | int    | no       | Tokens consumed by the call, if the adapter can provide. |
| `tokens_out`   | int    | no       | Tokens emitted by the call, if the adapter can provide. |
| `duration_ms`  | int    | no       | Wall-clock duration, if the adapter can provide. |

## Args sidecar row (JSONL)

One JSON object per row, schema-free — raw args as the adapter saw
them. Row index implicitly aligns with the shape row's order in the
shape file for the same session.

## Privacy & retention

- Both tiers are gitignored by default (`.gitignore` excludes
  everything under `.antoine/` except `katas.toml`).
- `kata log gc` (default TTL 7 days) deletes args files past TTL
  *first*, then shape files. If any unlink fails, gc exits non-zero
  and antoine refuses to silently retain expired data.

## Who writes this?

antoine itself does NOT write to the log during normal operation. The
agent's backend writes (via project hooks, transcript ingest, or
self-emit — see `kata learn`). antoine only reads, prunes, and reports.
```

- [ ] **Step 2: Version bump**

Modify `pyproject.toml`:

```toml
version = "0.10.0"
```

(Bump from `0.9.2` → `0.10.0` — feature add, minor bump.)

- [ ] **Step 3: CHANGELOG entry**

Prepend to `CHANGELOG.md`, immediately after the top heading:

```markdown
## [0.10.0] — 2026-05-17

### Added

- `kata log {tail, gc, grep}` verbs for inspecting the local capture log
  under `.antoine/log/`.
- `antoine.kata.log` engine subpackage: `LogEntry` schema, daily-sharded
  `LogStore`, `ArgsSidecar`, TTL `gc` with privacy invariant (args files
  deleted first).
- `.gitignore` rule: everything under `.antoine/` is local-only except
  `katas.toml` (the future committed ledger; introduced in cell 4).
- `docs/kata/log-schema.md` documenting the JSONL row format.

This is **Cell 1** of the kata-cli capture/reduce/assess loop. See
`docs/superpowers/specs/2026-05-17-kata-loop-design.md` for the full
8-cell scope.
```

- [ ] **Step 4: Verify version-check CI gate would pass**

```bash
uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
```
Expected: `0.10.0`.

- [ ] **Step 5: Final full-suite pass**

```bash
uv run pytest -n auto
uv run flake8 --config=.flake8 antoine/ tests/
uv run black --check antoine/ tests/
uv run isort --check-only antoine/ tests/
```
Expected: all green. If `black`/`isort` fail, run without `--check`/`--check-only`, re-run check, then commit the formatting fix as part of the same commit.

- [ ] **Step 6: Commit**

```bash
git add docs/kata/log-schema.md pyproject.toml CHANGELOG.md
git commit -m "docs(kata.log): schema spec + v0.10.0 changelog"
```

---

## Post-plan integration check

After all 10 tasks merge to the feature branch:

- [ ] **Manual smoke** — from a fresh terminal in the repo root:

```bash
uv run antoine log              # prints help (no subcommand)
uv run antoine log tail         # exits 2 with Error/remediation
mkdir -p .antoine/log
echo '{"ts":"2026-05-17T10:00:00Z","session":"smoke","agent":"claude-code","tool":"Bash","args_digest":"sha256:0000000000000000000000000000000000000000000000000000000000000000","bash_argv0":"git"}' > .antoine/log/2026-05-17.jsonl
uv run antoine log tail         # prints the seeded line
uv run antoine log grep git     # prints the seeded line
uv run antoine log gc           # deleted 0 shape files (fresh)
rm -rf .antoine
```

- [ ] **Open PR** with title `feat: kata log subsystem (Cell 1 of kata-cli loop)`. Body summarises:
  - which cell of the spec this implements
  - the four invariants honoured (no env vars, no crash, remediable errors, TDD)
  - link to the design doc

---

## What this plan does NOT do (deferred to later cells)

- No `kata learn` instruction sheet (Cell 3).
- No `kata overview` / `doctor` / `explain` verbs (Cell 2).
- No `katas.toml` ledger or `kata skill *` verbs (Cells 4–6).
- No adapter docs and no actual capture — antoine only reads what the
  agent wrote. (Cell 3 adds the documentation; capture is always agent-side.)
- No dogfood loop on antoine itself (Cell 8).

Each of those is a separate plan triggered after this PR lands.
