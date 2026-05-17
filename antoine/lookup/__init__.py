"""antoine.lookup — codebase classification + lookup verbs.

This package is the sibling of `antoine.repo`: it answers "what kind of project
is this?" / "where is X?" rather than "tell me about this repo."
"""

from __future__ import annotations

from antoine.lookup.ast_scope import Scope, find_enclosing, list_symbols
from antoine.lookup.classify import classify
from antoine.lookup.grep_context import grep_with_context, render_grep_markdown
from antoine.lookup.recent_outline import recent_with_outline, render_recent_markdown
from antoine.lookup.render import render_classify_markdown

__all__ = [
    "classify",
    "find_enclosing",
    "grep_with_context",
    "list_symbols",
    "recent_with_outline",
    "render_classify_markdown",
    "render_grep_markdown",
    "render_recent_markdown",
    "Scope",
]
