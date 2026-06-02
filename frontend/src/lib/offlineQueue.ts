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

export async function enqueueTransaction(
  txn: Omit<QueuedTransaction, 'offline_id' | 'queued_at'>
): Promise<QueuedTransaction> {
  const record: QueuedTransaction = {
    ...txn,
    offline_id: genOfflineId(),
    queued_at: new Date().toISOString(),
  };
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
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
 * Flush the queue via the sync endpoint. Returns the number of transactions
 * accepted (processed + skipped duplicates), which are then cleared locally.
 * The injected `sync` is normally `api.syncOfflineTransactions`.
 */
export async function flushQueue(
  sync: (txns: Array<Record<string, unknown>>) => Promise<{
    processed: number;
    skipped_duplicates: number;
  }>
): Promise<{ flushed: number } | null> {
  if (!isOnline()) return null;
  const queued = await getQueued();
  if (!queued.length) return { flushed: 0 };

  const result = await sync(queued as unknown as Array<Record<string, unknown>>);
  // Everything the server processed or recognised as a duplicate is settled.
  const settled = (result.processed || 0) + (result.skipped_duplicates || 0);
  if (settled > 0) {
    await removeQueued(queued.map((q) => q.offline_id));
  }
  return { flushed: settled };
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
