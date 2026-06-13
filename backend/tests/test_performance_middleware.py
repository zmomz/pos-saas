"""PerformanceMiddleware registration (ISSUE-099).

The middleware is defined in ``middlewares/production.py`` but was never wired
onto the app, so the ``performance_monitor`` singleton stayed empty and the
``/api-usage``-style perf surface had no data. These tests assert the middleware
is registered and actually feeds the monitor on every request.
"""
import pytest

from services.production import performance_monitor


@pytest.mark.asyncio
async def test_request_is_recorded_by_performance_monitor(client):
    # Start from a known-empty monitor so the assertion is deterministic.
    performance_monitor._metrics.clear()
    performance_monitor._request_counts.clear()
    performance_monitor._error_counts.clear()

    resp = await client.get("/health")
    assert resp.status_code == 200

    summary = performance_monitor.get_summary()
    assert summary["total_requests"] >= 1
    # The endpoint we just hit must be among the tracked endpoints.
    assert "/health" in performance_monitor.get_metrics()


@pytest.mark.asyncio
async def test_performance_headers_are_set(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    # The middleware stamps timing + correlation headers on every response.
    assert "x-response-time-ms" in resp.headers
    assert "x-correlation-id" in resp.headers
