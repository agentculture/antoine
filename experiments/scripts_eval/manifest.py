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
            cwd=_io.REPO_ROOT,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=_io.REPO_ROOT,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _utcnow() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def init(
    run_id: str,
    *,
    corpus_path: Path,
    operator_model: str,
    judge_model: str,
    rubric_version: str,
    now=_utcnow,
    git_sha=_git_sha,
    git_branch=_git_branch,
) -> Path:
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
    out = init(
        args.run,
        corpus_path=Path(args.corpus),
        operator_model=args.operator_model,
        judge_model=args.judge_model,
        rubric_version=args.rubric_version,
    )
    print(f"manifest: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
