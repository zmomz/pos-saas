"""SEC-13 — the dead core/mask_crypto helper must stay deleted.

mask_crypto built a hardcoded Fernet key and had zero callers. Its removal is a
security cleanup; these guards keep it from being reintroduced.
"""
import importlib

import pytest


def test_mask_crypto_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("core.mask_crypto")


def test_app_still_imports_without_mask_crypto():
    # The application package imports cleanly with the dead module removed.
    assert importlib.import_module("main") is not None
