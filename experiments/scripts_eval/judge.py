"""judge.py — pairwise blind judge over any two arms.

The LLM call itself is performed by an operator-dispatched Claude Code
subagent. This module owns the deterministic plumbing:

* ``prepare`` — pair cells from two arms, seed-blind their labels,
  strip the ``### tools_used`` / ``### evidence`` tails (those tails
  de-blind the comparison because arm C's tail can name
  ``scripts/profile.sh``), and emit a job dict per pair with the
  assembled subagent prompt.
* ``record`` — parse the subagent's verdict JSON, validate the
  vocabulary, de-blind the winner, and write the locked-surface
  judge block into both paired cell JSONs.

Pairs: ``--pair AC`` (default), ``--pair AB``, or ``--pair BC``. The
two letters name the two arms; the first letter's cells land at
"X" in the prompt unless blinding swaps them. Verdict storage in
each cell lives under ``cell["judges"][pair]``; for the AC pair the
legacy ``cell["judge"]`` field is also written for back-compat with
summarize.py readers that haven't migrated.

The operator-Claude bridges the two: read a prepared job, dispatch a
``general-purpose`` subagent with a description prefixed
``"scripts_eval judge: "`` (the pre_tool hook skips that prefix to
avoid polluting ``raw/``), then pipe the subagent's final text into
``record``.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Iterator

from experiments.scripts_eval import _io

# ---------------------------------------------------------------------------
# Reused from the original judge.py
# ---------------------------------------------------------------------------


def _pair_key(cell: dict) -> tuple:
    return (cell.get("repo_id"), cell["question_id"], cell["trial"])


def _load_arm(rd: Path, arm: str) -> dict:
    out = {}
    arm_path = rd / f"arm-{arm}"
    if not arm_path.exists():
        return out
    for fp in arm_path.glob("*.json"):
        cell = _io.read_json(fp)
        out[_pair_key(cell)] = (fp, cell)
    return out


# ---------------------------------------------------------------------------
# Prompt template + helpers
# ---------------------------------------------------------------------------


PROMPT_TEMPLATE = """You are a blind judge comparing two answers to the same question.

Rubric:
{rubric}

Question:
{question}

answer_X:
{answer_x}

answer_Y:
{answer_y}

Respond with a single-line JSON object:
{{"winner": "X" or "Y" or "tie", "margin": "tie" or "slight" or "clear" \
or "decisive", "reasoning": "one short sentence"}}.

