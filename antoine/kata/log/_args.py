"""ArgsSidecar — raw args kept separately from the shape index.

This is the privacy-sensitive half of the log. TTL gc deletes this
directory first; the shape index can be retained longer if the user wants
aggregate stats without raw content.

Files live at <root>/args/<session>.jsonl, one JSON object per line.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class ArgsSidecar:
    """Per-session JSONL store for raw tool args."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.args_dir = root / "args"

    def _file_for(self, session: str) -> Path:
        return self.args_dir / f"{session}.jsonl"

    def append(self, session: str, args: dict[str, Any]) -> None:
        self.args_dir.mkdir(parents=True, exist_ok=True)
        path = self._file_for(session)
        with path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(args, ensure_ascii=False, separators=(",", ":")) + "\n")

    def read(self, session: str) -> Iterator[dict[str, Any]]:
        path = self._file_for(session)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fp:
            for raw in fp:
                stripped = raw.strip()
                if not stripped:
                    continue
                yield json.loads(stripped)
