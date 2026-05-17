"""TTL gc — deletes shape + args past TTL; raises on permission failure."""

from __future__ import annotations

import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from antoine.kata.log._gc import GCResult, gc


def _touch(path: Path, days_old: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("payload\n")
    age = (datetime.now(timezone.utc) - timedelta(days=days_old)).timestamp()
    os.utime(path, (age, age))


def test_gc_deletes_files_past_ttl(tmp_path: Path) -> None:
    fresh = tmp_path / "2026-05-16.jsonl"
    stale = tmp_path / "2026-05-01.jsonl"
    _touch(fresh, days_old=2)
    _touch(stale, days_old=10)

    result = gc(root=tmp_path, ttl_days=7)
    assert result.deleted_shape == [stale]
    assert result.deleted_args == []
    assert fresh.exists()
    assert not stale.exists()


def test_gc_deletes_args_first(tmp_path: Path) -> None:
    args_old = tmp_path / "args" / "old.jsonl"
    args_fresh = tmp_path / "args" / "fresh.jsonl"
    _touch(args_old, days_old=10)
    _touch(args_fresh, days_old=2)

    result = gc(root=tmp_path, ttl_days=7)
    assert result.deleted_args == [args_old]
    assert not args_old.exists()
    assert args_fresh.exists()


def test_gc_on_empty_store_is_noop(tmp_path: Path) -> None:
    result = gc(root=tmp_path, ttl_days=7)
    assert result == GCResult(deleted_shape=[], deleted_args=[])


def test_gc_raises_on_permission_error(tmp_path: Path) -> None:
    stale = tmp_path / "2026-05-01.jsonl"
    _touch(stale, days_old=10)
    # Lock the parent dir read-only so unlink fails.
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(PermissionError):
            gc(root=tmp_path, ttl_days=7)
    finally:
        # Restore for cleanup.
        tmp_path.chmod(stat.S_IRWXU)


def test_gc_rejects_negative_ttl(tmp_path: Path) -> None:
    """Engine-level guard against the negative-TTL log-wipe footgun."""
    fresh = tmp_path / "2026-05-17.jsonl"
    _touch(fresh, days_old=1)
    with pytest.raises(ValueError, match="ttl_days must be >= 0"):
        gc(root=tmp_path, ttl_days=-1)
    # The file is still there — guard fires BEFORE any unlink.
    assert fresh.exists()
