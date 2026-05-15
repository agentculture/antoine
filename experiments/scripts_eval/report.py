"""report.py — roll a run directory up into a single REPORT.md."""

from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median

from experiments.scripts_eval import _io

VIOLATION_PATTERNS = (
    "scripts/profile.sh",
    "scripts/connections.sh",
    "scripts/graph.sh",
    "seer.repo",
    "seer/repo",
    "python -m seer",
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
            key = (
                cell.get("repo_id") or "_workspace_",
                cell["question_id"],
                cell["trial"],
            )
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
            parts.append(
                f"Winner: **{cmp_.get('winner', '?')}** "
                f"({cmp_.get('margin', '?')}) — {cmp_.get('reasoning', '')}"
            )
        parts.append(f"validation A={av.get('score', '-')} / C={cv.get('score', '-')}")
        a_dur = (a.get("subagent") or {}).get("duration_seconds")
        c_dur = (c.get("subagent") or {}).get("duration_seconds")
        a_tok = ((a.get("subagent") or {}).get("tokens") or {}).get("input", 0) + (
            (a.get("subagent") or {}).get("tokens") or {}
        ).get("output", 0)
        c_tok = ((c.get("subagent") or {}).get("tokens") or {}).get("input", 0) + (
            (c.get("subagent") or {}).get("tokens") or {}
        ).get("output", 0)
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
    sections = [
        f"# scripts-eval — run `{run_id}`",
        "",
        _aggregate(by_pair),
        "",
    ]
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
