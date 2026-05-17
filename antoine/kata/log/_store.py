"""LogStore — append-only shape index, one file per UTC day.

Layout under ``root`` (defaults to ``./.antoine/log``):

    <YYYY-MM-DD>.jsonl   one line per LogEntry whose ts falls on that day

No IO beyond append + sequential read happens here. Raw args live in a
sibling sidecar handled by ``_args.py`` (next task).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from antoine.kata.log._schema import LogEntry


class LogStore:
    """Append-only daily-sharded JSONL store."""

    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path.cwd() / ".antoine" / "log"
        self.root = root

    def _file_for(self, ts: str) -> Path:
        # ts is ISO-8601 UTC; YYYY-MM-DD is the first 10 chars.
        return self.root / f"{ts[:10]}.jsonl"

    def append(self, entry: LogEntry) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._file_for(entry.ts)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(entry.to_json_line())

    def read_all(self) -> Iterator[LogEntry]:
        """Yield entries in chronological order across all shard files."""
        if not self.root.exists():
            return
        shards = sorted(self.root.glob("*.jsonl"))
        for shard in shards:
            with shard.open("r", encoding="utf-8") as fp:
                for line_no, raw in enumerate(fp, start=1):
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    try:
                        yield LogEntry.from_json_line(stripped)
                    except (ValueError, TypeError) as exc:
                        # ValueError covers json.JSONDecodeError (subclass) and
                        # the explicit raises in LogEntry. TypeError is
                        # belt-and-suspenders for any unexpected dataclass
                        # construction failure — schema evolution is otherwise
                        # tolerated by from_json_line dropping unknown fields.
                        raise ValueError(f"log corrupted: {shard.name}:{line_no}: {exc}") from exc
