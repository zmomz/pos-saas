"""ARC-09 — the in-process KDS broker must be single-worker safe (or fail loud).

services/kds_channel.py fans KDS fire/bump/recall events out over per-owner
``asyncio.Queue``s held in *this* process. Under more than one uvicorn worker an
event published in worker A never reaches the SSE subscribers attached to worker
B, so kitchen-board updates are silently dropped — the board just stops updating.

The smallest viable slice (full Redis pub/sub is the follow-up) is to enforce the
single-worker invariant the module already documents: a startup guard that refuses
to boot under a multi-worker configuration with a clear, actionable error, while
leaving the single-worker path (the only deployment ``run.ps1`` and CI use)
working untouched. These tests pin that behavior through the public
``assert_single_worker_safe`` seam.
"""
import pytest

from services.kds_channel import assert_single_worker_safe


def test_multi_worker_count_fails_loud():
    """An explicit worker count > 1 raises a clear error (events would drop)."""
    with pytest.raises(RuntimeError, match="worker"):
        assert_single_worker_safe(2)


def test_single_worker_is_a_no_op(monkeypatch):
    """The single-worker path (count 1, no env) boots untouched."""
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS",
                 "KDS_ALLOW_MULTI_WORKER"):
        monkeypatch.delenv(name, raising=False)
    assert_single_worker_safe(1) is None
    # And with nothing supplied it resolves the (default) single-worker env.
    assert_single_worker_safe() is None


def test_web_concurrency_env_is_detected(monkeypatch):
    """A multi-worker env var (the form uvicorn honors) is caught at boot."""
    monkeypatch.delenv("KDS_ALLOW_MULTI_WORKER", raising=False)
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeError, match="4 workers"):
        assert_single_worker_safe()


def test_uvicorn_workers_env_is_detected(monkeypatch):
    """The explicit UVICORN_WORKERS form is detected too."""
    monkeypatch.delenv("KDS_ALLOW_MULTI_WORKER", raising=False)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.setenv("UVICORN_WORKERS", "2")
    with pytest.raises(RuntimeError):
        assert_single_worker_safe()


def test_explicit_opt_out_allows_multi_worker(monkeypatch):
    """An operator who owns a shared broker can opt out via the env flag."""
    monkeypatch.setenv("WEB_CONCURRENCY", "8")
    monkeypatch.setenv("KDS_ALLOW_MULTI_WORKER", "1")
    assert_single_worker_safe() is None


async def test_startup_lifespan_enforces_the_guard(monkeypatch):
    """The app's startup refuses to boot under a multi-worker configuration.

    Proves the guard is actually wired into main.lifespan: it must raise before
    the DB/migrations init that follows it, so a misconfigured deploy fails fast.
    """
    import main

    monkeypatch.delenv("KDS_ALLOW_MULTI_WORKER", raising=False)
    monkeypatch.setenv("WEB_CONCURRENCY", "3")
    with pytest.raises(RuntimeError, match="worker"):
        async with main.lifespan(main.app):
            pass
