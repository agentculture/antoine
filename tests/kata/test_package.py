"""Smoke test: kata.log package is importable and exposes nothing yet."""

from __future__ import annotations


def test_kata_log_package_imports() -> None:
    import antoine.kata.log as mod

    # Cell 1 starts with no public API; later tasks will add LogEntry etc.
    assert mod.__name__ == "antoine.kata.log"
