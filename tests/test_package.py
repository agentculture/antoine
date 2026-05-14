"""Package-level smoke test."""

from __future__ import annotations

import seer


def test_version_is_a_nonempty_string() -> None:
    assert isinstance(seer.__version__, str)
    assert seer.__version__
