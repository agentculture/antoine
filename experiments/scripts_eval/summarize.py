"""summarize.py — accumulate per-set scripts-eval evidence into a single
tracked markdown file.

Reads ``results/<run_id>/arm-A/`` and ``arm-C/``, groups cells by
``(repo_id, question_id)``, and emits two markdown fragments that
replace the contents between marker comments in a tracked evidence
file:

* ``<!-- runstate:start -->`` / ``<!-- runstate:end -->`` — a per-set
  progress table (trials captured per arm, trials judged, winner tally).
* ``<!-- evidence:start -->`` / ``<!-- evidence:end -->`` — one section
  per set with the verdict table (trial → winner → margin → reasoning).

The script is idempotent: re-running on the same run id rewrites both
sections to reflect current on-disk state, so the operator can call it
at the end of every session without thinking about state.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from experiments.scripts_eval import _io

RUNSTATE_START = "<!-- runstate:start -->"
RUNSTATE_END = "<!-- runstate:end -->"
EVIDENCE_START = "<!-- evidence:start -->"
EVIDENCE_END = "<!-- evidence:end -->"

# Matches corpus.yaml config.trials_per_cell. Hard-coded here so the
# script has no YAML dependency; if the corpus ever bumps the trial
# count, update both.
TRIALS_PER_CELL = 3


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------


def _load_cells(run_id: str, arm: str) -> list[dict]:
    arm_dir = _io.arm_dir(run_id, arm)
    if not arm_dir.exists():
        return []
    return [_io.read_json(fp) for fp in arm_dir.glob("*.json")]


def _set_key(cell: dict) -> tuple:
    return (cell.get("repo_id"), cell["question_id"])


def collect_run_state(run_id: str) -> list[dict]:
    """Walk arm-A and arm-C, group by ``(repo_id, question_id)``.

    Returns one dict per set, sorted by ``(repo_id, question_id)``.
    Each dict carries trial counts, judged-trial list, winner tally,
    and per-verdict details (winner, margin, reasoning, durations,
    tools used per arm) for rendering.
    """
    groups: dict[tuple, dict] = defaultdict(lambda: {"arm_a": {}, "arm_c": {}})
    for cell in _load_cells(run_id, "A"):
        groups[_set_key(cell)]["arm_a"][cell["trial"]] = cell
    for cell in _load_cells(run_id, "C"):
        groups[_set_key(cell)]["arm_c"][cell["trial"]] = cell

    out = []
    for key in sorted(groups.keys(), key=lambda k: (k[0] or "", k[1])):
        repo_id, qid = key
        grp = groups[key]
        a_trials = sorted(grp["arm_a"].keys())
        c_trials = sorted(grp["arm_c"].keys())

        judged_trials: list[int] = []
        winners = {"A": 0, "C": 0, "tie": 0}
        verdicts: list[dict] = []

        for trial in sorted(set(a_trials) & set(c_trials)):
            a_cell = grp["arm_a"][trial]
            c_cell = grp["arm_c"][trial]
            judge = a_cell.get("judge") or c_cell.get("judge")
            if not judge:
                continue
            cmp_ = judge.get("comparison", {}) or {}
            w = cmp_.get("winner")
            if w not in winners:
                continue
            winners[w] += 1
            judged_trials.append(trial)
            verdicts.append(
                {
                    "trial": trial,
                    "winner": w,
                    "margin": cmp_.get("margin", ""),
                    "reasoning": cmp_.get("reasoning", ""),
                    "a_duration": (a_cell.get("subagent") or {}).get("duration_seconds"),
                    "c_duration": (c_cell.get("subagent") or {}).get("duration_seconds"),
                    "a_tools": (a_cell.get("subagent") or {}).get("tools_used", []),
                    "c_tools": (c_cell.get("subagent") or {}).get("tools_used", []),
                }
            )

        out.append(
            {
                "repo_id": repo_id,
                "question_id": qid,
                "arm_a_trials": a_trials,
                "arm_c_trials": c_trials,
                "judged_trials": judged_trials,
                "winners": winners,
                "verdicts": verdicts,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_runstate_table(state: list[dict]) -> str:
    if not state:
        return "*No sets captured yet.*\n"
    lines = [
        "| target | question | arm-A | arm-C | judged | winners (A/C/tie) |",
        "|---|---|---|---|---|---|",
    ]
    for s in state:
        target = s["repo_id"] or "_workspace_"
        a = f"{len(s['arm_a_trials'])}/{TRIALS_PER_CELL}"
        c = f"{len(s['arm_c_trials'])}/{TRIALS_PER_CELL}"
        j = f"{len(s['judged_trials'])}/{TRIALS_PER_CELL}"
        w = s["winners"]
        winners_str = f"{w['A']}/{w['C']}/{w['tie']}"
        lines.append(f"| {target} | {s['question_id']} | {a} | {c} | {j} | {winners_str} |")
    return "\n".join(lines) + "\n"


def _fmt_tools(tools: list) -> str:
    if not tools:
        return "—"
    parts = [f"{t.get('name')}:{t.get('count')}" for t in tools]
    return ", ".join(parts)


def render_evidence_sections(state: list[dict]) -> str:
    if not state:
        return "*No verdicts captured yet.*\n"
    parts: list[str] = []
    for s in state:
        target = s["repo_id"] or "_workspace_"
        parts.append(f"### {target} / {s['question_id']}\n")
        if not s["verdicts"]:
            parts.append("*No judged trials yet.*\n")
            continue
        w = s["winners"]
        parts.append(
            f"Winners: **A={w['A']}, C={w['C']}, tie={w['tie']}** "
            f"(of {len(s['verdicts'])} judged).\n"
        )
        parts.append(
            "| trial | winner | margin | A duration | C duration "
            "| A tools | C tools | judge reasoning |"
        )
        parts.append("|---|---|---|---|---|---|---|---|")
        for v in s["verdicts"]:
            reason = (v["reasoning"] or "").replace("|", "\\|").replace("\n", " ")
            a_dur = f"{v['a_duration']:.1f}s" if v["a_duration"] is not None else "—"
            c_dur = f"{v['c_duration']:.1f}s" if v["c_duration"] is not None else "—"
            parts.append(
                f"| {v['trial']} | {v['winner']} | {v['margin']} | "
                f"{a_dur} | {c_dur} | "
                f"{_fmt_tools(v['a_tools'])} | {_fmt_tools(v['c_tools'])} | "
                f"{reason} |"
            )
        parts.append("")  # blank line between sets
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Update the tracked evidence file
# ---------------------------------------------------------------------------


_ALL_MARKERS = (RUNSTATE_START, RUNSTATE_END, EVIDENCE_START, EVIDENCE_END)


def _escape_markers_in_payload(payload: str) -> str:
    """Disarm any literal section-marker strings that happen to appear
    inside *payload*.

    Without this, a judge's reasoning that verbatim contains
    ``<!-- evidence:end -->`` would, after one update, leave that
    literal in the rendered table. The next ``update_evidence_file``
    call would then find that inner ``<!-- evidence:end -->`` first
    (before the proper one) and slice the wrong region, corrupting
    the file and breaking idempotence.

    The escape rewrites ``<!--`` to ``<\\!--`` only inside the literal
    marker strings — markdown renderers display the backslash-escaped
    form identically to the original, and ``str.find`` no longer
    matches it as a marker on subsequent passes.
    """
    out = payload
    for marker in _ALL_MARKERS:
        if marker in out:
            out = out.replace(marker, marker.replace("<!--", "<\\!--"))
    return out


def _replace_between(text: str, start_marker: str, end_marker: str, payload: str) -> str:
    """Replace the content between *start_marker* and *end_marker* in *text*.

    Uses index-based slicing on the *original* text instead of a regex,
    so the inserted payload can contain anything — including the literal
    marker strings in a judge's reasoning — without risk of the next
    call truncating at an inner occurrence and corrupting the file.

    The replacement always targets *the first* start_marker and *the
    first* end_marker that follows it. Subsequent occurrences anywhere
    in *text* (e.g., inside the payload from a prior call) are left
    alone.
    """
    start_idx = text.find(start_marker)
    if start_idx == -1:
        raise ValueError(f"start marker not found in evidence file: {start_marker!r}")
    end_idx = text.find(end_marker, start_idx + len(start_marker))
    if end_idx == -1:
        raise ValueError(f"end marker not found after start: {end_marker!r}")
    return (
        text[:start_idx]
        + f"{start_marker}\n\n{payload}\n{end_marker}"
        + text[end_idx + len(end_marker) :]
    )


def update_evidence_file(run_id: str, path: Path) -> None:
    """Rewrite the marked sections of *path* with current state for *run_id*."""
    if not path.exists():
        raise ValueError(f"evidence file not found: {path}")
    state = collect_run_state(run_id)
    runstate = _escape_markers_in_payload(render_runstate_table(state))
    evidence = _escape_markers_in_payload(render_evidence_sections(state))
    text = path.read_text(encoding="utf-8")
    text = _replace_between(text, RUNSTATE_START, RUNSTATE_END, runstate)
    text = _replace_between(text, EVIDENCE_START, EVIDENCE_END, evidence)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="summarize")
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True, help="path to the evidence markdown file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    update_evidence_file(args.run, Path(args.out))
    print(f"summarize: updated {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
