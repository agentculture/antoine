"""backfill.py — one-shot re-extraction of cells captured by the (broken) old hook.

The previous SubagentStop hook recorded ``model=null``, ``usage={}``,
``final_text=""`` (wrong CC transcript schema + wrong file). The cells
were committed nonetheless. This module re-extracts each cell from its
matching sidechain transcript using ``trial._extract_cell_from_sidechain``,
preserves the ``judge`` block, and writes the patched cell back in place.

  uv run --group experiments python -m experiments.scripts_eval.backfill \\
      --run 2026-05-15-round-01

Each sidechain is keyed to its (arm, trial) via the CC-emitted
``<agent>.meta.json``'s ``description`` field (e.g. ``Arm-A t1: agtag
profile`` or ``scripts_eval tester arm-C t1``). Judge dispatches
(``scripts_eval judge: ...``) are skipped — they're not tester trials.
``start_time`` comes from the pre_tool raw record when available, falling
back to the first assistant timestamp in the sidechain.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from experiments.scripts_eval import _io, trial

# Match "<arm-letter> t<N>" with an optional "arm[-_ ]" prefix.
# Hits both "Arm-A t1: …" and "scripts_eval tester arm-C t1".
_DESC_RE = re.compile(
    r"(?:arm[\s_\-])?(?P<arm>[AC])\s+t(?P<trial>\d+)",
    re.IGNORECASE,
)


def _identify_trial(meta_path: Path) -> tuple[str, int] | None:
    """From a sidechain's .meta.json, return (arm, trial) or None for non-tester."""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    desc = meta.get("description") or ""
    if desc.startswith("scripts_eval judge:"):
        return None
    m = _DESC_RE.search(desc)
    if not m:
        return None
    return (m.group("arm").upper(), int(m.group("trial")))


def _projects_root() -> Path:
    """Same indirection as trial.py — testable + matches operator's CC dir."""
    val = os.environ.get("CLAUDE_PROJECTS_DIR")
    if val:
        return Path(val)
    return Path.home() / ".claude" / "projects"


def _encoded_repo_root() -> str:
    return str(_io.REPO_ROOT).replace("/", "-")


def _all_tester_sidechains() -> dict[tuple[str, int], Path]:
    """Scan every CC session under this repo's projects dir for tester sidechains.

    Returns a map ``(arm, trial) → sidechain_path``. Judges are skipped.
    """
    out: dict[tuple[str, int], Path] = {}
    repo_dir = _projects_root() / _encoded_repo_root()
    if not repo_dir.exists():
        return out
    for session_dir in repo_dir.iterdir():
        if not session_dir.is_dir():
            continue
        sub_dir = session_dir / "subagents"
        if not sub_dir.exists():
            continue
        for meta_fp in sub_dir.glob("agent-*.meta.json"):
            key = _identify_trial(meta_fp)
            if key is None:
                continue
            sidechain_fp = sub_dir / (meta_fp.name.removesuffix(".meta.json") + ".jsonl")
            if not sidechain_fp.exists():
                continue
            # If the same (arm, trial) appears under multiple sessions
            # (e.g. retried runs), prefer the newest sidechain.
            existing = out.get(key)
            if existing is None or sidechain_fp.stat().st_mtime > existing.stat().st_mtime:
                out[key] = sidechain_fp
    return out


def _read_pre_tool(fp: Path) -> dict | None:
    """Return the first record of *fp* if it's a pre_tool event, else None."""
    try:
        first = fp.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    try:
        rec = json.loads(first)
    except ValueError:
        return None
    return rec if rec.get("event") == "pre_tool" else None


_TRIAL_RE = re.compile(r"\bt(\d+)\b")


def _trial_from_pre(pre: dict) -> int | None:
    return (
        int(_TRIAL_RE.search(pre.get("description") or "").group(1))
        if _TRIAL_RE.search(pre.get("description") or "")
        else None
    )


def _pre_tools_by_arm_trial(raw_dir: Path, run_id: str) -> dict[tuple[str, int], dict]:
    by_key: dict[tuple[str, int], dict] = {}
    if not raw_dir.exists():
        return by_key
    for fp in raw_dir.glob(f"{run_id}-*-*.jsonl*"):
        rec = _read_pre_tool(fp)
        if rec is None:
            continue
        arm = rec.get("arm")
        trial_n = _trial_from_pre(rec)
        if arm is None or trial_n is None:
            continue
        by_key[(arm, trial_n)] = rec
    return by_key


def _first_assistant_iso(sidechain: Path) -> str | None:
    for line in sidechain.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") == "assistant":
            return entry.get("timestamp")
    return None


def backfill_cell(
    cell_path: Path,
    *,
    sidechains: dict[tuple[str, int], Path],
    pre_tools: dict[tuple[str, int], dict],
) -> dict[str, object]:
    cell = _io.read_json(cell_path)
    key = (cell["arm"], cell["trial"])
    sidechain = sidechains.get(key)
    if sidechain is None:
        return {"cell": cell_path.name, "skipped": "no sidechain matched (arm, trial)"}

    pre = pre_tools.get(key, {})
    start_time = pre.get("start_time")
    if start_time is None:
        # Fall back to first assistant timestamp from the sidechain itself.
        iso = _first_assistant_iso(sidechain)
        if iso:
            try:
                start_time = trial._iso_to_epoch(iso)
            except ValueError:
                start_time = None

    in_flight = {
        "run_id": cell["run_id"],
        "arm": cell["arm"],
        "repo_id": cell.get("repo_id"),
        "question_id": cell["question_id"],
        "trial": cell["trial"],
        "session_id": pre.get("session_id", ""),
        "start_time": start_time if start_time is not None else 0.0,
        "agent_type": pre.get("agent_type", "Explore"),
        "question_text": pre.get("prompt", ""),
    }

    new_cell = trial._extract_cell_from_sidechain(sidechain, in_flight=in_flight)
    # Preserve validation + judge from original cell. The judge block in
    # particular has the (meaningless empty-string-compared) verdict that
    # the operator will re-run after backfill.
    new_cell["validation"] = cell.get("validation")
    new_cell["judge"] = cell.get("judge")
    _io.write_json(cell_path, new_cell)

    return {
        "cell": cell_path.name,
        "sidechain": sidechain.name,
        "answer_chars": len(new_cell["answer_text"]),
        "model": new_cell["subagent"]["model"],
        "tools": {t["name"]: t["count"] for t in new_cell["subagent"]["tools_used"]},
        "tokens_in": new_cell["subagent"]["tokens"]["input"],
        "tokens_out": new_cell["subagent"]["tokens"]["output"],
        "duration_s": new_cell["subagent"]["duration_seconds"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="backfill")
    p.add_argument("--run", required=True)
    args = p.parse_args(argv)

    rd = _io.run_dir(args.run)
    if not rd.exists():
        print(f"backfill: run dir {rd} does not exist")
        return 1

    sidechains = _all_tester_sidechains()
    pre_tools = _pre_tools_by_arm_trial(_io.raw_dir(args.run), args.run)

    if not sidechains:
        print("backfill: no tester sidechains discovered via meta.json descriptions")
        return 1

    total = 0
    for arm in ("A", "C"):
        arm_dir = rd / f"arm-{arm}"
        if not arm_dir.exists():
            continue
        for cell_path in sorted(arm_dir.glob("*.json")):
            summary = backfill_cell(cell_path, sidechains=sidechains, pre_tools=pre_tools)
            print(json.dumps(summary, separators=(",", ":")))
            total += 1
    print(f"backfill: processed {total} cell(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
