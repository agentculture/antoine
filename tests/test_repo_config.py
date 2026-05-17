"""Tests for antoine.repo.config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from antoine.repo.config import DEFAULT_SKIP_DIRS, RepoMapConfig, load_config


def test_defaults() -> None:
    cfg = RepoMapConfig()
    assert cfg.roots == [Path.home() / "git"]
    assert cfg.additional_markers == []
    assert set(DEFAULT_SKIP_DIRS).issubset(set(cfg.skip_dirs))
    assert cfg.default_connections_depth == 1


def test_load_config_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "does-not-exist.json")
    assert cfg == RepoMapConfig()


def test_load_config_reads_json(tmp_path: Path) -> None:
    f = tmp_path / "config.json"
    f.write_text(
        json.dumps(
            {
                "roots": ["/r1", "/r2"],
                "additional_markers": ["culture.yaml"],
                "skip_dirs": ["foo"],
                "default_connections_depth": 3,
            }
        )
    )
    cfg = load_config(f)
    assert cfg.roots == [Path("/r1"), Path("/r2")]
    assert cfg.additional_markers == ["culture.yaml"]
    assert cfg.skip_dirs == ["foo"]
    assert cfg.default_connections_depth == 3


def test_load_config_partial_keys_filled_with_defaults(tmp_path: Path) -> None:
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"additional_markers": ["culture.yaml"]}))
    cfg = load_config(f)
    assert cfg.additional_markers == ["culture.yaml"]
    assert cfg.roots == [Path.home() / "git"]
    assert cfg.default_connections_depth == 1


def test_load_config_malformed_json_raises(tmp_path: Path) -> None:
    f = tmp_path / "config.json"
    f.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        load_config(f)


def test_load_config_explicit_empty_lists_are_preserved(tmp_path: Path) -> None:
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"roots": [], "skip_dirs": []}))
    cfg = load_config(f)
    assert cfg.roots == []
    assert cfg.skip_dirs == []
    # Untouched keys still default
    assert cfg.additional_markers == []
    assert cfg.default_connections_depth == 1


def test_load_config_empty_json_object_uses_defaults(tmp_path: Path) -> None:
    f = tmp_path / "config.json"
    f.write_text("{}")
    cfg = load_config(f)
    assert cfg == RepoMapConfig()
