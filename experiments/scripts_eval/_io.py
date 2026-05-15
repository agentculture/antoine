"""Shared I/O helpers for the scripts-eval harness.

All paths resolve relative to the seer-cli repo root, so scripts work
regardless of cwd. Env-var helpers return None when unset rather than
raising — call sites decide whether the absence is fatal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "experiments" / "scripts_eval" / "results"
RAW_DIRNAME = "raw"


def eval_run_id() -> str | None:
    """Return SEER_EVAL_RUN_ID, or None if unset.

    Hooks read this first and no-op when None.
    """
    val = os.environ.get("SEER_EVAL_RUN_ID")
    return val if val else None


def eval_arm() -> str | None:
    """Return SEER_EVAL_ARM (must be 'A' or 'C'), or None if unset."""
    val = os.environ.get("SEER_EVAL_ARM")
    if val is None or val == "":
        return None
    if val not in ("A", "C"):
        raise ValueError(
            f"SEER_EVAL_ARM must be 'A' or 'C' (got {val!r})"
        )
    return val


def run_dir(run_id: str) -> Path:
    """Path to a specific run's results directory."""
    return REPO_ROOT / "experiments" / "scripts_eval" / "results" / run_id


def raw_dir(run_id: str) -> Path:
    """Path where hooks write their raw per-subagent JSONLs."""
    return run_dir(run_id) / RAW_DIRNAME


def arm_dir(run_id: str, arm: str) -> Path:
    """Path where capture.py writes per-cell JSONs for one arm."""
    return run_dir(run_id) / f"arm-{arm}"


def write_json(path: Path, data) -> None:
    """Write *data* as pretty JSON, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")


def read_json(path: Path):
    """Read JSON from *path*."""
    return json.loads(path.read_text(encoding="utf-8"))
