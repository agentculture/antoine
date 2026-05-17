"""Tests for antoine.lookup.ast_scope — Scope, list_symbols, find_enclosing."""

from __future__ import annotations

import ast

from antoine.lookup.ast_scope import Scope, find_enclosing, list_symbols

SRC = """class Foo:
    def method_a(self):
        pass
    async def method_b(self):
        pass

def top_level():
    pass
"""


# ---------------------------------------------------------------------------
# C1 — list_symbols
# ---------------------------------------------------------------------------


def test_list_symbols_basic():
    tree = ast.parse(SRC)
    symbols = list_symbols(tree)
    assert symbols == [
        Scope(kind="class", name="Foo", start_line=1, end_line=5),
        Scope(kind="function", name="Foo.method_a", start_line=2, end_line=3),
        Scope(kind="async_function", name="Foo.method_b", start_line=4, end_line=5),
        Scope(kind="function", name="top_level", start_line=7, end_line=8),
    ]


def test_list_symbols_empty_source():
    tree = ast.parse("")
    assert list_symbols(tree) == []


def test_list_symbols_nested_class():
    src = """class Outer:
    class Inner:
        def method(self):
            pass
"""
    tree = ast.parse(src)
    symbols = list_symbols(tree)
    names = [s.name for s in symbols]
    assert "Outer" in names
    assert "Outer.Inner" in names
    assert "Outer.Inner.method" in names


# ---------------------------------------------------------------------------
# C2 — find_enclosing
# ---------------------------------------------------------------------------


def test_find_enclosing_function_body():
    tree = ast.parse(SRC)
    scope = find_enclosing(tree, 2)
    assert scope is not None
    assert scope.name == "Foo.method_a"
    assert scope.kind == "function"


def test_find_enclosing_module_level_returns_none():
    tree = ast.parse(SRC)
    # Line 6 is the blank line between Foo and top_level
    assert find_enclosing(tree, 6) is None


def test_find_enclosing_top_level_function():
    tree = ast.parse(SRC)
    scope = find_enclosing(tree, 7)
    assert scope is not None
    assert scope.name == "top_level"
