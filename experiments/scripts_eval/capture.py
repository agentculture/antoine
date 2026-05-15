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
    """Rename raw/<sid>.jsonl to raw/<sid>.jsonl.done so we don't re-process."""
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
            # Extract first token (command/script name) from args_summary
            first_token = s.split()[0] if s.split() else s
            slot["patterns"].append(first_token)
    out = []
    for name, slot in by_name.items():
        out.append(
            {
                "name": name,
                "count": slot["count"],
                "patterns": slot["patterns"][:10],  # cap
            }
        )
    out.sort(key=lambda d: d["name"])
    return out


def build_cell(records: list[dict], *, repo_id: str | None, question_id: str, trial: int) -> dict:
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


def process_run(run_id: str, *, repo_id: str | None, question_id: str, trial: int) -> list[dict]:
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
    cells = process_run(args.run, repo_id=args.repo, question_id=args.question, trial=args.trial)
    if not cells:
        print(f"capture: no complete subagent JSONL found under run={args.run}")
        return 1
    print(f"capture: wrote {len(cells)} cell(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