Do not call any tools. Do not read any files. Produce only the single-line
JSON above as your final response."""


# Anchor each candidate heading at line start; ``re.MULTILINE`` makes ``^``
# match after newlines. The first match terminates the answer body — both
# the ``### tools_used`` and ``### evidence`` sections live after it.
_EVIDENCE_TAIL_RE = re.compile(
    r"^#{3}\s+(?:tools_used|evidence)\s*$",
    re.MULTILINE,
)


def _strip_evidence_tail(text: str) -> str:
    """Return *text* with the ``### tools_used`` / ``### evidence`` tails
    removed. The tails are produced by the tester subagent per
    ``RUNBOOK.md``; passing them through to the judge de-blinds the
    comparison.
    """
    if not text:
        return text
    match = _EVIDENCE_TAIL_RE.search(text)
    if match is None:
        return text
    return text[: match.start()].rstrip() + "\n"


def _assign_blind_labels(rng: random.Random) -> tuple[str, str]:
    """Return ``(label_for_first_arm, label_for_second_arm)`` — randomly
    one of ``('answer_X', 'answer_Y')`` or vice versa, drawn from *rng*.

    The arm letters in the pair are arbitrary at this layer; callers
    just unpack into ``(first_label, second_label)``.
    """
    first = rng.choice(["answer_X", "answer_Y"])
    second = "answer_Y" if first == "answer_X" else "answer_X"
    return first, second


VALID_PAIRS = ("AC", "AB", "BC")


def _parse_pair(pair: str) -> tuple[str, str]:
    """Return ``(arm_x, arm_y)`` for a pair string like ``"AC"``."""
    if pair not in VALID_PAIRS:
        raise ValueError(f"pair must be one of {VALID_PAIRS} (got {pair!r})")
    return pair[0], pair[1]


def _build_prompt(*, rubric: str, question: str, answer_x: str, answer_y: str) -> str:
    return PROMPT_TEMPLATE.format(
        rubric=rubric,
        question=question,
        answer_x=answer_x,
        answer_y=answer_y,
    )


def _format_pair_key(repo_id: str | None, question_id: str, trial: int) -> str:
    """Stable string key for a pair: ``<repo or _workspace_>/<qid>/<trial>``."""
    return f"{repo_id or '_workspace_'}/{question_id}/{trial}"


def _parse_pair_key(pair_key: str) -> tuple:
    """Reverse of ``_format_pair_key``. Returns ``(repo_id, qid, trial)``;
    ``repo_id`` is ``None`` for the ``_workspace_`` literal."""
    parts = pair_key.split("/")
    if len(parts) != 3:
        raise ValueError(f"pair_key must be repo/qid/trial (got {pair_key!r})")
    repo_part, qid, trial_part = parts
    try:
        trial = int(trial_part)
    except ValueError as exc:
        raise ValueError(f"pair_key trial must be int (got {trial_part!r})") from exc
    repo_id = None if repo_part == "_workspace_" else repo_part
    return repo_id, qid, trial


_WINNER_VOCAB = {"X", "Y", "tie"}
_MARGIN_VOCAB = {"tie", "slight", "clear", "decisive"}


_BLIND_LABEL_VOCAB = {"answer_X", "answer_Y"}


def _extract_json(text: str) -> dict:
    """Lift the *first* valid JSON object out of *text* and parse it.

    Scans for balanced ``{...}`` spans (respecting nested braces and
    quoted strings), tries ``json.loads`` on each candidate, and returns
    the first that parses. A greedy ``r"\\{.*\\}"`` would span from the
    first ``{`` to the *last* ``}`` and either fail or pick the wrong
    object when a chatty subagent emits multiple blobs.
    """
    n = len(text)
    last_error: json.JSONDecodeError | None = None
    for i in range(n):
        if text[i] != "{":
            continue
        depth = 0
        in_string = False
        escape = False
        for j in range(i, n):
            ch = text[j]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[i : j + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError as exc:
                        last_error = exc
                        break  # try the next opening brace
    if last_error is not None:
        raise ValueError(
            f"judge returned non-JSON ({last_error.msg}): {text[:200]!r}"
        ) from last_error
    raise ValueError(f"judge returned non-JSON: {text[:200]!r}")


def _validate_verdict(verdict: dict) -> dict:
    """Check vocabulary; raise ``ValueError`` on a malformed verdict."""
    winner = verdict.get("winner")
    if winner not in _WINNER_VOCAB:
        raise ValueError(
            f"judge verdict winner must be one of {sorted(_WINNER_VOCAB)} (got {winner!r})"
        )
    margin = verdict.get("margin")
    if margin not in _MARGIN_VOCAB:
        raise ValueError(
            f"judge verdict margin must be one of {sorted(_MARGIN_VOCAB)} (got {margin!r})"
        )
    return verdict


def _validate_blind_labels(blind_label_for_a: str, blind_label_for_c: str) -> None:
    """Reject malformed blind label pairs before any disk I/O.

    Both labels must be in ``{answer_X, answer_Y}`` and they must be
    distinct — otherwise de-blinding is ambiguous and a silent wrong
    winner would land in the locked-surface judge block.
    """
    if blind_label_for_a not in _BLIND_LABEL_VOCAB:
        raise ValueError(
            f"blind_label_for_a must be one of {sorted(_BLIND_LABEL_VOCAB)} "
            f"(got {blind_label_for_a!r})"
        )
    if blind_label_for_c not in _BLIND_LABEL_VOCAB:
        raise ValueError(
            f"blind_label_for_c must be one of {sorted(_BLIND_LABEL_VOCAB)} "
            f"(got {blind_label_for_c!r})"
        )
    if blind_label_for_a == blind_label_for_c:
        raise ValueError(
            f"blind_label_for_a and blind_label_for_c must be distinct "
            f"(both got {blind_label_for_a!r})"
        )


def _validate_pair_labels(label_x: str, label_y: str, *, arm_x: str, arm_y: str) -> None:
    """Pair-aware blind-label validator (replaces the AC-only one for new code).

    Same checks, just with the arm letters carried through so error
    messages name the actual arms in the pair.
    """
    if label_x not in _BLIND_LABEL_VOCAB:
        raise ValueError(
            f"blind_label_for_{arm_x} must be one of {sorted(_BLIND_LABEL_VOCAB)} "
            f"(got {label_x!r})"
        )
    if label_y not in _BLIND_LABEL_VOCAB:
        raise ValueError(
            f"blind_label_for_{arm_y} must be one of {sorted(_BLIND_LABEL_VOCAB)} "
            f"(got {label_y!r})"
        )
    if label_x == label_y:
        raise ValueError(
            f"blind_label_for_{arm_x} and blind_label_for_{arm_y} must be "
            f"distinct (both got {label_x!r})"
        )


def _de_blind(
    winner_letter: str,
    blind_label_for_a: str,
    blind_label_for_c: str,
) -> str:
    """Map the verdict's X/Y/tie back to A/C/tie via the blind labels.

    Callers should validate label complementarity via
    ``_validate_blind_labels`` before reaching here; the trailing
    ``ValueError`` is a defensive backstop for direct internal callers.
    """
    if winner_letter == "tie":
        return "tie"
    target = f"answer_{winner_letter}"
    if blind_label_for_a == target:
        return "A"
    if blind_label_for_c == target:
        return "C"
    # Defensive: caller passed mismatched labels.
    raise ValueError(
        f"de-blind failed: winner={winner_letter!r} "
        f"a={blind_label_for_a!r} c={blind_label_for_c!r}"
    )


def _de_blind_pair(
    winner_letter: str,
    *,
    label_x: str,
    label_y: str,
    arm_x: str,
    arm_y: str,
) -> str:
    """Generalised de-blind: map X/Y/tie back to the actual arm letter."""
    if winner_letter == "tie":
        return "tie"
    target = f"answer_{winner_letter}"
    if label_x == target:
        return arm_x
    if label_y == target:
        return arm_y
    raise ValueError(
        f"de-blind failed: winner={winner_letter!r} " f"{arm_x}={label_x!r} {arm_y}={label_y!r}"
    )


# ---------------------------------------------------------------------------
# Public API: record side
# ---------------------------------------------------------------------------


def record_verdict_pair(
    run_id: str,
    *,
    pair: str,
    pair_key: str,
    verdict_text: str,
    label_x: str,
    label_y: str,
    rubric_version: str,
    judge_model: str,
) -> tuple[Path, Path]:
    """Pair-aware verdict recorder.

    *pair* is ``"AC"`` / ``"AB"`` / ``"BC"``. *label_x* and *label_y*
    are the blind labels for the first and second arm of the pair.
    Writes the locked-surface judge block to
    ``cell["judges"][pair]`` on both cells, and — for the AC pair only
    — also mirrors it to the legacy ``cell["judge"]`` field so readers
    that haven't migrated continue to work.

    Returns ``(path_x, path_y)``. Idempotent.
    """
    arm_x, arm_y = _parse_pair(pair)
    _validate_pair_labels(label_x, label_y, arm_x=arm_x, arm_y=arm_y)
    repo_id, qid, trial = _parse_pair_key(pair_key)
    rd = _io.run_dir(run_id)
    x_by = _load_arm(rd, arm_x)
    y_by = _load_arm(rd, arm_y)
    target = (repo_id, qid, trial)
    if target not in x_by or target not in y_by:
        raise ValueError(
            f"no cells found for pair {pair_key!r} in run {run_id!r} "
            f"(arm-{arm_x}: {target in x_by}, arm-{arm_y}: {target in y_by})"
        )
    path_x, cell_x = x_by[target]
    path_y, cell_y = y_by[target]

    verdict = _validate_verdict(_extract_json(verdict_text))
    winner = _de_blind_pair(
        verdict["winner"],
        label_x=label_x,
        label_y=label_y,
        arm_x=arm_x,
        arm_y=arm_y,
    )
    block = {
        "pair": pair,
        "judge_model": judge_model,
        "rubric_version": rubric_version,
        "comparison": {
            "winner": winner,
            "margin": verdict["margin"],
            "reasoning": verdict.get("reasoning", ""),
            f"blind_label_for_{arm_x}": label_x,
            f"blind_label_for_{arm_y}": label_y,
        },
    }
    for cell in (cell_x, cell_y):
        judges = cell.setdefault("judges", {})
        judges[pair] = block
        if pair == "AC":
            cell["judge"] = block  # legacy mirror for unmigrated readers
    _io.write_json(path_x, cell_x)
    _io.write_json(path_y, cell_y)
    return path_x, path_y


def record_verdict(
    run_id: str,
    *,
    pair_key: str,
    verdict_text: str,
    blind_label_for_a: str,
    blind_label_for_c: str,
    rubric_version: str,
    judge_model: str,
) -> tuple[Path, Path]:
    """Back-compat AC-pair wrapper around ``record_verdict_pair``.

    Preserved so existing tests and any external callers keep working
    with their AC-named arguments.
    """
    return record_verdict_pair(
        run_id,
        pair="AC",
        pair_key=pair_key,
        verdict_text=verdict_text,
        label_x=blind_label_for_a,
        label_y=blind_label_for_c,
        rubric_version=rubric_version,
        judge_model=judge_model,
    )


# ---------------------------------------------------------------------------
# Public API: prepare side
# ---------------------------------------------------------------------------


def iter_jobs_pair(
    run_id: str,
    *,
    pair: str,
    rubric_text: str,
    rubric_version: str,
    judge_model: str,
    rng: random.Random,
) -> Iterator[dict]:
    """Yield one job dict per paired (arm_x, arm_y) cell in stable order.

    The RNG is consumed in pair-key order across the full sweep, so
    calling ``iter_jobs_pair`` and filtering by pair_key downstream
    produces the same blinding as a full run.

    The emitted dict carries ``blind_label_for_<arm_x>`` and
    ``blind_label_for_<arm_y>`` keys named after the actual arm letters
    in *pair*, plus a ``pair`` field echoing the pair label.
    """
    arm_x, arm_y = _parse_pair(pair)
    rd = _io.run_dir(run_id)
    x_by = _load_arm(rd, arm_x)
    y_by = _load_arm(rd, arm_y)
    pairs = sorted(set(x_by) & set(y_by))
    for key in pairs:
        repo_id, question_id, trial = key
        _, cell_x = x_by[key]
        _, cell_y = y_by[key]
        label_x, label_y = _assign_blind_labels(rng)
        answer_arm_x = _strip_evidence_tail(cell_x.get("answer_text", ""))
        answer_arm_y = _strip_evidence_tail(cell_y.get("answer_text", ""))
        if label_x == "answer_X":
            answer_x, answer_y = answer_arm_x, answer_arm_y
        else:
            answer_x, answer_y = answer_arm_y, answer_arm_x
        prompt_text = _build_prompt(
            rubric=rubric_text,
            question=cell_x.get("question_text", ""),
            answer_x=answer_x,
            answer_y=answer_y,
        )
        yield {
            "pair": pair,
            "pair_key": _format_pair_key(repo_id, question_id, trial),
            "repo_id": repo_id,
            "question_id": question_id,
            "trial": trial,
            f"blind_label_for_{arm_x}": label_x,
            f"blind_label_for_{arm_y}": label_y,
            "prompt_text": prompt_text,
            "rubric_version": rubric_version,
            "judge_model": judge_model,
        }


def iter_jobs(
    run_id: str,
    *,
    rubric_text: str,
    rubric_version: str,
    judge_model: str,
    rng: random.Random,
) -> Iterator[dict]:
    """Back-compat AC-pair wrapper around ``iter_jobs_pair``."""
    yield from iter_jobs_pair(
        run_id,
        pair="AC",
        rubric_text=rubric_text,
        rubric_version=rubric_version,
        judge_model=judge_model,
        rng=rng,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_prepare(args: argparse.Namespace) -> int:
    rubric_text = Path(args.rubric).read_text(encoding="utf-8")
    rng = random.Random(args.seed)  # noqa: S311 — non-cryptographic blinding
    jobs = list(
        iter_jobs_pair(
            args.run,
            pair=args.pair,
            rubric_text=rubric_text,
            rubric_version=args.rubric_version,
            judge_model=args.judge_model,
            rng=rng,
        )
    )
    if args.list:
        for job in jobs:
            print(job["pair_key"])
        return 0
    if args.pair_key:
        matches = [j for j in jobs if j["pair_key"] == args.pair_key]
        if not matches:
            print(f"prepare: no pair {args.pair_key!r} in run {args.run!r}", file=sys.stderr)
            return 1
        print(json.dumps(matches[0]))
        return 0
    # Emit JSONL (one job per line) so the operator can iterate.
    for job in jobs:
        print(json.dumps(job))
    return 0


_LABEL_FLAGS = {
    "A": "blind_label_for_a",
    "B": "blind_label_for_b",
    "C": "blind_label_for_c",
}


def _cmd_record(args: argparse.Namespace) -> int:
    if args.verdict_file == "-":
        verdict_text = sys.stdin.read()
    elif args.verdict_file is not None:
        verdict_text = Path(args.verdict_file).read_text(encoding="utf-8")
    elif args.verdict_text is not None:
        verdict_text = args.verdict_text
    else:
        print("record: provide --verdict-text or --verdict-file", file=sys.stderr)
        return 2
    arm_x, arm_y = _parse_pair(args.pair)
    label_x = getattr(args, _LABEL_FLAGS[arm_x])
    label_y = getattr(args, _LABEL_FLAGS[arm_y])
    if label_x is None or label_y is None:
        print(
            f"record: --pair {args.pair} requires "
            f"--blind-label-for-{arm_x.lower()} and "
            f"--blind-label-for-{arm_y.lower()}",
            file=sys.stderr,
        )
        return 2
    try:
        path_x, path_y = record_verdict_pair(
            args.run,
            pair=args.pair,
            pair_key=args.pair_key,
            verdict_text=verdict_text,
            label_x=label_x,
            label_y=label_y,
            rubric_version=args.rubric_version,
            judge_model=args.judge_model,
        )
    except ValueError as exc:
        print(f"record: {exc}", file=sys.stderr)
        return 1
    print(f"{path_x}\n{path_y}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="judge")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("prepare", help="emit subagent job(s) for paired cells")
    pp.add_argument("--run", required=True)
    pp.add_argument(
        "--pair",
        default="AC",
        choices=list(VALID_PAIRS),
        help="arm pair to judge; default AC for back-compat",
    )
    pp.add_argument(
        "--rubric",
        default="experiments/scripts_eval/judge_rubric.md",
        help="path to the rubric markdown file",
    )
    pp.add_argument("--rubric-version", default="v1")
    pp.add_argument("--judge-model", default="subagent:claude-opus-4-7")
    pp.add_argument("--seed", type=int, default=0)
    pp.add_argument(
        "--pair-key",
        default=None,
        help="emit only the job for this pair_key (repo/qid/trial)",
    )
    pp.add_argument(
        "--list",
        action="store_true",
        help="list available pair_keys, one per line",
    )
    pp.set_defaults(func=_cmd_prepare)

    rp = sub.add_parser("record", help="write a subagent verdict back to both cells")
    rp.add_argument("--run", required=True)
    rp.add_argument(
        "--pair",
        default="AC",
        choices=list(VALID_PAIRS),
        help="arm pair to judge; default AC for back-compat",
    )
    rp.add_argument("--pair-key", required=True)
    g = rp.add_mutually_exclusive_group()
    g.add_argument("--verdict-text", default=None, help="inline verdict JSON text")
    g.add_argument(
        "--verdict-file",
        default=None,
        help="path to a file holding the verdict text, or '-' for stdin",
    )
    # All three labels are optional at argparse level; the command-handler
    # checks that the two relevant for --pair are present and valid.
    rp.add_argument("--blind-label-for-a", default=None, choices=["answer_X", "answer_Y"])
    rp.add_argument("--blind-label-for-b", default=None, choices=["answer_X", "answer_Y"])
    rp.add_argument("--blind-label-for-c", default=None, choices=["answer_X", "answer_Y"])
    rp.add_argument("--rubric-version", default="v1")
    rp.add_argument("--judge-model", default="subagent:claude-opus-4-7")
    rp.set_defaults(func=_cmd_record)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
