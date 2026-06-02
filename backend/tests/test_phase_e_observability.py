"""Phase E — Sentry error tracking is a safe no-op when unconfigured."""
import os

from core.observability import init_sentry


def test_sentry_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_sentry_noop_blank_dsn(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "   ")
    assert init_sentry() is False
