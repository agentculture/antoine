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

Respond with a single-line JSON object:
{{"winner": "X" or "Y" or "tie", "margin": "tie" or "slight" or "clear" \
or "decisive", "reasoning": "one short sentence"}}.
"""


def _ask_judge(
    client, *, judge_model: str, rubric: str, question: str, answer_x: str, answer_y: str
) -> dict:
    msg = client.messages.create(
        model=judge_model,
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": PROMPT_TEMPLATE.format(
                    rubric=rubric,
                    question=question,
                    answer_x=answer_x,
                    answer_y=answer_y,
                ),
            }
        ],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    # Extract the first JSON object from the response.
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"judge returned non-JSON: {text[:200]!r}")
    return json.loads(match.group(0))


def process_run(
    run_id: str,
    *,
    client,
    rubric_text: str,
    rubric_version: str,
    judge_model: str,
    rng: random.Random,
) -> int:
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
        verdict = _ask_judge(
            client,
            judge_model=judge_model,
            rubric=rubric_text,
            question=question,
            answer_x=ans_x,
            answer_y=ans_y,
        )
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
    p.add_argument("--rubric", default="experiments/scripts_eval/judge_rubric.md")
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
        rng=random.Random(args.seed),  # noqa: S311
    )
    print(f"judge: scored {n} pair(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
