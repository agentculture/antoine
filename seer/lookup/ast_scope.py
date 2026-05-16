"""seer.lookup.ast_scope — AST-based scope resolver (stdlib ast only).

Provides:
  Scope          — frozen dataclass describing a named code scope.
  list_symbols   — collect all module-level + class-method scopes.
  find_enclosing — smallest scope whose line range contains a given line.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

__all__ = ["Scope", "list_symbols", "find_enclosing"]


@dataclass(frozen=True)
class Scope:
    kind: str  # "function" | "async_function" | "class"
    name: str  # qualified, e.g. "Foo.method_a"
    start_line: int
    end_line: int


def list_symbols(tree: ast.AST) -> list[Scope]:
    """Walk *tree* and return one :class:`Scope` per named scope.

    Covers:
    - Module-level functions, async functions, and classes.
    - Methods defined directly inside a class (one level of nesting per
      class, but classes inside classes recurse so ``Outer.Inner.method``
      is emitted correctly).

    Does **not** recurse into function bodies.
    """
    out: list[Scope] = []

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                if isinstance(child, ast.AsyncFunctionDef):
                    kind = "async_function"
                elif isinstance(child, ast.ClassDef):
                    kind = "class"
                else:
                    kind = "function"
                end = child.end_lineno or child.lineno
                out.append(Scope(kind=kind, name=name, start_line=child.lineno, end_line=end))
                if isinstance(child, ast.ClassDef):
                    visit(child, prefix=f"{name}.")

    visit(tree)
    return out


def find_enclosing(tree: ast.AST, line: int) -> Scope | None:
    """Return the smallest :class:`Scope` whose ``[start_line, end_line]``
    contains *line*, or ``None`` for module-level lines.
    """
    best: Scope | None = None
    for s in list_symbols(tree):
        if s.start_line <= line <= s.end_line:
            if best is None or (s.end_line - s.start_line) < (best.end_line - best.start_line):
                best = s
    return best
