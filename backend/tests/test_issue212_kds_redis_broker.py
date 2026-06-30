"""ISSUE-212 — Redis-backed KDS broker lifts the single-worker constraint.

services/kds_channel.py grew a pluggable backend behind the same
``subscribe`` / ``unsubscribe`` / ``publish`` surface (#212):

* the in-process backend (default) fans events out within one worker, and
* a Redis pub/sub backend fans them across workers so the restaurant tier can
  scale horizontally.

Real Redis isn't available in CI, so these tests inject a tiny in-memory fake
that mimics the ``redis.asyncio`` pub/sub surface the backend touches. The fan-out
test wires up *two* backends against the same fake server — standing in for two
uvicorn workers — and proves an event published in one reaches a subscriber on
the other. The guard tests pin that the single-worker assertion steps aside once
a shared backend is active.
"""
import asyncio
import sys
import types

import pytest

from services.kds_channel import (
    InProcessKdsBackend,
    KdsChannel,
    RedisKdsBackend,
    assert_single_worker_safe,
)


# --- Minimal in-memory stand-in for redis.asyncio --------------------------
class _FakeServer:
    """Shared message bus: channel name -> the pubsub queues listening on it."""

    def __init__(self):
        self.channels = {}


class _FakePubSub:
    def __init__(self, server):
        self._server = server
        self._queue = asyncio.Queue()
        self._channel = None

    async def subscribe(self, channel):
        self._channel = channel
        self._server.channels.setdefault(channel, []).append(self._queue)

    async def listen(self):
        while True:
            data = await self._queue.get()
            yield {"type": "message", "channel": self._channel, "data": data}

    async def aclose(self):
        subs = self._server.channels.get(self._channel, [])
        if self._queue in subs:
            subs.remove(self._queue)


class _FakeRedis:
    def __init__(self, server):
        self._server = server

    async def ping(self):
        return True

    def pubsub(self):
        return _FakePubSub(self._server)

    async def publish(self, channel, data):
        for q in list(self._server.channels.get(channel, [])):
            q.put_nowait(data)

    async def aclose(self):
        pass


@pytest.fixture
def fake_redis(monkeypatch):
    """Install a fake ``redis.asyncio`` whose ``from_url`` shares one server."""
    server = _FakeServer()

    def from_url(url, decode_responses=False):
        return _FakeRedis(server)

    fake_asyncio = types.SimpleNamespace(from_url=from_url)
    fake_redis_mod = types.ModuleType("redis")
    fake_redis_mod.asyncio = fake_asyncio
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio)
    return server


async def test_redis_backend_fans_out_across_workers(fake_redis):
    """An event published on one worker reaches a subscriber on another (#212)."""
    worker_a = RedisKdsBackend("redis://fake/0")
    worker_b = RedisKdsBackend("redis://fake/0")
    await worker_a.start()
    await worker_b.start()
    try:
        # A KDS stream lives on worker B; the fire happens on worker A.
        queue = worker_b.subscribe("owner-1")
        await worker_a.publish("owner-1", {"type": "fired", "card": {"id": 7}})

        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event == {"type": "fired", "card": {"id": 7}}
    finally:
        await worker_a.stop()
        await worker_b.stop()


async def test_redis_backend_only_delivers_to_the_right_owner(fake_redis):
    """Cross-worker fan-out stays tenant-scoped by user_id."""
    worker_a = RedisKdsBackend("redis://fake/0")
    worker_b = RedisKdsBackend("redis://fake/0")
    await worker_a.start()
    await worker_b.start()
    try:
        mine = worker_b.subscribe("owner-1")
        theirs = worker_b.subscribe("owner-2")
        await worker_a.publish("owner-1", {"type": "bumped", "card": {"id": 1}})

        event = await asyncio.wait_for(mine.get(), timeout=1.0)
        assert event["card"]["id"] == 1
        assert theirs.empty()
    finally:
        await worker_a.stop()
        await worker_b.stop()


async def test_channel_configure_switches_to_redis(fake_redis):
    """configure(redis_url=...) swaps the facade onto the multi-worker backend."""
    channel = KdsChannel()
    assert channel.is_multi_worker_safe is False  # in-process default
    await channel.configure(redis_url="redis://fake/0")
    try:
        assert channel.is_multi_worker_safe is True
        # And the public surface still works end-to-end through the new backend.
        queue = channel.subscribe("owner-1")
        await channel.publish("owner-1", {"type": "recalled", "card": {"id": 3}})
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert event["type"] == "recalled"
    finally:
        await channel.shutdown()


async def test_configure_without_redis_stays_in_process():
    """No Redis URL → the in-process default is left untouched."""
    channel = KdsChannel()
    await channel.configure(redis_url=None)
    assert channel.is_multi_worker_safe is False
    assert isinstance(channel._backend, InProcessKdsBackend)


def test_guard_is_noop_when_backend_is_multi_worker_safe(fake_redis, monkeypatch):
    """The single-worker assertion no longer blocks a Redis multi-worker deploy."""
    monkeypatch.delenv("KDS_ALLOW_MULTI_WORKER", raising=False)
    monkeypatch.setenv("WEB_CONCURRENCY", "8")

    class _SafeBroker:
        is_multi_worker_safe = True

    # Even with a multi-worker env and no opt-out, a safe backend short-circuits.
    assert assert_single_worker_safe(broker=_SafeBroker()) is None


def test_guard_still_fires_for_in_process_backend(monkeypatch):
    """With the in-process backend, a multi-worker env still fails loud."""
    monkeypatch.delenv("KDS_ALLOW_MULTI_WORKER", raising=False)
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeError, match="4 workers"):
        assert_single_worker_safe(broker=InProcessKdsBackend())
