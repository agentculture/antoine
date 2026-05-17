"""Smoke test: kata.log package is importable and exposes nothing yet."""

from __future__ import annotations


def test_kata_log_package_imports() -> None:
    import antoine.kata.log as mod

    # Cell 1 keeps __init__ empty — callers import from private modules
    # (_schema, _store, _args, _gc) directly; nothing is re-exported yet.
    assert mod.__name__ == "antoine.kata.log"
