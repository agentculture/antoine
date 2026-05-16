"""summarize.py — accumulate per-set scripts-eval evidence into a single
tracked markdown file.

Reads ``results/<run_id>/arm-{A,B,C}/``, groups cells by
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


def _get_judge_block(cell_x: dict, cell_y: dict, pair: str) -> dict | None:
    """Return the judge block for *pair* if present on either cell.

    Prefers the new ``cell["judges"][pair]`` schema. For the AC pair,
    also falls back to the legacy ``cell["judge"]`` field so cells
    written before phase 2 still summarize correctly.
    """
    for c in (cell_x, cell_y):
        judges = c.get("judges") or {}
        if pair in judges and judges[pair]:
            return judges[pair]
    if pair == "AC":
        for c in (cell_x, cell_y):
            legacy = c.get("judge")
            if legacy:
                return legacy
    return None


def _collect_pair_verdicts(
    grp: dict,
    *,
    pair: str,
    arm_x_trials: list[int],
    arm_y_trials: list[int],
    arm_x_key: str,
    arm_y_key: str,
) -> tuple[list[int], dict, list[dict]]:
    """Walk the trial intersection for *pair*; collect verdicts.

    Returns ``(judged_trials, winners, verdicts)`` shaped for the
    render layer. *winners* keys are the two arm letters + ``"tie"``.
    """
    arm_x, arm_y = pair[0], pair[1]
    winners = {arm_x: 0, arm_y: 0, "tie": 0}
    judged_trials: list[int] = []
    verdicts: list[dict] = []
    for trial in sorted(set(arm_x_trials) & set(arm_y_trials)):
        cell_x = grp[arm_x_key][trial]
        cell_y = grp[arm_y_key][trial]
        block = _get_judge_block(cell_x, cell_y, pair)
        if not block:
            continue
        cmp_ = block.get("comparison", {}) or {}
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
                "x_arm": arm_x,
                "y_arm": arm_y,
                "x_duration": (cell_x.get("subagent") or {}).get("duration_seconds"),
                "y_duration": (cell_y.get("subagent") or {}).get("duration_seconds"),
                "x_tools": (cell_x.get("subagent") or {}).get("tools_used", []),
                "y_tools": (cell_y.get("subagent") or {}).get("tools_used", []),
            }
        )
    return judged_trials, winners, verdicts


def collect_run_state(run_id: str) -> list[dict]:
    """Walk arm-A, arm-B, and arm-C; group by ``(repo_id, question_id)``.

    For each set, collects both A-vs-C judges (legacy + new schema)
    and A-vs-B judges (new schema only). The accumulator renders both
    pair-wise winner tallies; the per-pair verdict tables expand into
    separate sections.
    """
    groups: dict[tuple, dict] = defaultdict(lambda: {"arm_a": {}, "arm_b": {}, "arm_c": {}})
    for cell in _load_cells(run_id, "A"):
        groups[_set_key(cell)]["arm_a"][cell["trial"]] = cell
    for cell in _load_cells(run_id, "B"):
        groups[_set_key(cell)]["arm_b"][cell["trial"]] = cell
    for cell in _load_cells(run_id, "C"):
        groups[_set_key(cell)]["arm_c"][cell["trial"]] = cell

    out = []
    for key in sorted(groups.keys(), key=lambda k: (k[0] or "", k[1])):
        repo_id, qid = key
        grp = groups[key]
        a_trials = sorted(grp["arm_a"].keys())
        b_trials = sorted(grp["arm_b"].keys())
        c_trials = sorted(grp["arm_c"].keys())

        ac_judged, ac_winners, ac_verdicts = _collect_pair_verdicts(
            grp,
            pair="AC",
            arm_x_trials=a_trials,
            arm_y_trials=c_trials,
            arm_x_key="arm_a",
            arm_y_key="arm_c",
        )
        ab_judged, ab_winners, ab_verdicts = _collect_pair_verdicts(
            grp,
            pair="AB",
            arm_x_trials=a_trials,
            arm_y_trials=b_trials,
            arm_x_key="arm_a",
            arm_y_key="arm_b",
        )

        out.append(
            {
                "repo_id": repo_id,
                "question_id": qid,
                "arm_a_trials": a_trials,
                "arm_b_trials": b_trials,
                "arm_c_trials": c_trials,
                # Back-compat aliases (used by render_runstate_table /
                # render_evidence_sections + existing tests).
                "judged_trials": ac_judged,
                "winners": ac_winners,
                "verdicts": ac_verdicts,
                # Explicit pair-aware containers.
                "ac_judged_trials": ac_judged,
                "ac_winners": ac_winners,
                "ac_verdicts": ac_verdicts,
                "ab_judged_trials": ab_judged,
                "ab_winners": ab_winners,
                "ab_verdicts": ab_verdicts,
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
        "| target | question | arm-A | arm-B | arm-C | "
        "A-vs-B judged | A-vs-B (A/B/tie) | "
        "A-vs-C judged | A-vs-C (A/C/tie) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in state:
        target = s["repo_id"] or "_workspace_"
        a = f"{len(s['arm_a_trials'])}/{TRIALS_PER_CELL}"
        b = f"{len(s['arm_b_trials'])}/{TRIALS_PER_CELL}"
        c = f"{len(s['arm_c_trials'])}/{TRIALS_PER_CELL}"
        jab = f"{len(s['ab_judged_trials'])}/{TRIALS_PER_CELL}"
        jac = f"{len(s['ac_judged_trials'])}/{TRIALS_PER_CELL}"
        wab = s["ab_winners"]
        wac = s["ac_winners"]
        ab_str = f"{wab['A']}/{wab['B']}/{wab['tie']}"
        ac_str = f"{wac['A']}/{wac['C']}/{wac['tie']}"
        lines.append(
            f"| {target} | {s['question_id']} | {a} | {b} | {c} "
            f"| {jab} | {ab_str} | {jac} | {ac_str} |"
        )
    return "\n".join(lines) + "\n"


def _fmt_tools(tools: list) -> str:
    if not tools:
        return "—"
    parts = [f"{t.get('name')}:{t.get('count')}" for t in tools]
    return ", ".join(parts)


def _render_pair_table(verdicts: list[dict], winners: dict, *, pair_label: str) -> list[str]:
    """Render one pair's verdict table; returns markdown lines (no trailing newline)."""
    if not verdicts:
        return [f"*No {pair_label} verdicts yet.*"]
    arm_x, arm_y = pair_label[0], pair_label[1]
    parts: list[str] = []
    parts.append(
        f"**{pair_label}** winners: "
        f"{arm_x}={winners[arm_x]}, {arm_y}={winners[arm_y]}, "
        f"tie={winners['tie']} (of {len(verdicts)} judged).\n"
    )
    parts.append(
        f"| trial | winner | margin | {arm_x} duration | {arm_y} duration "
        f"| {arm_x} tools | {arm_y} tools | judge reasoning |"
    )
    parts.append("|---|---|---|---|---|---|---|---|")
    for v in verdicts:
        reason = (v["reasoning"] or "").replace("|", "\\|").replace("\n", " ")
        x_dur = f"{v['x_duration']:.1f}s" if v["x_duration"] is not None else "—"
        y_dur = f"{v['y_duration']:.1f}s" if v["y_duration"] is not None else "—"
        parts.append(
            f"| {v['trial']} | {v['winner']} | {v['margin']} | "
            f"{x_dur} | {y_dur} | "
            f"{_fmt_tools(v['x_tools'])} | {_fmt_tools(v['y_tools'])} | "
            f"{reason} |"
        )
    return parts


def render_evidence_sections(state: list[dict]) -> str:
    if not state:
        return "*No verdicts captured yet.*\n"
    parts: list[str] = []
    for s in state:
        target = s["repo_id"] or "_workspace_"
        parts.append(f"### {target} / {s['question_id']}\n")
        if not s["ab_verdicts"] and not s["ac_verdicts"]:
            parts.append("*No judged trials yet.*\n")
            continue
        parts.extend(_render_pair_table(s["ab_verdicts"], s["ab_winners"], pair_label="AB"))
        parts.append("")
        parts.extend(_render_pair_table(s["ac_verdicts"], s["ac_winners"], pair_label="AC"))
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
