import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { toast } from 'sonner';
import { undoableAction } from './undo';

// #231 (Productivity — undo). The deferred-commit ("undo send") primitive:
// the destructive action is delayed behind a short window and cancelled
// outright if the operator undoes, so a mistaken delete never hits the server.

vi.mock('sonner', () => {
  const t = vi.fn(() => 'tid');
  return { toast: Object.assign(t, { dismiss: vi.fn() }) };
});

const mockToast = toast as unknown as ReturnType<typeof vi.fn> & {
  dismiss: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('undoableAction', () => {
  it('shows a toast with the message and an undo action label', () => {
    undoableAction({ message: 'Product deleted', undoLabel: 'Undo', onCommit: vi.fn() });
    expect(mockToast).toHaveBeenCalledTimes(1);
    const [msg, opts] = mockToast.mock.calls[0] as [string, { action: { label: string } }];
    expect(msg).toBe('Product deleted');
    expect(opts.action.label).toBe('Undo');
  });

  it('commits the deferred action after the undo window elapses', () => {
    const onCommit = vi.fn();
    undoableAction({ message: 'x', undoLabel: 'Undo', onCommit, duration: 5000 });
    expect(onCommit).not.toHaveBeenCalled();
    vi.advanceTimersByTime(5000);
    expect(onCommit).toHaveBeenCalledTimes(1);
  });

  it('cancels the commit and dismisses the toast when undone within the window', () => {
    const onCommit = vi.fn();
    const onUndo = vi.fn();
    const { undo } = undoableAction({
      message: 'x',
      undoLabel: 'Undo',
      onCommit,
      onUndo,
      duration: 5000,
    });
    undo();
    vi.advanceTimersByTime(5000);
    expect(onCommit).not.toHaveBeenCalled();
    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(mockToast.dismiss).toHaveBeenCalledWith('tid');
  });

  it('wires the toast action button to the undo path', () => {
    const onCommit = vi.fn();
    const onUndo = vi.fn();
    undoableAction({ message: 'x', undoLabel: 'Undo', onCommit, onUndo, duration: 5000 });
    const opts = mockToast.mock.calls[0][1] as { action: { onClick: () => void } };
    opts.action.onClick();
    vi.advanceTimersByTime(5000);
    expect(onCommit).not.toHaveBeenCalled();
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it('is idempotent: commits at most once and a late undo is a no-op', () => {
    const onCommit = vi.fn();
    const onUndo = vi.fn();
    const { undo } = undoableAction({
      message: 'x',
      undoLabel: 'Undo',
      onCommit,
      onUndo,
      duration: 5000,
    });
    vi.advanceTimersByTime(5000);
    expect(onCommit).toHaveBeenCalledTimes(1);
    undo(); // too late — already committed
    expect(onUndo).not.toHaveBeenCalled();
    vi.advanceTimersByTime(5000);
    expect(onCommit).toHaveBeenCalledTimes(1);
  });
});
