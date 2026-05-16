"""seer.lookup — codebase classification + lookup verbs.

This package is the sibling of `seer.repo`: it answers "what kind of project
is this?" / "where is X?" rather than "tell me about this repo."
"""

from __future__ import annotations

from seer.lookup.ast_scope import Scope, find_enclosing, list_symbols
from seer.lookup.classify import classify
from seer.lookup.grep_context import grep_with_context, render_grep_markdown
from seer.lookup.render import render_classify_markdown

__all__ = [
    "classify",
    "find_enclosing",
    "grep_with_context",
    "list_symbols",
    "render_classify_markdown",
    "render_grep_markdown",
    "Scope",
]
