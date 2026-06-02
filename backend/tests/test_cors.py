"""Unit tests for the environment-aware CORS configuration."""
import importlib

import core.cors as cors_module
from core.config import settings


def _reload():
    return importlib.reload(cors_module)


def test_explicit_origins_take_priority(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "https://a.com,https://b.com", raising=False)
    cfg = _reload().get_cors_config()
    assert cfg["allow_origins"] == ["https://a.com", "https://b.com"]
    assert cfg["allow_credentials"] is True
    assert "allow_origin_regex" not in cfg


def test_dev_falls_back_to_wildcard_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "dev")
    cfg = _reload().get_cors_config()
    assert cfg.get("allow_origin_regex") == r".*"
    # Wildcard + credentials is invalid in browsers, so credentials must be off.
    assert cfg["allow_credentials"] is False


def test_prod_fails_closed_to_localhost(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "prod")
    cfg = _reload().get_cors_config()
    assert "allow_origins" in cfg
    assert "allow_origin_regex" not in cfg
    assert all(o.startswith("http://localhost") or o.startswith("http://127.0.0.1") for o in cfg["allow_origins"])
