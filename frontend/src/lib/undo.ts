import { toast } from 'sonner';

// #231 (Productivity — undo). A deferred-commit ("undo send") primitive shared
// across list/management pages. Instead of firing a destructive mutation and
// then offering a compensating restore round-trip, the destructive action is
// held for a short window: the UI reflects the change optimistically, and if
// the operator undoes before the window elapses the commit is cancelled outright
// and never reaches the server. The single commit-or-undo settlement guarantees
// the mutation runs at most once and a late undo is a harmless no-op.

const DEFAULT_UNDO_WINDOW_MS = 6000;

export interface UndoableActionOptions {
  /** Localized, human-readable toast text (e.g. "Product deleted"). */
  message: string;
  /** Localized label for the undo affordance (e.g. "Undo"). */
  undoLabel: string;
  /** The destructive action, deferred until the undo window elapses. */
  onCommit: () => void | Promise<void>;
  /** Optional: reverse the optimistic UI change when the operator undoes. */
  onUndo?: () => void;
  /** Undo window in ms (default 6000). */
  duration?: number;
}

export interface UndoableActionHandle {
  /** Cancel the pending commit if it has not already settled. */
  undo: () => void;
}

/**
 * Schedule a destructive action behind an undo window and surface an undo toast.
 * Returns a handle whose `undo()` cancels the commit — the same path the toast's
 * action button triggers — so callers can also undo programmatically.
 */
export function undoableAction(opts: UndoableActionOptions): UndoableActionHandle {
  const { message, undoLabel, onCommit, onUndo, duration = DEFAULT_UNDO_WINDOW_MS } = opts;

  // A single latch: the action either commits or is undone, never both, and the
  // outcome fires exactly once regardless of how often undo() is invoked.
  let settled = false;

  const timer = setTimeout(() => {
    if (settled) return;
    settled = true;
    void onCommit();
  }, duration);

  const undo = () => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    toast.dismiss(toastId);
    onUndo?.();
  };

  const toastId = toast(message, {
    duration,
    action: { label: undoLabel, onClick: undo },
  });

  return { undo };
}
