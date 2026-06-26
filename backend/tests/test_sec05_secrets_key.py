"""SEC-05 — dedicated at-rest secrets-encryption key.

Stored secrets (payment-gateway keys, saved-card tokens, ZATCA credentials) are
AES-256-GCM encrypted under a key that, absent a dedicated value, falls back to
the JWT signing secret. Sharing the signing key with the data-encryption key
means a single leak compromises both. ``validate_secrets()`` (the SEC-01 startup
validator) must therefore require a dedicated ``SECRETS_ENCRYPTION_KEY`` (or the
legacy ``ZATCA_ENCRYPTION_KEY``) in production while leaving dev's JWT fallback
intact, and the key resolution must prefer the dedicated key over the fallback.
"""
import pytest

from core.config import (
    MIN_JWT_SECRET_LENGTH,
    dedicated_secrets_key,
    settings,
    validate_secrets,
)
from core.crypto import decrypt_secret, encrypt_secret


def _strong_jwt(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret_key", "j" * MIN_JWT_SECRET_LENGTH, raising=False)


def _no_dedicated_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "secrets_encryption_key", "", raising=False)
    monkeypatch.setattr(settings, "zatca_encryption_key", "", raising=False)


def test_prod_boot_rejects_jwt_fallback_for_secrets(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    _strong_jwt(monkeypatch)
    # No dedicated key configured -> only the JWT fallback is available.
    _no_dedicated_key(monkeypatch)
    with pytest.raises(RuntimeError):
        validate_secrets()


def test_prod_boot_accepts_dedicated_secrets_key(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    _strong_jwt(monkeypatch)
    monkeypatch.setattr(settings, "secrets_encryption_key", "dedicated-at-rest-key", raising=False)
    monkeypatch.setattr(settings, "zatca_encryption_key", "", raising=False)
    validate_secrets()  # must not raise


def test_prod_boot_accepts_legacy_zatca_key(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    _strong_jwt(monkeypatch)
    # The legacy ZATCA key still satisfies the requirement (backward compat).
    monkeypatch.setattr(settings, "secrets_encryption_key", "", raising=False)
    monkeypatch.setattr(settings, "zatca_encryption_key", "legacy-zatca-key", raising=False)
    validate_secrets()  # must not raise


def test_dev_allows_jwt_fallback(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    _strong_jwt(monkeypatch)
    _no_dedicated_key(monkeypatch)
    # Dev never aborts: the JWT fallback for at-rest encryption is tolerated.
    validate_secrets()


def test_key_resolution_prefers_dedicated_over_legacy(monkeypatch):
    monkeypatch.setattr(settings, "secrets_encryption_key", "  dedicated  ", raising=False)
    monkeypatch.setattr(settings, "zatca_encryption_key", "legacy", raising=False)
    # The dedicated key wins over the legacy ZATCA key, and is stripped.
    assert dedicated_secrets_key() == "dedicated"
    monkeypatch.setattr(settings, "secrets_encryption_key", "", raising=False)
    assert dedicated_secrets_key() == "legacy"


def test_round_trip_under_dedicated_key(monkeypatch):
    _strong_jwt(monkeypatch)
    monkeypatch.setattr(settings, "secrets_encryption_key", "dedicated-at-rest-key", raising=False)
    monkeypatch.setattr(settings, "zatca_encryption_key", "", raising=False)
    token = encrypt_secret("moyasar-sk_live_xyz")
    assert token != "moyasar-sk_live_xyz"
    assert decrypt_secret(token) == "moyasar-sk_live_xyz"


def test_dedicated_key_is_used_not_jwt_fallback(monkeypatch):
    # Encrypt under the dedicated key; once it's removed, the JWT fallback is a
    # different key, so decryption must fail (proving the dedicated key was used).
    _strong_jwt(monkeypatch)
    monkeypatch.setattr(settings, "secrets_encryption_key", "dedicated-at-rest-key", raising=False)
    monkeypatch.setattr(settings, "zatca_encryption_key", "", raising=False)
    token = encrypt_secret("zatca-csid")

    _no_dedicated_key(monkeypatch)  # now _aes_key() falls back to the JWT secret
    with pytest.raises(Exception):
        decrypt_secret(token)
