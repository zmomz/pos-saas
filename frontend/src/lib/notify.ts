import { toast } from 'sonner';

// FE-04: shared error-surfacing helper. ~40+ handlers across the SPA swallowed
// failures into console.error, so a failed checkout / mutation looked identical
// to a no-op and a failed list fetch looked identical to "empty". This gives
// every handler one call that (a) keeps the console trace for debugging and
// (b) raises a visible toast so the operator knows the action did NOT happen.

/**
 * Best-effort, human-readable message for an arbitrary thrown value.
 *
 * Prefers the backend's FastAPI `detail` string (e.g. "Insufficient stock for
 * X") when it is a plain string — that is the most actionable text for the
 * operator. A non-string detail (FastAPI validation returns a list of objects)
 * or any other shape falls back to the caller's localized message.
 */
export function errorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return fallback;
}

/**
 * Surface a failed action to the operator as an error toast, while preserving
 * the console trace for debugging. `fallback` should be a localized,
 * user-facing message describing what failed.
 */
export function notifyError(err: unknown, fallback: string): void {
  // Keep the original error in the console for diagnosis.
  console.error(fallback, err);
  toast.error(errorMessage(err, fallback));
}
