"""seer — codebase lookup and indexing for agent skills (greenfield AgentCulture sibling)."""

from importlib.metadata import PackageNotFoundError, packages_distributions
from importlib.metadata import version as _v


def _resolve_version() -> str:
    """Resolve the installed-distribution version of the ``seer`` package.

    The same source ships under multiple PyPI distribution names (``seer-cli``,
    ``kata-cli``, ``code-lens-cli``) per the lean dual-publish slice of issue
    #17. Look up which distribution provides the ``seer`` top-level package
    via ``importlib.metadata.packages_distributions()`` and return its
    version. Falls back through a known-name allowlist if that lookup is
    unavailable, and finally to ``0.0.0+local`` for editable installs without
    metadata.
    """
    dist_map = packages_distributions()
    for dist in dist_map.get("seer") or []:
        try:
            return _v(dist)
        except PackageNotFoundError:
            continue
    for fallback in ("seer-cli", "kata-cli", "code-lens-cli"):
        try:
            return _v(fallback)
        except PackageNotFoundError:
            continue
    return "0.0.0+local"  # pragma: no cover  — editable install without metadata


__version__ = _resolve_version()

__all__ = ["__version__"]
