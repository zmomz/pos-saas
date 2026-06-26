"""SEC-04 — Gate mock-data seeding behind explicit opt-in.

``initialize_mock_data`` previously ran at *every* boot and seeded the live DB,
skipping only when ``SKIP_INIT_DATA`` was set — a fail-open default that meant a
fresh production deploy silently populated packages/agents/etc. with demo rows.

These tests pin the inverted, fail-closed contract:

* seeding is *off* by default (a fresh prod boot leaves the DB untouched);
* it turns on only via an explicit ``LOAD_MOCK_DATA`` flag *or* when
  ``ENVIRONMENT=dev`` (dev/CI keep their convenience seeding);
* ``initialize_mock_data`` short-circuits before touching any table when the
  gate is closed.
"""
import os

import pytest

from services import mock_data


@pytest.fixture(autouse=True)
def _clean_seed_env(monkeypatch):
    """Each case controls the gate explicitly; start from a clean slate."""
    monkeypatch.delenv("LOAD_MOCK_DATA", raising=False)
    monkeypatch.delenv("SKIP_INIT_DATA", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    yield


def test_disabled_by_default_on_a_fresh_prod_boot(monkeypatch):
    # No ENVIRONMENT (defaults to prod) and no opt-in flag -> must not seed.
    assert mock_data._should_load_mock_data() is False


def test_enabled_in_dev(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    assert mock_data._should_load_mock_data() is True


def test_enabled_by_explicit_flag_even_in_prod(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("LOAD_MOCK_DATA", "true")
    assert mock_data._should_load_mock_data() is True


def test_falsey_flag_does_not_enable(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("LOAD_MOCK_DATA", "false")
    assert mock_data._should_load_mock_data() is False


@pytest.mark.asyncio
async def test_initialize_short_circuits_when_gate_closed(monkeypatch):
    """When seeding is disabled it returns before reading any table file."""
    called = False

    async def _boom(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(mock_data, "_load_table_from_file", _boom)
    # Gate closed: prod + no flag.
    await mock_data.initialize_mock_data()
    assert called is False
