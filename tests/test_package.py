"""Package-level smoke test."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import seer
from seer import _resolve_version


def test_version_is_a_nonempty_string() -> None:
    assert isinstance(seer.__version__, str)
    assert seer.__version__


def test_resolve_version_handles_each_dual_publish_dist_name(monkeypatch) -> None:
    """The same source ships under three PyPI names; --version must work for each."""
    for dist_name in ("seer-cli", "kata-cli", "code-lens-cli"):
        monkeypatch.setattr(
            "seer.packages_distributions",
            lambda dn=dist_name: {"seer": [dn]},
        )
        monkeypatch.setattr(
            "seer._v",
            lambda name, dn=dist_name: (
                "9.9.9" if name == dn else (_ for _ in ()).throw(PackageNotFoundError(name))
            ),
        )
        assert _resolve_version() == "9.9.9"


def test_resolve_version_falls_back_through_known_dist_names(monkeypatch) -> None:
    """When packages_distributions() can't help, fall back through the known-name list."""
    monkeypatch.setattr("seer.packages_distributions", lambda: {})

    def fake_v(name: str) -> str:
        if name == "kata-cli":
            return "1.2.3"
        raise PackageNotFoundError(name)

    monkeypatch.setattr("seer._v", fake_v)
    assert _resolve_version() == "1.2.3"


def test_resolve_version_local_fallback_when_nothing_resolves(monkeypatch) -> None:
    """Editable install without metadata: returns the local sentinel."""
    monkeypatch.setattr("seer.packages_distributions", lambda: {})

    def always_missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("seer._v", always_missing)
    assert _resolve_version() == "0.0.0+local"
