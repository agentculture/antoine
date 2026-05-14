"""seer — codebase lookup and indexing for agent skills (greenfield AgentCulture sibling)."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _v

try:
    __version__ = _v("seer-cli")
except PackageNotFoundError:  # pragma: no cover  — editable install without metadata
    __version__ = "0.0.0+local"

__all__ = ["__version__"]
