"""SEC-01 — startup secret validation.

The app signs/validates JWTs with a source-visible default secret
(``change-me-in-production``); HS256 with a known key enables token forgery and
full admin impersonation. ``validate_secrets()`` must fail prod boot on an
unset/default/short JWT secret while leaving dev untouched (ephemeral key).
"""
import pytest

from core.config import DEFAULT_JWT_SECRET, MIN_JWT_SECRET_LENGTH, settings, validate_secrets


def _strong_key() -> str:
    return "x" * MIN_JWT_SECRET_LENGTH


def test_prod_boot_rejects_default_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setattr(settings, "jwt_secret_key", DEFAULT_JWT_SECRET, raising=False)
    with pytest.raises(RuntimeError):
        validate_secrets()


def test_prod_boot_rejects_empty_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setattr(settings, "jwt_secret_key", "", raising=False)
    with pytest.raises(RuntimeError):
        validate_secrets()


def test_prod_boot_rejects_short_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * (MIN_JWT_SECRET_LENGTH - 1), raising=False)
    with pytest.raises(RuntimeError):
        validate_secrets()


def test_prod_boot_accepts_strong_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setattr(settings, "jwt_secret_key", _strong_key(), raising=False)
    # Prod also requires a dedicated at-rest secrets key (SEC-05); provide one so
    # the full validator passes.
    monkeypatch.setattr(settings, "secrets_encryption_key", "dedicated-at-rest-key", raising=False)
    # Must not raise, and must not mutate an already-strong secret.
    validate_secrets()
    assert settings.jwt_secret_key == _strong_key()


def test_dev_generates_ephemeral_key_instead_of_failing(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setattr(settings, "jwt_secret_key", DEFAULT_JWT_SECRET, raising=False)
    # Dev never aborts; it swaps in a generated ephemeral key strong enough to sign with.
    validate_secrets()
    assert settings.jwt_secret_key != DEFAULT_JWT_SECRET
    assert len(settings.jwt_secret_key) >= MIN_JWT_SECRET_LENGTH
