// F-014 (POS-12, P0 [market]): the offline queue must be capped (ring buffer,
// ≥500 queued sales — oldest evicted on overflow) and must sync in bounded
// chunks rather than one giant payload. Before this fix enqueue had no cap and
// flushQueue sent the entire backlog in a single request.
//
// `fake-indexeddb/auto` gives jsdom a real IndexedDB so we exercise the actual
// enqueue/evict/flush path, not a mock.
import 'fake-indexeddb/auto';
import { IDBFactory } from 'fake-indexeddb';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import {
  enqueueTransaction,
  getQueued,
  flushQueue,
  selectEvictions,
  chunk,
  OFFLINE_QUEUE_CAP,
  SYNC_CHUNK_SIZE,
} from './offlineQueue';

beforeEach(() => {
  // Fresh IndexedDB per test for isolation.
  (globalThis as unknown as { indexedDB: IDBFactory }).indexedDB = new IDBFactory();
  // flushQueue early-returns when offline.
  Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true });
});

function sale(n: number) {
  return { total_amount: n, payment_method: 'cash', items: [] };
}

describe('selectEvictions (ring-buffer policy, POS-12)', () => {
  it('evicts the oldest beyond the cap, oldest first', () => {
    const records = Array.from({ length: OFFLINE_QUEUE_CAP + 1 }, (_, i) => ({
      offline_id: `id-${i}`,
      queued_at: new Date(2024, 0, 1, 0, 0, i).toISOString(), // strictly increasing
    }));
    const evicted = selectEvictions(records, OFFLINE_QUEUE_CAP);
    expect(evicted).toEqual(['id-0']); // exactly the single oldest
  });

  it('evicts nothing while at or under the cap', () => {
    const records = Array.from({ length: OFFLINE_QUEUE_CAP }, (_, i) => ({
      offline_id: `id-${i}`,
      queued_at: new Date(2024, 0, 1, 0, 0, i).toISOString(),
    }));
    expect(selectEvictions(records, OFFLINE_QUEUE_CAP)).toEqual([]);
  });

  it('breaks ties deterministically by offline_id when queued_at is equal', () => {
    const same = new Date(2024, 0, 1).toISOString();
    const records = [
      { offline_id: 'b', queued_at: same },
      { offline_id: 'a', queued_at: same },
      { offline_id: 'c', queued_at: same },
    ];
    expect(selectEvictions(records, 2)).toEqual(['a']); // smallest id is "oldest"
  });
});

describe('chunk (bounded sync, POS-12)', () => {
  it('splits into bounded chunks, last one short', () => {
    expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
  });
  it('returns one chunk when smaller than the size', () => {
    expect(chunk([1, 2], 100)).toEqual([[1, 2]]);
  });
  it('returns no chunks for an empty list', () => {
    expect(chunk([], 100)).toEqual([]);
  });
});

describe('enqueueTransaction ring-buffer cap (POS-12 / F-014)', () => {
  it('caps the queue at OFFLINE_QUEUE_CAP and evicts the oldest on overflow', async () => {
    // Enqueue one past the cap.
    for (let i = 0; i < OFFLINE_QUEUE_CAP; i++) {
      await enqueueTransaction(sale(i));
    }
    expect((await getQueued()).length).toBe(OFFLINE_QUEUE_CAP);

    const last = await enqueueTransaction(sale(9999));
    const queued = await getQueued();

    // Still capped — overflow evicted, not appended (would be 501 before the fix).
    expect(queued.length).toBe(OFFLINE_QUEUE_CAP);
    // The newest sale survives; exactly one prior sale rolled off.
    expect(queued.some((q) => q.offline_id === last.offline_id)).toBe(true);
  }, 30000);
});

describe('flushQueue chunked sync (POS-12 / F-014)', () => {
  it('flushes the backlog in SYNC_CHUNK_SIZE batches, not one giant request', async () => {
    const total = SYNC_CHUNK_SIZE * 2 + 50; // 250 with default 100
    for (let i = 0; i < total; i++) {
      await enqueueTransaction(sale(i));
    }

    const batchSizes: number[] = [];
    const sync = vi.fn(async (txns: Array<Record<string, unknown>>) => {
      batchSizes.push(txns.length);
      return { processed: txns.length, skipped_duplicates: 0 };
    });

    const result = await flushQueue(sync);

    // Three bounded requests, never one payload of `total`.
    expect(batchSizes).toEqual([SYNC_CHUNK_SIZE, SYNC_CHUNK_SIZE, 50]);
    expect(Math.max(...batchSizes)).toBeLessThanOrEqual(SYNC_CHUNK_SIZE);
    expect(result).toEqual({ flushed: total });
    // Everything settled is cleared locally.
    expect((await getQueued()).length).toBe(0);
  }, 30000);
});
