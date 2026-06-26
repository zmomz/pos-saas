/**
 * Offline POS queue (Phase E).
 *
 * When the device is offline, completed sales are buffered in IndexedDB and
 * replayed to `POST /api/v1/production/offline/sync` once connectivity returns.
 * Each queued sale carries a client-generated `offline_id`; the backend dedupes
 * on it, so a flaky reconnect that replays the same batch never double-posts.
 *
 * Pair this with the service worker (`public/sw.js`) which caches the app shell
 * so the POS keeps loading with no network.
 */

const DB_NAME = 'pos-offline';
const STORE = 'queued-transactions';
const DB_VERSION = 1;

/**
 * Ring-buffer cap on the offline queue (POS-12, P0 `[market]`: "offline cap …
 * ≥500 queued sales"). A long outage must not grow IndexedDB without bound, so
 * once the queue holds {@link OFFLINE_QUEUE_CAP} sales each new sale evicts the
 * oldest queued one. 500 is the SRS floor — the merchant can buffer at least a
 * full day of sales before the very oldest starts rolling off.
 */
export const OFFLINE_QUEUE_CAP = 500;

/**
 * Sales per sync request. The backlog is flushed in bounded chunks rather than
 * one giant payload (POS-12 "deterministic … handling on sync") — a 500-deep
 * backlog replays as several requests, each settled and cleared independently,
 * so a drop mid-flush still keeps the progress already made.
 */
export const SYNC_CHUNK_SIZE = 100;

export interface QueuedTransaction {
  offline_id: string;
  client_id?: number;
  subtotal?: number;
  vat_amount?: number;
  discount_amount?: number;
  total_amount?: number;
  payment_method?: string;
  items?: unknown[];
  customer_name?: string;
  customer_phone?: string;
  queued_at: string;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'offline_id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function genOfflineId(): string {
  const rand = Math.random().toString(36).slice(2, 10).toUpperCase();
  return `OFFLINE-${Date.now().toString(36).toUpperCase()}-${rand}`;
}

export function isOnline(): boolean {
  return typeof navigator === 'undefined' ? true : navigator.onLine;
}

/**
 * Split an array into bounded chunks. Pure — drives the chunked sync so the
 * backlog never goes out in one oversized request.
 */
export function chunk<T>(items: T[], size: number): T[][] {
  if (size <= 0) return items.length ? [items] : [];
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    out.push(items.slice(i, i + size));
  }
  return out;
}

/**
 * The ring-buffer eviction policy, isolated as a pure function so it can be
 * tested deterministically: given the currently-queued records and a cap,
 * return the `offline_id`s to evict (oldest first) to bring the queue down to
 * the cap. Oldest is by `queued_at`, with `offline_id` as a stable tiebreaker
 * so two sales queued in the same millisecond evict deterministically.
 */
export function selectEvictions(
  records: Array<Pick<QueuedTransaction, 'offline_id' | 'queued_at'>>,
  cap: number
): string[] {
  if (records.length <= cap) return [];
  const sorted = [...records].sort((a, b) => {
    if (a.queued_at !== b.queued_at) return a.queued_at < b.queued_at ? -1 : 1;
    return a.offline_id < b.offline_id ? -1 : a.offline_id > b.offline_id ? 1 : 0;
  });
  return sorted.slice(0, records.length - cap).map((r) => r.offline_id);
}

export async function enqueueTransaction(
  txn: Omit<QueuedTransaction, 'offline_id' | 'queued_at'>
): Promise<QueuedTransaction> {
  const record: QueuedTransaction = {
    ...txn,
    offline_id: genOfflineId(),
    queued_at: new Date().toISOString(),
  };
  const db = await openDb();
  try {
    // 1) Persist the new sale.
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(record);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    // 2) Enforce the ring-buffer cap — evict the oldest beyond OFFLINE_QUEUE_CAP.
    const all = await new Promise<QueuedTransaction[]>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const req = tx.objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result as QueuedTransaction[]);
      req.onerror = () => reject(req.error);
    });
    const evict = selectEvictions(all, OFFLINE_QUEUE_CAP);
    if (evict.length) {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE, 'readwrite');
        const store = tx.objectStore(STORE);
        evict.forEach((id) => store.delete(id));
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    }
  } finally {
    db.close();
  }
  return record;
}

export async function getQueued(): Promise<QueuedTransaction[]> {
  const db = await openDb();
  const items = await new Promise<QueuedTransaction[]>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result as QueuedTransaction[]);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return items;
}

export async function queuedCount(): Promise<number> {
  return (await getQueued()).length;
}

async function removeQueued(offlineIds: string[]): Promise<void> {
  if (!offlineIds.length) return;
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    const store = tx.objectStore(STORE);
    offlineIds.forEach((id) => store.delete(id));
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

/**
 * Flush the queue via the sync endpoint. Returns how many queued sales the
 * server durably settled (`flushed`) and how many it rejected (`failed`), the
 * latter left in the queue to retry on the next flush. The injected `sync` is
 * normally `api.syncOfflineTransactions`.
 */
export async function flushQueue(
  sync: (txns: Array<Record<string, unknown>>) => Promise<{
    processed: number;
    skipped_duplicates: number;
    accepted_offline_ids?: string[];
  }>
): Promise<{ flushed: number; failed: number } | null> {
  if (!isOnline()) return null;
  const queued = await getQueued();
  if (!queued.length) return { flushed: 0, failed: 0 };

  // Replay the backlog in bounded chunks rather than one giant payload. Each
  // chunk is settled and cleared independently, so a reconnect that drops
  // mid-flush keeps whatever already synced (POS-12 deterministic sync).
  let flushed = 0;
  let failed = 0;
  for (const batch of chunk(queued, SYNC_CHUNK_SIZE)) {
    const result = await sync(batch as unknown as Array<Record<string, unknown>>);
    const batchIds = batch.map((q) => q.offline_id);
    // FE-03: the server reports exactly which offline_ids it durably settled
    // (booked now or already booked on a prior sync). Delete ONLY those —
    // anything it rejected stays queued and is retried next flush — so a
    // partially-accepted batch never silently drops a rejected sale.
    let acceptedIds: string[];
    if (Array.isArray(result.accepted_offline_ids)) {
      const accepted = new Set(result.accepted_offline_ids);
      acceptedIds = batchIds.filter((id) => accepted.has(id));
    } else {
      // Legacy backend without per-id accounting: fall back to the settled
      // count and clear the whole batch only when something was settled.
      const settled = (result.processed || 0) + (result.skipped_duplicates || 0);
      acceptedIds = settled > 0 ? batchIds : [];
    }
    await removeQueued(acceptedIds);
    flushed += acceptedIds.length;
    failed += batchIds.length - acceptedIds.length;
  }
  return { flushed, failed };
}

/**
 * Register auto-flush on reconnect. Returns an unsubscribe function.
 */
export function registerAutoFlush(
  sync: (txns: Array<Record<string, unknown>>) => Promise<{
    processed: number;
    skipped_duplicates: number;
  }>
): () => void {
  const handler = () => {
    flushQueue(sync).catch((e) => console.warn('Offline flush failed:', e));
  };
  window.addEventListener('online', handler);
  // Attempt an immediate flush in case we loaded already-online with a backlog.
  handler();
  return () => window.removeEventListener('online', handler);
}
