"""TTL gc — privacy invariant: if files past TTL exist, they MUST be deleted.

The order is intentional: raw args first (privacy-sensitive), then the
shape index. If any unlink raises ``PermissionError``, propagate it
unchanged so the caller (the ``kata log gc`` verb handler) can translate
it into an ``AntoineError`` with an actionable Fix line.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class GCResult:
    deleted_shape: list[Path] = field(default_factory=list)
    deleted_args: list[Path] = field(default_factory=list)


def _stale_files(directory: Path, ttl_seconds: float, now: float) -> list[Path]:
    if not directory.exists():
        return []
    out: list[Path] = []
    for p in sorted(directory.glob("*.jsonl")):
        if (now - p.stat().st_mtime) > ttl_seconds:
            out.append(p)
    return out


def gc(*, root: Path, ttl_days: int) -> GCResult:
    """Delete files older than ``ttl_days`` from ``root`` and ``root/args``.

    Raises ``ValueError`` on negative ``ttl_days`` — a negative TTL would
    classify every file as stale and wipe the whole log from a single typo,
    which we treat as a programming error, not silently allowed input.
    Raises ``PermissionError`` if any unlink fails — privacy invariant.
    """
    if ttl_days < 0:
        raise ValueError(f"ttl_days must be >= 0 (got {ttl_days})")
    now = time.time()
    ttl_seconds = ttl_days * 86400.0

    args_dir = root / "args"
    stale_args = _stale_files(args_dir, ttl_seconds, now)
    stale_shape = _stale_files(root, ttl_seconds, now)

    # Args first — they hold the raw, privacy-sensitive data.
    for path in stale_args:
        path.unlink()
    for path in stale_shape:
        path.unlink()

    return GCResult(deleted_shape=stale_shape, deleted_args=stale_args)
