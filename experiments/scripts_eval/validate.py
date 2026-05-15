"""validate.py — fills the 'validation' block on every per-cell JSON.

Each expected_evidence entry is either a substring (case-insensitive)
or a regex in /pattern/ form. score = len(found) / len(expected).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

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
